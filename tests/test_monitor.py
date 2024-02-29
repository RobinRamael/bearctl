from unittest.mock import ANY, Mock
from unittest.mock import Mock
from unittest.mock import patch

from bear.monitor import BearLevel, LoadAverageBear
from bear.monitor import CPUBear, LoadAverageBear, MemoryBear
import pytest


@pytest.fixture
def mocks(mocker):
    run_sync = mocker.patch("bear.poke.GLib.idle_add", new=lambda f, *x, **y: f())

    mock_eww = mocker.patch("bear.eww.EwwController")


@pytest.fixture
def load_avg_bear(mocker):
    mocker.patch("os.cpu_count", return_value=4)

    # register fuckery
    if hasattr(LoadAverageBear.metric, "bear"):
        del LoadAverageBear.metric.bear

    bear = LoadAverageBear(session_bus=Mock())

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


def test_cpubear(mocks):
    bus = Mock()
    bear = CPUBear(bus)
    bear.views = [Mock()]

    bear.register()
    bear.metric.poll()
    bear.update()


def test_load_avg_bear(mocks):
    bus = Mock()
    bear = LoadAverageBear(bus)
    bear.views = [Mock()]

    bear.register()
    bear.metric.poll()
    bear.update()


def test_memorybear(mocks):
    bus = Mock()
    bear = MemoryBear(bus)
    bear.views = [Mock()]

    bear.register()
    bear.metric.poll()
    bear.update()
