import time
import pytest
import redis

from backend.src.dependencies.rate_limit import check_and_increment
from backend.src.config import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

_TEST_KEY_PREFIX = "ratelimit:test:"


@pytest.fixture
def client():
    c = redis.Redis(host=REDIS_HOST, port=int(REDIS_PORT), password=REDIS_PASSWORD, db=0, decode_responses=True)
    yield c
    for key in c.scan_iter(f"{_TEST_KEY_PREFIX}*"):
        c.delete(key)


class TestCheckAndIncrement:
    def test_allows_under_limit(self, client):
        key = f"{_TEST_KEY_PREFIX}under_limit"
        for _ in range(5):
            allowed, retry_after = check_and_increment(client, key, max_requests=5, window_seconds=60)
            assert allowed is True
            assert retry_after == 0

    def test_blocks_at_limit(self, client):
        key = f"{_TEST_KEY_PREFIX}at_limit"
        for _ in range(5):
            check_and_increment(client, key, max_requests=5, window_seconds=60)

        allowed, retry_after = check_and_increment(client, key, max_requests=5, window_seconds=60)
        assert allowed is False
        assert retry_after > 0

    def test_retry_after_within_window(self, client):
        key = f"{_TEST_KEY_PREFIX}retry_after"
        for _ in range(3):
            check_and_increment(client, key, max_requests=2, window_seconds=10)

        allowed, retry_after = check_and_increment(client, key, max_requests=2, window_seconds=10)
        assert allowed is False
        assert 0 < retry_after <= 10

    def test_different_keys_are_independent(self, client):
        key_a = f"{_TEST_KEY_PREFIX}user_a"
        key_b = f"{_TEST_KEY_PREFIX}user_b"
        for _ in range(5):
            check_and_increment(client, key_a, max_requests=5, window_seconds=60)

        allowed_a, _ = check_and_increment(client, key_a, max_requests=5, window_seconds=60)
        allowed_b, _ = check_and_increment(client, key_b, max_requests=5, window_seconds=60)
        assert allowed_a is False
        assert allowed_b is True

    def test_resets_after_window_expires(self, client):
        key = f"{_TEST_KEY_PREFIX}window_reset"
        for _ in range(2):
            check_and_increment(client, key, max_requests=2, window_seconds=1)

        allowed, _ = check_and_increment(client, key, max_requests=2, window_seconds=1)
        assert allowed is False

        time.sleep(1.5)

        allowed, _ = check_and_increment(client, key, max_requests=2, window_seconds=1)
        assert allowed is True
