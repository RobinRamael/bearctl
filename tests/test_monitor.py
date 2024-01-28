from unittest.mock import ANY, Mock

import pytest

from bear.load_average import LoadAverageBear
from bear.views import BlockState


@pytest.fixture
def load_avg_bear(mocker):
    mocker.patch("os.cpu_count", return_value=4)
    return LoadAverageBear(
        name="loadavg",
        bus=Mock(),
        view=Mock(),
        interval=5,
        levels=(0.3, 0.6, 0.9),
        icon=Mock(),
    )


def test_warn_avg(load_avg_bear, mocker):
    mocker.patch("os.getloadavg", return_value=(2.5, 1, 1))

    load_avg_bear.update()

    load_avg_bear.view.update.assert_called_once_with(
        message=ANY,
        state=BlockState.warning,
        icon=ANY,
    )


def test_low_avg(load_avg_bear, mocker):
    mocker.patch("os.getloadavg", return_value=(0.3, 1, 1))

    load_avg_bear.update()

    load_avg_bear.view.update.assert_called_once_with(
        message=ANY,
        state=BlockState.idle,
        icon=ANY,
    )
