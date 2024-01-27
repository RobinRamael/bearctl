from unittest.mock import ANY, Mock

import pytest

from bear.battery import BatteryData, BatteryNotificationView, BatteryState
from bear.views import NotificationUrgency


@pytest.fixture
def battery_notification_view():
    return BatteryNotificationView(notifications=Mock(), nag_lobound=10)


def test_notifies_when_discharging_and_low(battery_notification_view):
    battery_notification_view.on_change(BatteryData(9, BatteryState.DISCHARGING))

    battery_notification_view.notifications.notify.assert_called_once()


def test_id_set_when_notified(battery_notification_view):
    battery_notification_view.notifications.notify.return_value = 123

    battery_notification_view.on_change(BatteryData(9, BatteryState.DISCHARGING))

    assert battery_notification_view.notification_id == 123


def test_replace_id(battery_notification_view):
    battery_notification_view.notification_id = 123

    battery_notification_view.on_change(BatteryData(9, BatteryState.DISCHARGING))

    battery_notification_view.notifications.notify.assert_called_once_with(
        ANY, ANY, replace_id=123, urgency=ANY, icon=ANY
    )


def test_does_not_notify_when_discharging_and_high(battery_notification_view):
    battery_notification_view.on_change(BatteryData(11, BatteryState.DISCHARGING))

    battery_notification_view.notifications.notify.assert_not_called()


def test_closes_notification_when_discharging_and_high(battery_notification_view):
    battery_notification_view.notification_id = 123

    battery_notification_view.on_change(BatteryData(11, BatteryState.DISCHARGING))

    battery_notification_view.notifications.close_notification.assert_called_with(123)


def test_closes_notification_when_charging_and_low(battery_notification_view):
    battery_notification_view.notification_id = 123

    battery_notification_view.on_change(BatteryData(9, BatteryState.CHARGING))

    battery_notification_view.notifications.close_notification.assert_called_with(123)
