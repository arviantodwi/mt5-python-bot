from app.bot import healthcheck


def test_healthcheck():
    """Tests the healthcheck function."""
    assert healthcheck() == "Bot is healthy!"
