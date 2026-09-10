from importlib.resources import files
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .engine import VulcanEngine
from .nebius_adapter import NebiusAdapter
from .prompt_os_adapter import compile_prompt, status as prompt_os_status

app=FastAPI(title="VULCAN Agentic Engineering Foundry",version="0.2.0")
engine=VulcanEngine()
nebius=NebiusAdapter()
_self_test_packet=compile_prompt({"objective":"runtime-startup-self-check","prompt_id":"software.self-build","proof_class":"P8"})
print(f"PROMPT_OS_RUNTIME_SELF_CHECK=PASS packet_hash={_self_test_packet['packet_hash']} version={_self_test_packet['version']}")

@app.get("/",response_class=HTMLResponse)
def home():
    return files("vulcan").joinpath("static/index.html").read_text()

@app.get("/health")
def health():
    return {"status":"ok","service":"VULCAN","nebius_configured":nebius.configured(),"prompt_os":"mounted"}

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
