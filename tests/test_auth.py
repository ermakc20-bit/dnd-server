from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.auth.jwt import AuthenticationError, SupabaseJWTVerifier
from cryptography.hazmat.primitives.asymmetric import rsa

ISSUER = "https://project.supabase.co/auth/v1"
AUDIENCE = "authenticated"


@pytest.fixture(scope="module")
def key_pair() -> tuple[object, object]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def make_token(private_key: object, **overrides: object) -> str:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": str(uuid4()),
        "email": "player@example.com",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256")


def verifier(public_key: object) -> SupabaseJWTVerifier:
    return SupabaseJWTVerifier(
        issuer=ISSUER,
        audience=AUDIENCE,
        signing_key_resolver=lambda _token: public_key,
    )


def test_valid_token_establishes_identity(key_pair: tuple[object, object]) -> None:
    private_key, public_key = key_pair
    user_id = uuid4()

    identity = verifier(public_key).verify(make_token(private_key, sub=str(user_id)))

    assert identity.user_id == user_id
    assert identity.email == "player@example.com"
    assert identity.audience == AUDIENCE


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("iss", "https://attacker.invalid/auth/v1"),
        ("aud", "service_role"),
        ("exp", 1),
    ],
)
def test_invalid_claims_are_rejected(
    key_pair: tuple[object, object],
    claim: str,
    value: object,
) -> None:
    private_key, public_key = key_pair

    with pytest.raises(AuthenticationError):
        verifier(public_key).verify(make_token(private_key, **{claim: value}))


def test_wrong_signature_is_rejected(key_pair: tuple[object, object]) -> None:
    private_key, _public_key = key_pair
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    with pytest.raises(AuthenticationError):
        verifier(other_private_key.public_key()).verify(make_token(private_key))
