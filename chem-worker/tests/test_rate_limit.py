import time

from mapper.llm import RateLimiter


def test_rate_limiter_caps_calls_per_window():
    limiter = RateLimiter(max_calls=2, period_s=0.4)
    t0 = time.monotonic()
    limiter.wait()
    limiter.wait()
    limiter.wait()
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.35
