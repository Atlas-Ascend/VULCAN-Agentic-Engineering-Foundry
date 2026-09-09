from __future__ import annotations
import os
import httpx

class NebiusAdapter:
    """Optional sponsor-generation adapter. Not used or claimed in deterministic judge mode."""
    def configured(self)->bool:return bool(os.getenv("NEBIUS_API_KEY") and os.getenv("NEBIUS_MODEL"))
    async def generate_candidate(self,prompt:str)->str:
        key=os.getenv("NEBIUS_API_KEY");model=os.getenv("NEBIUS_MODEL")
        if not key or not model:raise RuntimeError("NEBIUS_API_KEY and NEBIUS_MODEL required")
        base=os.getenv("NEBIUS_BASE_URL","https://api.studio.nebius.ai/v1")
        async with httpx.AsyncClient(timeout=60) as c:
            r=await c.post(f"{base}/chat/completions",headers={"Authorization":f"Bearer {key}"},json={"model":model,"messages":[{"role":"user","content":prompt}],"temperature":0.2})
            r.raise_for_status();return r.json()["choices"][0]["message"]["content"]
