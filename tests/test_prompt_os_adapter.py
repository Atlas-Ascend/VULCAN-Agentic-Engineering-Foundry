from vulcan.prompt_os_adapter import compile_prompt, status


def test_prompt_os_self_build_contract():
    packet = compile_prompt({"objective":"self-build canary","prompt_id":"software.self-build","proof_class":"P8"})
    assert packet["prompt_id"] == "software.self-build"
    assert packet["proof_class"] == "P8"
    assert packet["verification"]["independent"] is True
    assert "self_authorize" in packet["forbidden_capabilities"]
    assert "self_verify" in packet["forbidden_capabilities"]
    assert len(packet["packet_hash"]) == 64


def test_prompt_os_runtime_status():
    snapshot = status()
    assert snapshot["status"] == "PASS"
    assert snapshot["service"] == "ghost-atlas-prompt-os"
    assert snapshot["deployment_provider"] == "Render"
