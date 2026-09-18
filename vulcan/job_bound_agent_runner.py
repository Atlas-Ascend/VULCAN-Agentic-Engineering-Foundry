from __future__ import annotations

import base64
import json

from .agent_runner import (
    AgentRunRequest,
    AgentRunner,
    AgentRunnerConfigError,
    LoadedAgentContext,
)

JOB_REGISTRY_REPOSITORY = "Atlas-Ascend/Federated-Autonomous-Repository-Custodian-Agent-Fabric"
JOB_REGISTRY_PATH = "generated/REPOSITORY-AGENT-JOBS.v1.json"
JOB_REGISTRY_REF = "main"
EXPECTED_JOB_COUNT = 81
EXPECTED_ASSIGNMENT_STATUS = "CAMPAIGN_ASSIGNED_LOCAL_BUILD_TRUTH_CONTROLS"


class JobBoundAgentRunner(AgentRunner):
    """Named-agent runner that fail-closes on missing or mismatched FARC job truth.

    Repository jobs are campaign assignment truth, subordinate to repository-local
    Build Truth. Office agents continue to use their office-specific HQ profile and
    task surface; this registry applies only to the 81 repository agents.
    """

    def __init__(self, github, model) -> None:
        super().__init__(github, model)
        self._active_job_assignments: dict[str, dict | None] = {}

    def status(self) -> dict:
        state = super().status()
        return {
            **state,
            "repository_job_registry": f"{JOB_REGISTRY_REPOSITORY}:{JOB_REGISTRY_PATH}@{JOB_REGISTRY_REF}",
            "repository_job_count": EXPECTED_JOB_COUNT,
            "repository_job_binding": "ENFORCED_FAIL_CLOSED",
            "repository_job_snapshot_binding": "IMMUTABLE_PER_RUN",
        }

    async def _resolve_registry_source_sha(self) -> str:
        response = await self.github._request(
            "GET",
            f"/repos/{JOB_REGISTRY_REPOSITORY}/commits/{JOB_REGISTRY_REF}",
            allow={200},
        )
        payload = response.json()
        source_sha = payload.get("sha") if isinstance(payload, dict) else None
        if not isinstance(source_sha, str) or not source_sha.strip():
            raise AgentRunnerConfigError("canonical repository job registry source ref could not be resolved")
        return source_sha.strip()

    async def _load_job_assignment(self, request: AgentRunRequest) -> dict | None:
        if request.agent_class != "REPOSITORY_AGENT":
            return None

        registry_source_sha = await self._resolve_registry_source_sha()
        response = await self.github._request(
            "GET",
            f"/repos/{JOB_REGISTRY_REPOSITORY}/contents/{JOB_REGISTRY_PATH}",
            params={"ref": registry_source_sha},
            allow={200},
        )
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise AgentRunnerConfigError("canonical repository job registry could not be loaded")

        registry_blob_sha = payload.get("sha")
        if not isinstance(registry_blob_sha, str) or not registry_blob_sha.strip():
            raise AgentRunnerConfigError("canonical repository job registry blob identity is missing")

        try:
            decoded = base64.b64decode(payload.get("content") or "").decode("utf-8")
            registry = json.loads(decoded)
        except Exception as exc:
            raise AgentRunnerConfigError("canonical repository job registry is malformed") from exc

        if registry.get("campaignId") != request.campaign:
            raise AgentRunnerConfigError("repository job registry campaign mismatch")
        if registry.get("count") != EXPECTED_JOB_COUNT:
            raise AgentRunnerConfigError("repository job registry count mismatch")
        if registry.get("assignmentStatus") != EXPECTED_ASSIGNMENT_STATUS:
            raise AgentRunnerConfigError("repository job registry assignment state mismatch")

        jobs = registry.get("jobs")
        if not isinstance(jobs, list):
            raise AgentRunnerConfigError("repository job registry jobs must be an array")
        matches = [job for job in jobs if isinstance(job, dict) and job.get("repository") == request.target_repository]
        if len(matches) != 1:
            raise AgentRunnerConfigError("target repository does not resolve to exactly one canonical campaign job")

        job = matches[0]
        required = ("roleId", "repository", "workerId", "jobTitle", "jobDescription")
        if any(not job.get(field) for field in required):
            raise AgentRunnerConfigError("canonical repository job assignment is incomplete")
        if job["workerId"] != request.agent_worker_id:
            raise AgentRunnerConfigError("repository job worker identity mismatch")

        return {
            "role_id": job["roleId"],
            "repository": job["repository"],
            "worker_id": job["workerId"],
            "job_title": job["jobTitle"],
            "job_description": job["jobDescription"],
            "assignment_status": registry["assignmentStatus"],
            "registry_repository": JOB_REGISTRY_REPOSITORY,
            "registry_path": JOB_REGISTRY_PATH,
            "registry_ref": JOB_REGISTRY_REF,
            "registry_source_sha": registry_source_sha,
            "registry_blob_sha": registry_blob_sha.strip(),
        }

    @staticmethod
    def _job_contract(assignment: dict) -> str:
        return (
            "CAMPAIGN JOB ASSIGNMENT (canonical FARC assignment truth; subordinate to local Build Truth):\n"
            f"role_id={assignment['role_id']}\n"
            f"job_title={assignment['job_title']}\n"
            f"job_description={assignment['job_description']}\n"
            f"registry={assignment['registry_repository']}:{assignment['registry_path']}@{assignment['registry_source_sha']}\n"
            f"registry_canonical_ref={assignment['registry_ref']}\n"
            f"registry_blob_sha={assignment['registry_blob_sha']}\n"
            "LAW: this assignment guides bounded work but cannot reactivate a SUPERSEDED lineage, override local Build Truth, "
            "or create replacement architecture. Resolve lifecycle and canonical ownership before mutation."
        )

    async def _load_context(self, request: AgentRunRequest) -> LoadedAgentContext:
        context = await super()._load_context(request)
        if request.agent_class != "REPOSITORY_AGENT":
            return context

        if request.run_id in self._active_job_assignments:
            assignment = self._active_job_assignments[request.run_id]
            if assignment is None:
                assignment = await self._load_job_assignment(request)
                self._active_job_assignments[request.run_id] = assignment
        else:
            assignment = await self._load_job_assignment(request)

        if assignment is None:
            raise AgentRunnerConfigError("repository job assignment was not bound before model planning")
        context.agent_profile = f"{context.agent_profile.rstrip()}\n\n{self._job_contract(assignment)}\n"
        return context

    async def run(self, request: AgentRunRequest, provided_key: str | None) -> dict:
        if request.agent_class != "REPOSITORY_AGENT":
            return await super().run(request, provided_key)
        if request.run_id in self._active_job_assignments:
            raise AgentRunnerConfigError("repository job run_id is already active")

        self._active_job_assignments[request.run_id] = None
        try:
            result = await super().run(request, provided_key)
            assignment = self._active_job_assignments.get(request.run_id)
            if assignment is None:
                raise AgentRunnerConfigError("repository job assignment snapshot was not retained through execution")
            result.setdefault("named_agent", {})["campaign_job"] = assignment
            result["job_binding_state"] = "CANONICAL_REPOSITORY_JOB_BOUND_IMMUTABLE_SNAPSHOT"
            return result
        finally:
            self._active_job_assignments.pop(request.run_id, None)
