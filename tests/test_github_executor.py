import asyncio
import json

import httpx
import pytest
from pydantic import ValidationError

from vulcan.github_executor import (
    ExecutorAuthorizationError,
    ExecutorConfigError,
    GitHubExecutor,
    RepositoryPatchRequest,
    validate_write_path,
)


def request_payload(**overrides):
    payload = {
        "campaign": "GA-FARC-ESTATE-AGENTIC-BUILD-002",
        "run_id": "ROLE-060-canary",
        "agent_worker_id": "REPO-AGENT-VULCAN-Agentic-Engineering-Foundry",
        "repository": "Atlas-Ascend/VULCAN-Agentic-Engineering-Foundry",
        "objective": "Create an execution receipt for a bounded canary.",
        "janus_receipt": "janus-receipt-canary",
        "commit_message": "canary: add execution receipt",
        "pr_title": "[GA-FARC] VULCAN executor canary",
        "pr_body": "Deterministic executor canary.",
        "files": [{"path": "receipts/ga-farc/canary.json", "content": "{\"status\":\"EXECUTED\"}\n"}],
    }
    payload.update(overrides)
    return payload


def test_executor_is_fail_closed_without_credentials():
    executor = GitHubExecutor(token="", execution_key="")
    assert executor.status()["configured"] is False
    with pytest.raises(ExecutorConfigError):
        executor.authorize("anything")


def test_executor_rejects_wrong_execution_key():
    executor = GitHubExecutor(token="token", execution_key="expected")
    with pytest.raises(ExecutorAuthorizationError):
        executor.authorize("wrong")


def test_sensitive_and_authority_paths_are_blocked():
    blocked = [
        ".github/workflows/ci.yml",
        ".github/agents/repo-custodian.agent.md",
        ".env",
        "config/.env.production",
        "keys/deploy.pem",
        "secrets/token.txt",
        "../escape.txt",
    ]
    for path in blocked:
        with pytest.raises(ValueError):
            validate_write_path(path)


def test_request_is_bounded_to_atlas_ascend():
    with pytest.raises(ValidationError):
        RepositoryPatchRequest.model_validate(request_payload(repository="someone-else/repo"))


def test_full_pr_only_flow_with_mock_github():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path, request.headers.get("authorization")))
        path = request.url.path
        method = request.method
        if method == "GET" and path == "/repos/Atlas-Ascend/VULCAN-Agentic-Engineering-Foundry":
            return httpx.Response(200, json={"default_branch": "main"})
        if method == "GET" and path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "base123"}})
        if method == "POST" and path.endswith("/git/refs"):
            body = json.loads(request.content)
            assert body["ref"].startswith("refs/heads/ga-farc/")
            assert body["sha"] == "base123"
            return httpx.Response(201, json={"ref": body["ref"]})
        if method == "GET" and "/contents/receipts/ga-farc/canary.json" in path:
            return httpx.Response(404, json={"message": "Not Found"})
        if method == "PUT" and "/contents/receipts/ga-farc/canary.json" in path:
            body = json.loads(request.content)
            assert body["branch"].startswith("ga-farc/")
            assert "sha" not in body
            return httpx.Response(201, json={"commit": {"sha": "commit456"}})
        if method == "POST" and path.endswith("/pulls"):
            body = json.loads(request.content)
            assert body["base"] == "main"
            assert "EXECUTED_NOT_VERIFIED" in body["body"]
            return httpx.Response(201, json={"number": 77, "html_url": "https://github.test/pr/77"})
        return httpx.Response(500, json={"unexpected": f"{method} {path}"})

    executor = GitHubExecutor(
        token="test-token",
        execution_key="exec-key",
        base_url="https://api.github.test",
        transport=httpx.MockTransport(handler),
    )
    request = RepositoryPatchRequest.model_validate(request_payload())
    result = asyncio.run(executor.execute_patch(request, "exec-key"))

    assert result["status"] == "EXECUTED_NOT_VERIFIED"
    assert result["merge_performed"] is False
    assert result["pull_request_number"] == 77
    assert result["writes"] == [{"path": "receipts/ga-farc/canary.json", "commit_sha": "commit456"}]
    assert all(auth == "Bearer test-token" for _, _, auth in seen)
    assert "test-token" not in json.dumps(result)
