from app.config.settings import Settings


def test_settings_defaults() -> None:
    """Ensure that default settings are applied correctly.

    This test verifies that the Settings class properly handles explicit configuration
    values and applies the correct defaults for unspecified fields.
    """
    s = Settings(
        db_host="localhost",
        db_user="x",
        db_password="y",
        db_name="z",
        db_url="postgresql+asyncpg://x:y@localhost/z",
    )
    assert s.environment == "test"
    assert "postgresql" in s.db_url
