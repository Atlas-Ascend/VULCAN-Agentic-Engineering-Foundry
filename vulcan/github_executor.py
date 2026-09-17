from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

CAMPAIGN = "GA-FARC-ESTATE-AGENTIC-BUILD-002"
_ALLOWED_REPOSITORY = re.compile(r"^Atlas-Ascend/[A-Za-z0-9_.-]+$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_.-]+$")
_BLOCKED_PREFIXES = (".github/workflows/", ".github/agents/")
_BLOCKED_FILENAMES = {".env", "id_rsa", "id_ed25519"}
_BLOCKED_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
_MAX_FILES = 20
_MAX_FILE_CHARS = 200_000
_JANUS_AUTHORITY = "janus-prime"
_JANUS_POLICY = "janus-runtime-gate-v1"
_JANUS_CAPABILITY = "autobuilder.repository.patch"
_JANUS_REQUIRED_REASONS = {"AUTHENTICATED_ARCHITECT_INGRESS", "CAPABILITY_ALLOWED"}


class ExecutorConfigError(RuntimeError):
    pass


class ExecutorAuthorizationError(RuntimeError):
    pass


class GitHubExecutionError(RuntimeError):
    pass


def validate_repository(repository: str) -> str:
    if not _ALLOWED_REPOSITORY.fullmatch(repository):
        raise ValueError("repository must be an Atlas-Ascend repository slug")
    return repository


def validate_write_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    lower = normalized.lower()
    parts = normalized.split("/")
    if not normalized or normalized.startswith("/") or ".." in parts or any(not part for part in parts):
        raise ValueError("unsafe repository path")
    if any(lower.startswith(prefix) for prefix in _BLOCKED_PREFIXES):
        raise ValueError("autonomous executor cannot modify workflows or agent authority profiles")
    basename = parts[-1].lower()
    if basename in _BLOCKED_FILENAMES or basename.startswith(".env.") or basename.endswith(_BLOCKED_SUFFIXES):
        raise ValueError("autonomous executor cannot write credential material")
    if any(part.lower() in {"secrets", ".secrets"} for part in parts):
        raise ValueError("autonomous executor cannot write secret directories")
    return normalized


def validate_janus_receipt(receipt: str, *, run_id: str, agent_worker_id: str) -> dict:
    """Validate JANUS receipt integrity and binding before any mutation.

    JANUS v1 receipts carry a canonical SHA-256 digest rather than a portable
    cryptographic signature. This gate therefore proves structural integrity,
    ALLOW semantics, request correlation, and capability binding; it does not
    pretend the digest is an HMAC signature. Authentication remains provided by
    the separate JANUS ingress secret and VULCAN execution-key boundary.
    """
    try:
        payload = json.loads(receipt)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("janus_receipt must be canonical JANUS decision JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("janus_receipt must decode to an object")

    required = {
        "decision_id",
        "decision",
        "authority",
        "policy_id",
        "run_id",
        "correlation_id",
        "capability",
        "requested_by",
        "reasons",
        "decided_at",
        "receipt_digest",
    }
    missing = sorted(key for key in required if key not in payload)
    if missing:
        raise ValueError(f"janus_receipt missing fields: {','.join(missing)}")
    if payload.get("decision") != "ALLOW":
        raise ValueError("janus_receipt decision must be ALLOW")
    if payload.get("authority") != _JANUS_AUTHORITY:
        raise ValueError("janus_receipt authority mismatch")
    if payload.get("policy_id") != _JANUS_POLICY:
        raise ValueError("janus_receipt policy mismatch")
    if payload.get("run_id") != run_id:
        raise ValueError("janus_receipt run_id mismatch")
    if payload.get("requested_by") != agent_worker_id:
        raise ValueError("janus_receipt requested_by mismatch")
    if payload.get("capability") != _JANUS_CAPABILITY:
        raise ValueError("janus_receipt capability mismatch")
    if not payload.get("decision_id") or not payload.get("correlation_id"):
        raise ValueError("janus_receipt decision_id/correlation_id required")

    reasons = payload.get("reasons")
    if not isinstance(reasons, list) or not _JANUS_REQUIRED_REASONS.issubset({str(item) for item in reasons}):
        raise ValueError("janus_receipt missing authenticated allow reasons")

    digest = payload.get("receipt_digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("janus_receipt digest invalid")
    unsigned = {key: value for key, value in payload.items() if key != "receipt_digest"}
    canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    expected = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(digest, expected):
        raise ValueError("janus_receipt digest mismatch")
    return payload


class PatchFile(BaseModel):
    path: str
    content: str = Field(max_length=_MAX_FILE_CHARS)

    @field_validator("path")
    @classmethod
    def _path_is_safe(cls, value: str) -> str:
        return validate_write_path(value)


class RepositoryPatchRequest(BaseModel):
    campaign: Literal[CAMPAIGN]
    run_id: str = Field(min_length=3, max_length=96)
    agent_worker_id: str = Field(min_length=3, max_length=180)
    repository: str
    objective: str = Field(min_length=3, max_length=4000)
    janus_receipt: str = Field(min_length=3, max_length=4000)
    commit_message: str = Field(min_length=3, max_length=240)
    pr_title: str = Field(min_length=3, max_length=240)
    pr_body: str = Field(default="", max_length=20_000)
    base_branch: str | None = Field(default=None, max_length=180)
    files: list[PatchFile] = Field(min_length=1, max_length=_MAX_FILES)

    @field_validator("repository")
    @classmethod
    def _repo_is_bounded(cls, value: str) -> str:
        return validate_repository(value)

    @field_validator("run_id")
    @classmethod
    def _run_id_is_safe(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("run_id may contain only letters, numbers, dot, underscore, and hyphen")
        return value

    @field_validator("base_branch")
    @classmethod
    def _base_branch_is_safe(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", value) or ".." in value or value.startswith("/"):
            raise ValueError("unsafe base branch")
        return value

    @model_validator(mode="after")
    def _janus_receipt_is_bound(self):
        validate_janus_receipt(
            self.janus_receipt,
            run_id=self.run_id,
            agent_worker_id=self.agent_worker_id,
        )
        return self


class GitHubExecutor:
    """Bounded repository mutation adapter.

    This adapter can create a task branch, write non-sensitive text files, and open
    a pull request. It intentionally cannot merge, delete, force-push, change
    workflow files, or change GitHub agent authority profiles.
    """

    def __init__(
        self,
        token: str | None = None,
        execution_key: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._token = token if token is not None else os.getenv("GITHUB_TOKEN")
        self._execution_key = execution_key if execution_key is not None else os.getenv("VULCAN_EXECUTION_KEY")
        self._base_url = (base_url or os.getenv("GITHUB_API_URL") or "https://api.github.com").rstrip("/")
        self._transport = transport

    def status(self) -> dict:
        token_ready = bool(self._token)
        key_ready = bool(self._execution_key)
        return {
            "service": "vulcan-github-executor",
            "mode": "PR_ONLY_NO_MERGE",
            "organization": "Atlas-Ascend",
            "github_token_configured": token_ready,
            "execution_key_configured": key_ready,
            "configured": token_ready and key_ready,
            "blocked_paths": list(_BLOCKED_PREFIXES),
            "janus_receipt_gate": "ALLOW_INTEGRITY_CORRELATION_AND_CAPABILITY_REQUIRED",
            "janus_required_capability": _JANUS_CAPABILITY,
            "proof_state_on_success": "EXECUTED_NOT_VERIFIED",
        }

    def authorize(self, provided_key: str | None) -> None:
        if not self._token or not self._execution_key:
            raise ExecutorConfigError("GitHub executor is fail-closed until GITHUB_TOKEN and VULCAN_EXECUTION_KEY are configured")
        if not provided_key or not hmac.compare_digest(provided_key, self._execution_key):
            raise ExecutorAuthorizationError("invalid execution key")

    @staticmethod
    def _branch_name(request: RepositoryPatchRequest) -> str:
        worker = re.sub(r"[^A-Za-z0-9_.-]+", "-", request.agent_worker_id).strip("-").lower()
        worker = worker[:80] or "agent"
        return f"ga-farc/{worker}/{request.run_id}"[:220]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "ghost-atlas-vulcan-autobuilder/1.0",
        }

    async def _request(self, method: str, path: str, *, allow: set[int] | None = None, **kwargs) -> httpx.Response:
        async with httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers(),
            timeout=60,
            transport=self._transport,
        ) as client:
            response = await client.request(method, path, **kwargs)
        accepted = allow or {200, 201}
        if response.status_code not in accepted:
            detail = response.text[:500]
            raise GitHubExecutionError(f"GitHub API {method} {path} returned {response.status_code}: {detail}")
        return response

    async def execute_patch(self, request: RepositoryPatchRequest, provided_key: str | None) -> dict:
        self.authorize(provided_key)
        repository = validate_repository(request.repository)

        repo_response = await self._request("GET", f"/repos/{repository}", allow={200})
        repo_data = repo_response.json()
        base_branch = request.base_branch or repo_data.get("default_branch") or "main"

        base_ref = await self._request(
            "GET",
            f"/repos/{repository}/git/ref/heads/{quote(base_branch, safe='/')}",
            allow={200},
        )
        base_sha = base_ref.json()["object"]["sha"]
        branch = self._branch_name(request)

        await self._request(
            "POST",
            f"/repos/{repository}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": base_sha},
            allow={201},
        )

        commits: list[dict[str, str]] = []
        for patch in request.files:
            path = validate_write_path(patch.path)
            encoded_path = quote(path, safe="/")
            existing = await self._request(
                "GET",
                f"/repos/{repository}/contents/{encoded_path}",
                params={"ref": branch},
                allow={200, 404},
            )
            payload = {
                "message": request.commit_message,
                "content": base64.b64encode(patch.content.encode("utf-8")).decode("ascii"),
                "branch": branch,
            }
            if existing.status_code == 200:
                existing_sha = existing.json().get("sha")
                if existing_sha:
                    payload["sha"] = existing_sha

            written = await self._request(
                "PUT",
                f"/repos/{repository}/contents/{encoded_path}",
                json=payload,
                allow={200, 201},
            )
            commit_sha = written.json().get("commit", {}).get("sha", "")
            commits.append({"path": path, "commit_sha": commit_sha})

        pull = await self._request(
            "POST",
            f"/repos/{repository}/pulls",
            json={
                "title": request.pr_title,
                "head": branch,
                "base": base_branch,
                "body": (
                    f"Campaign: `{request.campaign}`\n\n"
                    f"Worker: `{request.agent_worker_id}`\n\n"
                    f"Objective: {request.objective}\n\n"
                    f"JANUS receipt: `{request.janus_receipt}`\n\n"
                    f"{request.pr_body}\n\n"
                    "Execution state: `EXECUTED_NOT_VERIFIED`. This PR may not self-merge; SECA/DevOS/HQ-25 verification is required."
                ).strip(),
            },
            allow={201},
        )
        pr = pull.json()
        return {
            "status": "EXECUTED_NOT_VERIFIED",
            "campaign": request.campaign,
            "run_id": request.run_id,
            "agent_worker_id": request.agent_worker_id,
            "repository": repository,
            "base_branch": base_branch,
            "branch": branch,
            "base_sha": base_sha,
            "writes": commits,
            "pull_request_number": pr.get("number"),
            "pull_request_url": pr.get("html_url"),
            "merge_performed": False,
            "janus_receipt_gate": "PASS_INTEGRITY_CORRELATION_AND_CAPABILITY",
            "verification_required": ["SECA", "DevOS", "HQ-25"],
            "proof_required": "ProofGrid -> Thoth",
        }
