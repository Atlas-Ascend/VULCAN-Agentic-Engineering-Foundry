from vulcan.app import app


def test_named_agent_routes_registered_on_canonical_app():
    paths = {route.path for route in app.routes}
    assert "/autobuilder/agent-health" in paths
    assert "/autobuilder/v1/agents/run" in paths
    assert "/autobuilder/health" in paths
    assert "/autobuilder/v1/repository/patch" in paths
