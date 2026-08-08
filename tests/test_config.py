from app.config import Settings


def test_service_role_key_is_redacted_in_settings_repr() -> None:
    settings = Settings(supabase_service_role_key="server-secret-value")

    assert "server-secret-value" not in repr(settings)
    assert settings.supabase_service_role_key is not None
    assert settings.supabase_service_role_key.get_secret_value() == "server-secret-value"


def test_empty_secret_is_treated_as_unset() -> None:
    settings = Settings(supabase_service_role_key="")

    assert settings.supabase_service_role_key is None
