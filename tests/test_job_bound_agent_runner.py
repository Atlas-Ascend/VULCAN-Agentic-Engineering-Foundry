import base64
import json

import httpx
import pytest

from vulcan.agent_runner import AgentRunRequest, AgentRunner, AgentRunnerConfigError, LoadedAgentContext
from vulcan.job_bound_agent_runner import JobBoundAgentRunner


REGISTRY_REPO = "Atlas-Ascend/Federated-Autonomous-Repository-Custodian-Agent-Fabric"
REGISTRY_PATH = "generated/REPOSITORY-AGENT-JOBS.v1.json"
REGISTRY_SOURCE_SHA = "farc-source-immutable-123"


def registry_payload(*, worker_id="REPO-AGENT-Test-Repo", repository="Atlas-Ascend/Test-Repo", count=81):
    return {
        "schema": "ga.farc.repository-agent-jobs.v1",
        "campaignId": "GA-FARC-ESTATE-AGENTIC-BUILD-002",
        "mode": "CONVERGENCE_ONLY",
        "count": count,
        "assignmentStatus": "CAMPAIGN_ASSIGNED_LOCAL_BUILD_TRUTH_CONTROLS",
        "jobs": [
            {
                "roleId": "ROLE-999",
                "repository": repository,
                "workerId": worker_id,
                "jobTitle": "Test Repository Agent",
                "jobDescription": "Perform bounded test-repository work under local Build Truth.",
            }
        ],
    }


class FakeGitHub:
    def __init__(self, registry=None, source_sha=REGISTRY_SOURCE_SHA):
        self.registry = registry if registry is not None else registry_payload()
        self.source_sha = source_sha
        self.registry_reads = 0
        self.registry_refs = []

    def status(self):
        return {"configured": True}

    def authorize(self, key):
        if key != "exec-key":
            raise RuntimeError("bad key")

    async def _request(self, method, path, *, allow=None, params=None, **kwargs):
        request = httpx.Request(method, f"https://api.github.test{path}")
        commit_path = f"/repos/{REGISTRY_REPO}/commits/main"
        content_path = f"/repos/{REGISTRY_REPO}/contents/{REGISTRY_PATH}"
        if method == "GET" and path == commit_path:
            return httpx.Response(200, json={"sha": self.source_sha}, request=request)
        if method == "GET" and path == content_path:
            self.registry_reads += 1
            self.registry_refs.append((params or {}).get("ref"))
            encoded = base64.b64encode(json.dumps(self.registry).encode()).decode()
            return httpx.Response(
                200,
                json={"type": "file", "encoding": "base64", "content": encoded, "sha": "registry-blob-123"},
                request=request,
            )
        return httpx.Response(500, json={"unexpected": f"{method} {path}", "params": params}, request=request)


class FakeModel:
    def configured(self):
        return True

    async def generate_candidate(self, prompt, system_prompt=None):
        raise AssertionError("model should not be called in job-registry unit tests")


def repo_request(**updates):
    base = {
        "campaign": "GA-FARC-ESTATE-AGENTIC-BUILD-002",
        "run_id": "ROLE-999-canary",
        "agent_class": "REPOSITORY_AGENT",
        "agent_worker_id": "REPO-AGENT-Test-Repo",
        "agent_profile_repository": "Atlas-Ascend/Test-Repo",
        "agent_profile_path": ".github/agents/repo-custodian.agent.md",
        "source_issue_repository": "Atlas-Ascend/Test-Repo",
        "source_issue_number": 7,
        "target_repository": "Atlas-Ascend/Test-Repo",
        "janus_receipt": "placeholder-for-helper-test",
        "handoff_refs": [],
    }
    base.update(updates)
    return AgentRunRequest.model_validate(base)


def loaded_context():
    return LoadedAgentContext(
        agent_profile="---\nname: Test Repo Agent\n---\nBase profile.",
        issue_title="Resolve repository role",
        issue_body="Read local truth.",
        issue_url="https://github.test/issue/7",
        default_branch="main",
        repository_context={},
        discovered_paths=[],
    )


@pytest.mark.asyncio
async def test_repository_job_assignment_resolves_exact_worker_and_repo():
    github = FakeGitHub()
    runner = JobBoundAgentRunner(github, FakeModel())
    assignment = await runner._load_job_assignment(repo_request())
    assert assignment["role_id"] == "ROLE-999"
    assert assignment["job_title"] == "Test Repository Agent"
    assert assignment["registry_source_sha"] == REGISTRY_SOURCE_SHA
    assert assignment["registry_blob_sha"] == "registry-blob-123"
    assert github.registry_refs == [REGISTRY_SOURCE_SHA]


@pytest.mark.asyncio
async def test_repository_job_assignment_fails_closed_on_worker_mismatch():
    runner = JobBoundAgentRunner(
        FakeGitHub(registry_payload(worker_id="REPO-AGENT-Someone-Else")),
        FakeModel(),
    )
    with pytest.raises(AgentRunnerConfigError, match="worker identity mismatch"):
        await runner._load_job_assignment(repo_request())


@pytest.mark.asyncio
async def test_repository_job_assignment_fails_closed_on_missing_repo():
    runner = JobBoundAgentRunner(
        FakeGitHub(registry_payload(repository="Atlas-Ascend/Other-Repo")),
        FakeModel(),
    )
    with pytest.raises(AgentRunnerConfigError, match="exactly one canonical campaign job"):
        await runner._load_job_assignment(repo_request())


@pytest.mark.asyncio
async def test_repository_job_assignment_fails_closed_on_registry_count_drift():
    runner = JobBoundAgentRunner(FakeGitHub(registry_payload(count=80)), FakeModel())
    with pytest.raises(AgentRunnerConfigError, match="count mismatch"):
        await runner._load_job_assignment(repo_request())


@pytest.mark.asyncio
async def test_repository_job_assignment_fails_closed_when_source_ref_cannot_resolve():
    runner = JobBoundAgentRunner(FakeGitHub(source_sha=""), FakeModel())
    with pytest.raises(AgentRunnerConfigError, match="source ref could not be resolved"):
        await runner._load_job_assignment(repo_request())


@pytest.mark.asyncio
async def test_office_agents_do_not_use_repository_job_registry():
    github = FakeGitHub()
    runner = JobBoundAgentRunner(github, FakeModel())
    request = AgentRunRequest.model_validate(
        {
            "campaign": "GA-FARC-ESTATE-AGENTIC-BUILD-002",
            "run_id": "HQ-25-canary",
            "agent_class": "OFFICE_AGENT",
            "agent_worker_id": "OFFICE-AGENT-HQ-25",
            "agent_profile_repository": "Atlas-Ascend/Ghost-Atlas-HQ",
            "agent_profile_path": ".github/agents/hq-25-quality-audit-office.agent.md",
            "source_issue_repository": "Atlas-Ascend/Ghost-Atlas-HQ",
            "source_issue_number": 18,
            "target_repository": "Atlas-Ascend/Federated-Autonomous-Repository-Custodian-Agent-Fabric",
            "janus_receipt": "placeholder-for-helper-test",
        }
    )
    assert await runner._load_job_assignment(request) is None
    assert github.registry_reads == 0


@pytest.mark.asyncio
async def test_repository_context_receives_immutable_canonical_job_contract(monkeypatch):
    async def fake_base_load_context(self, request):
        return loaded_context()

    monkeypatch.setattr(AgentRunner, "_load_context", fake_base_load_context)
    runner = JobBoundAgentRunner(FakeGitHub(), FakeModel())
    context = await runner._load_context(repo_request())
    assert "CAMPAIGN JOB ASSIGNMENT" in context.agent_profile
    assert "role_id=ROLE-999" in context.agent_profile
    assert "job_title=Test Repository Agent" in context.agent_profile
    assert f"@{REGISTRY_SOURCE_SHA}" in context.agent_profile
    assert "registry_blob_sha=registry-blob-123" in context.agent_profile
    assert "subordinate to local Build Truth" in context.agent_profile


@pytest.mark.asyncio
async def test_repository_run_reuses_one_registry_snapshot_when_registry_changes_after_planning(monkeypatch):
    async def fake_base_load_context(self, request):
        return loaded_context()

    async def fake_base_run(self, request, provided_key):
        self.github.authorize(provided_key)
        context = await self._load_context(request)
        changed = registry_payload()
        changed["jobs"][0]["jobTitle"] = "Changed After Planning"
        self.github.registry = changed
        assert "job_title=Test Repository Agent" in context.agent_profile
        return {"named_agent": {"agent_worker_id": request.agent_worker_id}}

    monkeypatch.setattr(AgentRunner, "_load_context", fake_base_load_context)
    monkeypatch.setattr(AgentRunner, "run", fake_base_run)

    github = FakeGitHub()
    runner = JobBoundAgentRunner(github, FakeModel())
    result = await runner.run(repo_request(), "exec-key")

    assert github.registry_reads == 1
    assert result["named_agent"]["campaign_job"]["job_title"] == "Test Repository Agent"
    assert result["named_agent"]["campaign_job"]["registry_source_sha"] == REGISTRY_SOURCE_SHA
    assert result["named_agent"]["campaign_job"]["registry_blob_sha"] == "registry-blob-123"
    assert result["job_binding_state"] == "CANONICAL_REPOSITORY_JOB_BOUND_IMMUTABLE_SNAPSHOT"
    assert runner._active_job_assignments == {}


def test_health_exposes_enforced_job_registry_binding():
    state = JobBoundAgentRunner(FakeGitHub(), FakeModel()).status()
    assert state["repository_job_count"] == 81
    assert state["repository_job_binding"] == "ENFORCED_FAIL_CLOSED"
    assert state["repository_job_snapshot_binding"] == "IMMUTABLE_PER_RUN"
    assert REGISTRY_PATH in state["repository_job_registry"]
