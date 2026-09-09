from vulcan.engine import VulcanEngine

def test_tournament_repairs_and_promotes_only_verified():
    t,r=VulcanEngine().run()
    assert r["verification"]=="PASS"
    assert r["unverified_promotions"]==0
    assert r["repair_revisions"]>=1
    winner=next(c for c in t.candidates if c.id==t.winner_id)
    assert winner.verified and winner.promoted
    assert all(x.passed for x in winner.tests)

def test_initial_direct_candidate_exposes_zero_division():
    e=VulcanEngine();t=e.create();c=t.candidates[0];e.evaluate(t,c)
    assert not c.verified
    assert any(x.name=="zero-count" and not x.passed for x in c.tests)
