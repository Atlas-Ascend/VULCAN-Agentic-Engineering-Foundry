import base64
import json

import httpx
import pytest
from pydantic import ValidationError

from vulcan.agent_runner import AgentPlanError, AgentRunRequest, AgentRunner, AgentRunnerConfigError


class FakeGitHub:
    def __init__(self):
        self.executed = None
        self.authorized = []

    def status(self):
        return {"configured": True}

    def authorize(self, key):
        self.authorized.append(key)
        if key != "exec-key":
            raise RuntimeError("bad test key")

    async def _request(self, method, path, *, allow=None, params=None, **kwargs):
        def response(status, payload):
            return httpx.Response(status, json=payload, request=httpx.Request(method, f"https://api.github.test{path}"))

        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo":
            return response(200, {"default_branch": "main"})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/issues/7":
            return response(200, {
                "title": "[GA-FARC][ROLE-999] Resolve repository role before mutation",
                "body": "Read local Build Truth and create a bounded role receipt.",
                "html_url": "https://github.test/Atlas-Ascend/Test-Repo/issues/7",
            })
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/.github/agents/repo-custodian.agent.md":
            text = "---\nname: Test Repo Agent\n---\nMission: patch only this canonical repo and prove work."
            return response(200, {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents":
            return response(200, [
                {"name": "README.md", "path": "README.md", "type": "file"},
                {"name": ".ghost-atlas", "path": ".ghost-atlas", "type": "dir"},
                {"name": "tests", "path": "tests", "type": "dir"},
            ])
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/.ghost-atlas":
            return response(200, [{"name": "BUILD_TRUTH.md", "path": ".ghost-atlas/BUILD_TRUTH.md", "type": "file"}])
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/tests":
            return response(200, [{"name": "test_app.py", "path": "tests/test_app.py", "type": "file"}])
        if method == "GET" and path in {
            "/repos/Atlas-Ascend/Test-Repo/contents/.github/workflows",
            "/repos/Atlas-Ascend/Test-Repo/contents/test",
            "/repos/Atlas-Ascend/Test-Repo/contents/src",
        }:
            return response(404, {"message": "Not Found"})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/README.md":
            text = "# Test Repo\nCanonical purpose: prove named agent execution."
            return response(200, {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/.ghost-atlas/BUILD_TRUTH.md":
            text = "Lifecycle: ACTIVE\nOwner: Test Repo\nMutation law: bounded patches only."
            return response(200, {"type": "file", "encoding": "base64", "content": base64.b64encode(text.encode()).decode()})
        return response(500, {"unexpected": f"{method} {path}", "params": params})

    async def execute_patch(self, patch, key):
        assert key == "exec-key"
        self.executed = patch
        return {
            "status": "EXECUTED_NOT_VERIFIED",
            "repository": patch.repository,
            "branch": "ga-farc/test/ROLE-999",
            "pull_request_number": 9,
            "pull_request_url": "https://github.test/pr/9",
            "merge_performed": False,
        }


class FakeModel:
    def __init__(self, raw=None, configured=True):
        self.raw = raw
        self._configured = configured
        self.system_prompt = None
        self.prompt = None

    def configured(self):
        return self._configured

    async def generate_candidate(self, prompt, system_prompt=None):
        self.prompt = prompt
        self.system_prompt = system_prompt
        if self.raw is not None:
            return self.raw
        return json.dumps({
            "lifecycle": "ACTIVE",
            "repository_role": "Canonical test repository for named-agent execution proof.",
            "diagnosis": "The assigned role-resolution issue requires an evidence receipt without replacing architecture.",
            "mutation_boundary": "Write only a campaign receipt; do not alter authority or workflow files.",
            "target_repository": "Atlas-Ascend/Test-Repo",
            "files": [{
                "path": "receipts/ga-farc/ROLE-999.json",
                "content": "{\"lifecycle\":\"ACTIVE\",\"agent\":\"REPO-AGENT-Test-Repo\"}\n"
            }],
            "commit_message": "ga-farc: record repository role receipt",
            "pr_title": "[GA-FARC] Resolve Test-Repo role",
            "pr_body": "Records the bounded role-resolution evidence.",
            "tests_to_run": ["pytest -q"],
            "acceptance_evidence": ["role receipt exists", "repository tests pass"],
            "handoffs": ["HQ-25 independent verification"]
        })


def request_payload(**updates):
    payload = {
        "campaign": "GA-FARC-ESTATE-AGENTIC-BUILD-002",
        "run_id": "ROLE-999-canary",
        "agent_class": "REPOSITORY_AGENT",
        "agent_worker_id": "REPO-AGENT-Test-Repo",
        "agent_profile_repository": "Atlas-Ascend/Test-Repo",
        "agent_profile_path": ".github/agents/repo-custodian.agent.md",
        "source_issue_repository": "Atlas-Ascend/Test-Repo",
        "source_issue_number": 7,
        "target_repository": "Atlas-Ascend/Test-Repo",
        "janus_receipt": "JANUS-CANARY-001",
        "handoff_refs": ["ga-farc-eab002-role-999"],
    }
    payload.update(updates)
    return payload


@pytest.mark.asyncio
async def test_named_agent_loads_profile_issue_repo_truth_and_hands_validated_patch_to_executor():
    github = FakeGitHub()
    model = FakeModel()
    runner = AgentRunner(github, model)
    request = AgentRunRequest.model_validate(request_payload())

    result = await runner.run(request, "exec-key")

    assert result["status"] == "EXECUTED_NOT_VERIFIED"
    assert result["agent_runtime_state"] == "NAMED_AGENT_EXECUTED_NOT_VERIFIED"
    assert result["named_agent"]["lifecycle"] == "ACTIVE"
    assert result["named_agent"]["source_issue_number"] == 7
    assert github.executed is not None
    assert github.executed.repository == "Atlas-Ascend/Test-Repo"
    assert github.executed.files[0].path == "receipts/ga-farc/ROLE-999.json"
    assert "Test Repo Agent" in model.system_prompt
    assert "highest priority" not in model.system_prompt.lower()  # wrapper owns provider-precedence wording
    assert "Read local Build Truth" in model.prompt
    assert "BUILD_TRUTH.md" in model.prompt
    assert "tests/test_app.py" in model.prompt
    assert ".github/agents/" in model.system_prompt


def test_repository_agent_cannot_borrow_another_repo_profile():
    with pytest.raises(ValidationError):
        AgentRunRequest.model_validate(request_payload(agent_profile_repository="Atlas-Ascend/Other-Repo"))


def test_office_agent_must_use_hq_profile_and_issue():
    with pytest.raises(ValidationError):
        AgentRunRequest.model_validate(request_payload(
            agent_class="OFFICE_AGENT",
            agent_profile_repository="Atlas-Ascend/Test-Repo",
            agent_profile_path=".github/agents/hq-25-quality-audit-office.agent.md",
        ))


@pytest.mark.asyncio
async def test_runner_fails_closed_without_model_provider():
    runner = AgentRunner(FakeGitHub(), FakeModel(configured=False))
    with pytest.raises(AgentRunnerConfigError):
        await runner.run(AgentRunRequest.model_validate(request_payload()), "exec-key")


@pytest.mark.asyncio
async def test_runner_rejects_non_json_model_plan():
    runner = AgentRunner(FakeGitHub(), FakeModel(raw="I think you should rewrite everything."))
    with pytest.raises(AgentPlanError):
        await runner.run(AgentRunRequest.model_validate(request_payload()), "exec-key")


@pytest.mark.asyncio
async def test_runner_rejects_plan_target_drift():
    model = FakeModel(raw=json.dumps({
        "lifecycle": "ACTIVE",
        "repository_role": "test role",
        "diagnosis": "test diagnosis",
        "mutation_boundary": "bounded",
        "target_repository": "Atlas-Ascend/Other-Repo",
        "files": [{"path": "receipt.json", "content": "{}\n"}],
        "commit_message": "test commit",
        "pr_title": "test pr",
        "pr_body": "",
        "tests_to_run": ["pytest -q"],
        "acceptance_evidence": ["tests pass"],
        "handoffs": []
    }))
    runner = AgentRunner(FakeGitHub(), model)
    with pytest.raises(AgentPlanError):
        await runner.run(AgentRunRequest.model_validate(request_payload()), "exec-key")
