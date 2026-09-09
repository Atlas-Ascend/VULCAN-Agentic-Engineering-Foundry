from importlib.resources import files
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from .engine import VulcanEngine
from .nebius_adapter import NebiusAdapter
app=FastAPI(title="VULCAN Agentic Engineering Foundry",version="0.1.0");engine=VulcanEngine();nebius=NebiusAdapter()
@app.get("/",response_class=HTMLResponse)
def home():return files("vulcan").joinpath("static/index.html").read_text()
@app.get("/health")
def health():return {"status":"ok","service":"VULCAN","nebius_configured":nebius.configured()}
@app.post("/api/tournament")
def tournament():
    t,r=engine.run();return {"tournament":t,"receipt":r,"sponsor_runtime":{"nebius_configured":nebius.configured(),"used_in_this_demo":False}}
