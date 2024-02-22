from unittest.mock import ANY, Mock

import pytest

from bear.monitor import BearLevel, LoadAverageBear


@pytest.fixture
def load_avg_bear(mocker):
    mocker.patch("os.cpu_count", return_value=4)

    # register fuckery
    if hasattr(LoadAverageBear.metric, "bear"):
        del LoadAverageBear.metric.bear

    bear = LoadAverageBear(session_bus=Mock(), system_bus=Mock())

    bear.levels = (
        2.3,
        4.6,
        6.9,
    )
    return bear


def test_low_avg(load_avg_bear, mocker):
    mocker.patch("os.getloadavg", return_value=(7.5, 1, 1))

    load_avg_bear.metric._do_poll()
    context = load_avg_bear.build_context()

    assert context["state"] == BearLevel.error


def test_warn_avg(load_avg_bear: LoadAverageBear, mocker):
    mocker.patch("os.getloadavg", return_value=(5.5, 1, 1))

    load_avg_bear.metric._do_poll()
    context = load_avg_bear.build_context()

    assert context["state"] == BearLevel.warning
