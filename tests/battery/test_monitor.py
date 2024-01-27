from unittest.mock import ANY, Mock, patch

import pytest

from bear.battery import BatteryData, BatteryMonitor, BatteryState
from bear.views import BlockState


@pytest.fixture
def monitor():
    return BatteryMonitor(view=Mock(), bounds=(10, 30, 100))


def test_state_error(monitor):
    monitor.on_change(BatteryData(9, BatteryState.DISCHARGING))

    monitor.view.update.assert_called_once_with(ANY, state=BlockState.error, icon=ANY)


def test_state_warning(monitor):
    monitor.on_change(BatteryData(11, BatteryState.DISCHARGING))

    monitor.view.update.assert_called_once_with(ANY, state=BlockState.warning, icon=ANY)


def test_state_good(monitor):
    monitor.on_change(BatteryData(31, BatteryState.DISCHARGING))

    monitor.view.update.assert_called_once_with(ANY, state=BlockState.good, icon=ANY)


@pytest.fixture
def monitor_with_charging_icons(monitor, mocker):
    BATTERY_CHARGING_LEVELS = ["c1", "c2", "c3"]

    mocker.patch(
        "bear.icons.Icons.BATTERY_CHARGING_LEVELS", new=BATTERY_CHARGING_LEVELS
    )

    return monitor


def test_state_icons_charging(monitor_with_charging_icons):
    monitor_with_charging_icons.on_change(BatteryData(35, BatteryState.CHARGING))
    monitor_with_charging_icons.view.update.assert_called_once_with(
        ANY, state=ANY, icon="c2"
    )


def test_state_icons_charging_full(monitor_with_charging_icons):
    monitor_with_charging_icons.on_change(BatteryData(100, BatteryState.CHARGING))
    monitor_with_charging_icons.view.update.assert_called_once_with(
        ANY, state=ANY, icon="c3"
    )


def test_state_icons_charging_empty(monitor_with_charging_icons):
    monitor_with_charging_icons.on_change(BatteryData(0, BatteryState.CHARGING))
    monitor_with_charging_icons.view.update.assert_called_once_with(
        ANY, state=ANY, icon="c1"
    )


def test_state_icons_discharging(monitor, mocker):
    BATTERY_LEVELS = ["d1", "d2", "d3", "d4"]

    mocker.patch("bear.icons.Icons.BATTERY_LEVELS", new=BATTERY_LEVELS)

    monitor.on_change(BatteryData(76, BatteryState.DISCHARGING))
    monitor.view.update.assert_called_once_with(ANY, state=ANY, icon="d4")
