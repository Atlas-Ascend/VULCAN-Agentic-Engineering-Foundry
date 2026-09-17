import base64
import json

import httpx
import pytest
from pydantic import ValidationError

from vulcan.agent_runner import AgentPlanError, AgentRunRequest, AgentRunner, AgentRunnerConfigError


class FakeGitHub:
    def __init__(self):
        self.executed = None
    def status(self): return {"configured": True}
    def authorize(self, key):
        if key != "exec-key": raise RuntimeError("bad test key")
    async def _request(self, method, path, *, allow=None, params=None, **kwargs):
        def r(status, payload):
            return httpx.Response(status, json=payload, request=httpx.Request(method, f"https://api.github.test{path}"))
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo": return r(200, {"default_branch":"main"})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/issues/7": return r(200, {"title":"[GA-FARC][ROLE-999] Resolve repository role before mutation","body":"Read local Build Truth and create a bounded role receipt.","html_url":"https://github.test/issue/7"})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/.github/agents/repo-custodian.agent.md":
            text="---\nname: Test Repo Agent\n---\nMission: patch only this canonical repo and prove work."
            return r(200,{"type":"file","encoding":"base64","content":base64.b64encode(text.encode()).decode()})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents": return r(200,[{"name":"README.md","path":"README.md","type":"file"},{"name":".ghost-atlas","path":".ghost-atlas","type":"dir"},{"name":"tests","path":"tests","type":"dir"}])
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/.ghost-atlas": return r(200,[{"name":"BUILD_TRUTH.md","path":".ghost-atlas/BUILD_TRUTH.md","type":"file"}])
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/tests": return r(200,[{"name":"test_app.py","path":"tests/test_app.py","type":"file"}])
        if method == "GET" and path in {"/repos/Atlas-Ascend/Test-Repo/contents/.github/workflows","/repos/Atlas-Ascend/Test-Repo/contents/test","/repos/Atlas-Ascend/Test-Repo/contents/src"}: return r(404,{"message":"Not Found"})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/README.md":
            text="# Test Repo\nCanonical purpose: prove named agent execution."
            return r(200,{"type":"file","encoding":"base64","content":base64.b64encode(text.encode()).decode()})
        if method == "GET" and path == "/repos/Atlas-Ascend/Test-Repo/contents/.ghost-atlas/BUILD_TRUTH.md":
            text="Lifecycle: ACTIVE\nOwner: Test Repo\nMutation law: bounded patches only."
            return r(200,{"type":"file","encoding":"base64","content":base64.b64encode(text.encode()).decode()})
        return r(500,{"unexpected":f"{method} {path}","params":params})
    async def execute_patch(self, patch, key):
        self.executed=patch
        return {"status":"EXECUTED_NOT_VERIFIED","repository":patch.repository,"branch":"ga-farc/test/ROLE-999","pull_request_number":9,"pull_request_url":"https://github.test/pr/9","merge_performed":False}


class FakeModel:
    def __init__(self, raw=None, configured=True): self.raw=raw; self._configured=configured; self.system_prompt=None; self.prompt=None
    def configured(self): return self._configured
    async def generate_candidate(self,prompt,system_prompt=None):
        self.prompt=prompt; self.system_prompt=system_prompt
        if self.raw is not None: return self.raw
        return json.dumps({"lifecycle":"ACTIVE","repository_role":"Canonical test repository for named-agent execution proof.","diagnosis":"Role resolution requires an evidence receipt without replacement architecture.","mutation_boundary":"Write only a campaign receipt; do not alter authority or workflow files.","target_repository":"Atlas-Ascend/Test-Repo","files":[{"path":"receipts/ga-farc/ROLE-999.json","content":"{\"lifecycle\":\"ACTIVE\"}\n"}],"commit_message":"ga-farc: record repository role receipt","pr_title":"[GA-FARC] Resolve Test-Repo role","pr_body":"Bounded role-resolution evidence.","tests_to_run":["pytest -q"],"acceptance_evidence":["role receipt exists","repository tests pass"],"handoffs":["HQ-25 independent verification"]})


def payload(**updates):
    base={"campaign":"GA-FARC-ESTATE-AGENTIC-BUILD-002","run_id":"ROLE-999-canary","agent_class":"REPOSITORY_AGENT","agent_worker_id":"REPO-AGENT-Test-Repo","agent_profile_repository":"Atlas-Ascend/Test-Repo","agent_profile_path":".github/agents/repo-custodian.agent.md","source_issue_repository":"Atlas-Ascend/Test-Repo","source_issue_number":7,"target_repository":"Atlas-Ascend/Test-Repo","janus_receipt":"JANUS-CANARY-001","handoff_refs":["ga-farc-eab002-role-999"]}
    base.update(updates); return base


@pytest.mark.asyncio
async def test_named_agent_wake_cycle():
    github=FakeGitHub(); model=FakeModel(); runner=AgentRunner(github,model)
    result=await runner.run(AgentRunRequest.model_validate(payload()),"exec-key")
    assert result["status"]=="EXECUTED_NOT_VERIFIED"
    assert result["agent_runtime_state"]=="NAMED_AGENT_EXECUTED_NOT_VERIFIED"
    assert github.executed.files[0].path=="receipts/ga-farc/ROLE-999.json"
    assert "Test Repo Agent" in model.system_prompt
    assert "profile_path=.github/agents/repo-custodian.agent.md" in model.system_prompt
    assert "Read local Build Truth" in model.prompt
    assert "BUILD_TRUTH.md" in model.prompt
    assert "tests/test_app.py" in model.prompt


def test_repository_agent_cannot_borrow_profile():
    with pytest.raises(ValidationError): AgentRunRequest.model_validate(payload(agent_profile_repository="Atlas-Ascend/Other-Repo"))


def test_office_agent_must_use_hq_profile_and_issue():
    with pytest.raises(ValidationError): AgentRunRequest.model_validate(payload(agent_class="OFFICE_AGENT",agent_profile_repository="Atlas-Ascend/Test-Repo",agent_profile_path=".github/agents/hq-25-quality-audit-office.agent.md"))


@pytest.mark.asyncio
async def test_fail_closed_without_model():
    with pytest.raises(AgentRunnerConfigError): await AgentRunner(FakeGitHub(),FakeModel(configured=False)).run(AgentRunRequest.model_validate(payload()),"exec-key")


@pytest.mark.asyncio
async def test_rejects_non_json_plan():
    with pytest.raises(AgentPlanError): await AgentRunner(FakeGitHub(),FakeModel(raw="rewrite everything")).run(AgentRunRequest.model_validate(payload()),"exec-key")


@pytest.mark.asyncio
async def test_rejects_target_drift():
    raw=json.dumps({"lifecycle":"ACTIVE","repository_role":"test role","diagnosis":"test diagnosis","mutation_boundary":"bounded","target_repository":"Atlas-Ascend/Other-Repo","files":[{"path":"receipt.json","content":"{}\n"}],"commit_message":"test commit","pr_title":"test pr","pr_body":"","tests_to_run":["pytest -q"],"acceptance_evidence":["tests pass"],"handoffs":[]})
    with pytest.raises(AgentPlanError): await AgentRunner(FakeGitHub(),FakeModel(raw=raw)).run(AgentRunRequest.model_validate(payload()),"exec-key")
