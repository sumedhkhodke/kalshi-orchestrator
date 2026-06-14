# tests/test_timeutil.py
from kalshi_console.app import timeutil


def test_now_ms_is_int_and_plausible():
    ms = timeutil.now_ms()
    assert isinstance(ms, int)
    # after 2025-01-01 and before 2100-01-01, in milliseconds
    assert 1_735_689_600_000 < ms < 4_102_444_800_000


def test_now_s_is_int_and_plausible():
    s = timeutil.now_s()
    assert isinstance(s, int)
    assert 1_735_689_600 < s < 4_102_444_800


def test_ms_to_s_truncates():
    assert timeutil.ms_to_s(1703123456789) == 1703123456


def test_now_ms_roughly_thousand_times_now_s():
    s = timeutil.now_s()
    ms = timeutil.now_ms()
    assert abs(ms - s * 1000) < 2000
