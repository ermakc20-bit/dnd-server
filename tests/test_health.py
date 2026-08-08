from app.config import Settings, get_settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_liveness_is_public(client: TestClient) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "environment": "test",
        "missing_configuration": [],
    }


def test_readiness_is_lenient_locally(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_blocks_unconfigured_production() -> None:
    settings = Settings(environment="production")
    application = create_app(settings)
    application.dependency_overrides[get_settings] = lambda: settings

    with TestClient(application) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert set(response.json()["missing_configuration"]) == {
        "supabase_url",
        "supabase_publishable_key",
        "supabase_service_role_key",
        "database_url",
        "redis_url",
    }
