import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location('codex_usage', Path(__file__).parents[1] / 'codex_usage.py')
usage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(usage)


def test_unknown_is_not_available():
    assert usage.summarize({})['available'] is None
    assert usage.summarize({'rateLimits': {'primary': {'usedPercent': 0}}})['available'] is None


def test_remaining_allowance_does_not_wait_for_next_reset():
    result = usage.summarize({'rateLimits': {'primary': {'usedPercent': 0, 'resetsAt': 9999999999}, 'secondary': {'usedPercent': 50}}})
    assert result == {'available': True, 'reset_at': None}


def test_both_exhausted_windows_require_later_reset():
    result = usage.summarize({'rateLimitsByLimitId': {'codex': {'primary': {'usedPercent': 100, 'resetsAt': 1788756840}, 'secondary': {'usedPercent': 100, 'resetsAt': 1788756900}}}})
    assert result['available'] is False
    assert result['reset_at'].endswith('+00:00')
    assert result['reset_at'] == '2026-09-07T04:55:00+00:00'
