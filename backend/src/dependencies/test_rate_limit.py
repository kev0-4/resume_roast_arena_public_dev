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


class TestInterviewStartExemption:
    """
    The interview cap is one per week, which makes ADMIN_EMAILS the only
    way to exercise the feature more than once in seven days. Real Redis,
    like the rest of this file -- the point is that an admin account never
    touches a counter at all.
    """

    class _User:
        def __init__(self, uid, email):
            self.id = uid
            self.email = email

    def _run(self, coro):
        import asyncio

        asyncio.run(coro)

    def test_every_admin_email_is_never_limited(self, client):
        # Loops the whole list rather than sampling one, so adding an admin
        # without it actually working cannot pass silently.
        from backend.src.config import ADMIN_EMAILS
        from backend.src.dependencies.rate_limit import check_interview_start_rate_limit

        assert ADMIN_EMAILS, "expected at least one configured admin"

        for i, admin in enumerate(sorted(ADMIN_EMAILS)):
            user = self._User(f"admin-{i}-{time.time()}", admin)

            async def run():
                # Far more than the weekly cap; none of these may raise.
                for _ in range(5):
                    await check_interview_start_rate_limit(user)

            self._run(run())

            # No counter was created, so a stale one can never lock an
            # admin out later.
            assert client.get(f"ratelimit:interview_start:user:{user.id}") is None, admin

    def test_exemption_ignores_case_and_padding(self, client):
        from backend.src.config import ADMIN_EMAILS
        from backend.src.dependencies.rate_limit import check_interview_start_rate_limit

        exempt = next(iter(ADMIN_EMAILS))
        user = self._User(f"exempt-case-{time.time()}", f"  {exempt.upper()}  ")

        async def run():
            await check_interview_start_rate_limit(user)

        self._run(run())
        assert client.get(f"ratelimit:interview_start:user:{user.id}") is None

    def test_ordinary_account_is_capped(self, client):
        from fastapi import HTTPException
        from backend.src.config import INTERVIEW_START_RATE_LIMIT_MAX
        from backend.src.dependencies.rate_limit import check_interview_start_rate_limit

        user = self._User(f"capped-{time.time()}", "someone.else@example.com")

        async def run():
            for _ in range(INTERVIEW_START_RATE_LIMIT_MAX):
                await check_interview_start_rate_limit(user)
            with pytest.raises(HTTPException) as caught:
                await check_interview_start_rate_limit(user)
            assert caught.value.status_code == 429

        self._run(run())
        client.delete(f"ratelimit:interview_start:user:{user.id}")

    def test_user_with_no_email_is_capped_not_exempt(self, client):
        # A null email must never be read as "matches the empty exemption".
        from fastapi import HTTPException
        from backend.src.config import INTERVIEW_START_RATE_LIMIT_MAX
        from backend.src.dependencies.rate_limit import check_interview_start_rate_limit

        user = self._User(f"noemail-{time.time()}", None)

        async def run():
            for _ in range(INTERVIEW_START_RATE_LIMIT_MAX):
                await check_interview_start_rate_limit(user)
            with pytest.raises(HTTPException):
                await check_interview_start_rate_limit(user)

        self._run(run())
        client.delete(f"ratelimit:interview_start:user:{user.id}")
