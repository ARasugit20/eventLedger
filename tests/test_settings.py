def test_settings_use_testcontainer_urls(redis_url, postgres_url):
    from app.config import settings

    assert settings.redis_url == redis_url
    assert settings.database_url == postgres_url
