import datetime
import time

from bear.sjebbestie import format_elapsed, parse_status


def _iso(seconds_ago: int) -> str:
    dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        seconds=seconds_ago
    )
    return dt.isoformat()


# --- format_elapsed ---------------------------------------------------------


def test_format_elapsed_hms():
    assert format_elapsed(time.time() - 3725) == "1:02:05"


def test_format_elapsed_pads_minutes_and_seconds():
    assert format_elapsed(time.time() - 65) == "0:01:05"


def test_format_elapsed_idle_is_blank():
    assert format_elapsed(None) == ""


def test_format_elapsed_negative_is_blank():
    # clock skew / a start in the future shouldn't render a negative time
    assert format_elapsed(time.time() + 120) == ""


# --- parse_status -----------------------------------------------------------


def test_parse_status_running():
    parsed = parse_status(
        {"running": True, "project_name": "Acme", "started_at": _iso(3600)}
    )
    assert parsed["running"] is True
    assert parsed["project"] == "Acme"
    # ~an hour ago, allowing for test runtime
    assert abs((time.time() - parsed["started_at"]) - 3600) < 5


def test_parse_status_idle():
    parsed = parse_status(
        {"running": False, "project_name": None, "started_at": None}
    )
    assert parsed == {"running": False, "project": "", "started_at": None}


def test_parse_status_tolerates_missing_keys():
    assert parse_status({}) == {"running": False, "project": "", "started_at": None}


def test_parse_status_bad_timestamp_falls_back_to_idle():
    parsed = parse_status(
        {"running": True, "project_name": "Acme", "started_at": "not-a-date"}
    )
    assert parsed["running"] is False
    assert parsed["started_at"] is None
