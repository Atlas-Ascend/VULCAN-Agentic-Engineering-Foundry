from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from pydantic import BaseModel, Field

class TestResult(BaseModel):
    name:str
    passed:bool
    expected:float
    actual:float | str

class Candidate(BaseModel):
    id:str
    lineage:str
    strategy:str
    revision:int=0
    tests:list[TestResult]=Field(default_factory=list)
    score:float=0.0
    risk:int=0
    verified:bool=False
    promoted:bool=False

class Tournament(BaseModel):
    run_id:str
    objective:str
    candidates:list[Candidate]
    events:list[dict]=Field(default_factory=list)
    winner_id:str|None=None
    def event(self,t:str,**p):self.events.append({"at":datetime.now(timezone.utc).isoformat(),"type":t,**p})
    def receipt(self):
        raw=self.model_dump_json(exclude={"events"})
        winner=next((c for c in self.candidates if c.id==self.winner_id),None)
        return {"run_id":self.run_id,"objective":self.objective,"candidate_count":len(self.candidates),"verified_candidates":sum(c.verified for c in self.candidates),"repair_revisions":sum(c.revision for c in self.candidates),"winner":self.winner_id,"winner_verified":bool(winner and winner.verified),"unverified_promotions":sum(c.promoted and not c.verified for c in self.candidates),"verification":"PASS" if winner and winner.verified else "FAIL","sha256":sha256(raw.encode()).hexdigest()}
