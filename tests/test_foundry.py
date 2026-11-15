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


def test_ga001_metaforge_handoff_contract_preserves_authority_and_proof():
    import json
    from pathlib import Path

    contract = json.loads((Path(__file__).resolve().parents[1] / "SOFTWARE_DESIGN" / "GA001_METAFORGE_HANDOFF_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["canonical_owner"] == "MetaForge"
    assert contract["implementation_repository"] == "Atlas-Ascend/VULCAN-Agentic-Engineering-Foundry"
    assert contract["governance"]["executive_authority"] == "JANUS PRIME"
    assert contract["governance"]["engineering_governance"] == "PROMETHEUS AIS"
    assert contract["governance"]["independent_verification"] == ["SECA", "DEVOS"]
    assert contract["production_deployment_authorized"] is False
    assert "Unverified candidates cannot be promoted." in contract["invariants"]
