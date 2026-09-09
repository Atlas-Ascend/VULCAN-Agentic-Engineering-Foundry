from __future__ import annotations
from uuid import uuid4
from .models import Candidate,TestResult,Tournament

CASES=[("normal",(10.0,2),5.0),("fraction",(7.0,2),3.5),("zero-count",(8.0,0),0.0),("zero-total",(0.0,4),0.0)]

def impl(candidate:Candidate,total:float,count:int)->float:
    s=candidate.strategy
    if s=="direct": return total/count
    if s=="guarded": return 0.0 if count==0 else total/count
    if s=="overfit": return 0.0 if total==0 else (0.0 if count<=0 else round(total/count,2))
    raise ValueError(s)

class VulcanEngine:
    def create(self):
        t=Tournament(run_id=f"forge_{uuid4().hex[:10]}",objective="Implement safe_ratio(total, count) with zero-count safety and numeric correctness.",candidates=[
            Candidate(id="candidate-a",lineage="forge-a",strategy="direct",risk=6),
            Candidate(id="candidate-b",lineage="forge-b",strategy="guarded",risk=2),
            Candidate(id="candidate-c",lineage="forge-c",strategy="overfit",risk=4),
        ]);t.event("TOURNAMENT_CREATED",candidates=3);return t
    def evaluate(self,t: Tournament,c:Candidate):
        c.tests=[]
        for name,args,expected in CASES:
            try: actual=impl(c,*args);passed=abs(actual-expected)<1e-9
            except Exception as exc: actual=type(exc).__name__;passed=False
            c.tests.append(TestResult(name=name,passed=passed,expected=expected,actual=actual))
        passed=sum(x.passed for x in c.tests);c.score=round((passed/len(CASES))*100-c.risk*2-c.revision,2);c.verified=passed==len(CASES)
        t.event("CANDIDATE_EVALUATED",candidate=c.id,score=c.score,passed=passed,total=len(CASES),verified=c.verified)
    def repair(self,t:Tournament,c:Candidate):
        if c.verified:return
        if c.strategy=="direct":c.strategy="guarded";c.revision+=1;c.lineage=f"{c.lineage}-r{c.revision}";t.event("REPAIR_APPLIED",candidate=c.id,revision=c.revision,reason="zero-count failure");self.evaluate(t,c)
    def run(self):
        t=self.create()
        for c in t.candidates:self.evaluate(t,c)
        for c in t.candidates:
            if not c.verified:self.repair(t,c)
        eligible=[c for c in t.candidates if c.verified]
        winner=max(eligible,key=lambda c:(c.score,-c.risk,-c.revision));winner.promoted=True;t.winner_id=winner.id;t.event("PROMOTION_VERIFIED",winner=winner.id,score=winner.score)
        return t,t.receipt()
