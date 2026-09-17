from __future__ import annotations

from fastapi import Header, HTTPException

from .agent_runner import AgentPlanError, AgentRunRequest, AgentRunner, AgentRunnerConfigError
from .app import app, github_executor, nebius
from .github_executor import ExecutorAuthorizationError, ExecutorConfigError, GitHubExecutionError
from .named_agent_model import NamedAgentNebiusAdapter

named_agent_runner = AgentRunner(github_executor, NamedAgentNebiusAdapter(nebius))


@app.get("/autobuilder/agent-health")
def autobuilder_agent_health():
    state = named_agent_runner.status()
    return {
        "status": "READY" if state["ready"] else "READY_FAIL_CLOSED",
        **state,
        "authority": "JANUS",
        "mutation_contract": "PR_ONLY_NO_MERGE",
        "verification_required": ["SECA", "DevOS", "HQ-25"],
        "proof_required": "ProofGrid -> Thoth",
    }


@app.post("/autobuilder/v1/agents/run")
async def autobuilder_named_agent_run(
    payload: AgentRunRequest,
    execution_key: str | None = Header(default=None, alias="X-Ghost-Atlas-Execution-Key"),
):
    try:
        return await named_agent_runner.run(payload, execution_key)
    except ExecutorAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (ExecutorConfigError, AgentRunnerConfigError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AgentPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (GitHubExecutionError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
