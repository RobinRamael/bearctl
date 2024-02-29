from unittest.mock import Mock

from dasbus.typing import Variant

from bear.poke import ProxyPoke
from bear.systemd import GammastepBear, ServiceState, ServiceStates
import pytest


@pytest.fixture
def mocked_gammastepbear(mocker):
    mocker.patch("bear.poke.GLib.idle_add", new=lambda f, *x, **y: f())

    bus_mock = Mock()
    bear = GammastepBear(bus_mock)
    view_mock = Mock()
    bear.views = [view_mock]
    bear.update = Mock()
    proxy_mock = Mock(
        GetAll=Mock(
            return_value={
                "ActiveState": Variant.new_string("inactive"),
                "SubState": Variant.new_string("dead"),
            }
        )
    )
    bear.service.get_proxy = Mock(return_value=proxy_mock)
    bear.service.obj_path = "/some/path"
    return bear


def test_servicebear_change(mocked_gammastepbear):
    bear = mocked_gammastepbear
    bear.register()
    bear.service.on_property_change("", {"ActiveState": "active"})
    bear.update.assert_called_once()

    context = bear.build_context()

    assert context["active_state"] == "active"


def test_servicebear_no_change(mocked_gammastepbear):
    bear = mocked_gammastepbear
    bear.register()
    bear.service.on_property_change("", {"UnknownAttr": 3})
    bear.update.assert_not_called()


def test_servicebear_only_update_on_actual_change(mocked_gammastepbear):
    bear = mocked_gammastepbear
    bear.register()
    bear.service.on_property_change("", {"ActiveState": "active"})
    bear.update.assert_called_once()

    bear.service.on_property_change("", {"ActiveState": "active"})
    bear.update.assert_called_once()

    bear.service.on_property_change("", {"ActiveState": "something_else"})
    assert bear.update.call_count == 2


def test_servicebear_change_active_state_active(mocked_gammastepbear):
    bear = mocked_gammastepbear
    bear.register()
    bear.service.on_property_change(
        "", {"ActiveState": "active", "SubState": "running"}
    )
    bear.update.assert_called_once()

    context = bear.build_context()

    assert context["active_state"] == "active"
    assert context["sub_state"] == "running"
    assert context["state"] == ServiceStates.ENABLED


def test_servicebear_pause(mocked_gammastepbear):
    bear = mocked_gammastepbear
    bear.register()
    bear.service.on_property_change(
        "", {"ActiveState": "active", "SubState": "running"}
    )

    bear.pause(10)
    bear.service.proxy.Stop.assert_called_once()
    assert bear.update.call_count == 2

    bear.service.on_property_change("", {"ActiveState": "inactive", "SubState": "dead"})

    context = bear.build_context()

    assert context["state"] == ServiceStates.PAUSED
