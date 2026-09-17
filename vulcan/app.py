from importlib.resources import files

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse

from .engine import VulcanEngine
from .github_executor import (
    ExecutorAuthorizationError,
    ExecutorConfigError,
    GitHubExecutionError,
    GitHubExecutor,
    RepositoryPatchRequest,
)
from .nebius_adapter import NebiusAdapter
from .prompt_os_adapter import compile_prompt, status as prompt_os_status

app=FastAPI(title="VULCAN Agentic Engineering Foundry",version="0.3.0")
engine=VulcanEngine()
nebius=NebiusAdapter()
github_executor=GitHubExecutor()
_self_test_packet=compile_prompt({"objective":"runtime-startup-self-check","prompt_id":"software.self-build","proof_class":"P8"})
print(f"PROMPT_OS_RUNTIME_SELF_CHECK=PASS packet_hash={_self_test_packet['packet_hash']} version={_self_test_packet['version']}")
_executor_status=github_executor.status()
print(
    "AUTOBUILDER_GITHUB_EXECUTOR=READY "
    f"configured={_executor_status['configured']} "
    f"github_token_configured={_executor_status['github_token_configured']} "
    f"execution_key_configured={_executor_status['execution_key_configured']} "
    f"nebius_configured={nebius.configured()} mode={_executor_status['mode']}"
)

@app.get("/",response_class=HTMLResponse)
def home():
    return files("vulcan").joinpath("static/index.html").read_text()

@app.get("/health")
def health():
    return {
        "status":"ok",
        "service":"VULCAN",
        "nebius_configured":nebius.configured(),
        "prompt_os":"mounted",
        "autobuilder":github_executor.status(),
    }

@app.post("/api/tournament")
def tournament():
    t,r=engine.run()
    return {"tournament":t,"receipt":r,"sponsor_runtime":{"nebius_configured":nebius.configured(),"used_in_this_demo":False}}

@app.get("/prompt-os/health")
def prompt_os_health():
    return prompt_os_status()

@app.post("/prompt-os/v1/prompts/compile")
def prompt_os_compile(payload: dict | None = None):
    return {"status":"COMPILED","packet":compile_prompt(payload)}

@app.get("/autobuilder/health")
def autobuilder_health():
    return {
        "status":"READY_FAIL_CLOSED" if not github_executor.status()["configured"] else "READY",
        "campaign":"GA-FARC-ESTATE-AGENTIC-BUILD-002",
        "github_executor":github_executor.status(),
        "model_provider_configured":nebius.configured(),
        "contract":"PR_ONLY_NO_MERGE",
        "verification_required":["SECA","DevOS","HQ-25"],
        "proof_required":"ProofGrid -> Thoth",
    }

@app.post("/autobuilder/v1/repository/patch")
async def autobuilder_repository_patch(
    payload: RepositoryPatchRequest,
    execution_key: str | None = Header(default=None, alias="X-Ghost-Atlas-Execution-Key"),
):
    try:
        return await github_executor.execute_patch(payload, execution_key)
    except ExecutorConfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ExecutorAuthorizationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (GitHubExecutionError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
