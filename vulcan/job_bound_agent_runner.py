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

    def status(self) -> dict:
        state = super().status()
        return {
            **state,
            "repository_job_registry": f"{JOB_REGISTRY_REPOSITORY}:{JOB_REGISTRY_PATH}@{JOB_REGISTRY_REF}",
            "repository_job_count": EXPECTED_JOB_COUNT,
            "repository_job_binding": "ENFORCED_FAIL_CLOSED",
        }

    async def _load_job_assignment(self, request: AgentRunRequest) -> dict | None:
        if request.agent_class != "REPOSITORY_AGENT":
            return None

        response = await self.github._request(
            "GET",
            f"/repos/{JOB_REGISTRY_REPOSITORY}/contents/{JOB_REGISTRY_PATH}",
            params={"ref": JOB_REGISTRY_REF},
            allow={200},
        )
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise AgentRunnerConfigError("canonical repository job registry could not be loaded")

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
            "registry_blob_sha": payload.get("sha"),
        }

    @staticmethod
    def _job_contract(assignment: dict) -> str:
        return (
            "CAMPAIGN JOB ASSIGNMENT (canonical FARC assignment truth; subordinate to local Build Truth):\n"
            f"role_id={assignment['role_id']}\n"
            f"job_title={assignment['job_title']}\n"
            f"job_description={assignment['job_description']}\n"
            f"registry={assignment['registry_repository']}:{assignment['registry_path']}@{assignment['registry_ref']}\n"
            "LAW: this assignment guides bounded work but cannot reactivate a SUPERSEDED lineage, override local Build Truth, "
            "or create replacement architecture. Resolve lifecycle and canonical ownership before mutation."
        )

    async def _load_context(self, request: AgentRunRequest) -> LoadedAgentContext:
        context = await super()._load_context(request)
        assignment = await self._load_job_assignment(request)
        if assignment is not None:
            context.agent_profile = f"{context.agent_profile.rstrip()}\n\n{self._job_contract(assignment)}\n"
        return context

    async def run(self, request: AgentRunRequest, provided_key: str | None) -> dict:
        result = await super().run(request, provided_key)
        assignment = await self._load_job_assignment(request)
        if assignment is not None:
            result.setdefault("named_agent", {})["campaign_job"] = assignment
            result["job_binding_state"] = "CANONICAL_REPOSITORY_JOB_BOUND"
        return result
