from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.auth.dependencies import get_current_identity
from app.auth.jwt import AuthIdentity
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_me_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_me_reports_missing_auth_configuration(client: TestClient) -> None:
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer opaque-token"},
    )

    assert response.status_code == 503


def test_me_returns_verified_identity() -> None:
    user_id = uuid4()
    identity = AuthIdentity(
        user_id=user_id,
        email="gm@example.com",
        audience="authenticated",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    application = create_app(Settings(environment="test"))
    application.dependency_overrides[get_current_identity] = lambda: identity

    with TestClient(application) as client:
        response = client.get("/api/v1/me")

    assert response.status_code == 200
    assert response.json() == {"user_id": str(user_id), "email": "gm@example.com"}
