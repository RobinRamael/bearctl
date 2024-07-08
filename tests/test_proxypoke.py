from contextlib import contextmanager
import sys
from threading import Event, Thread
import traceback
from unittest.mock import Mock

from dasbus.connection import SessionMessageBus
from dasbus.server.interface import dbus_interface, dbus_signal
from dasbus.typing import Dict, Int, List, Str, Variant, get_variant
from gi.repository import GLib
import pytest

from bear.poke import ProxyPoke


def test_poke_pokes_handlers(mocker):
    handler = Mock()
    poke = ProxyPoke()

    poke.add_handler(handler)

    mocker.patch("bear.poke.GLib.idle_add", new=lambda f, *x, **y: f())
    poke.registered = True

    poke.poke()

    handler.assert_called_once_with()


@contextmanager
def catch_errors():
    """Catch exceptions raised in this context.

    :return: a list of exceptions
    """
    errors = []

    def _handle_error(*exc_info):
        errors.append(exc_info)
        sys.__excepthook__(*exc_info)

    try:
        sys.excepthook = _handle_error
        yield errors
    finally:
        sys.excepthook = sys.__excepthook__


class MainLoopThread(Thread):
    def __init__(self, timeout: float = 3):
        super().__init__()
        self.errors = []
        self.loop = GLib.MainLoop()
        self.timeout = timeout

    def start(self) -> None:
        GLib.timeout_add(self.timeout * 1000, self.kill_loop)
        return super().start()

    def run(self):
        with catch_errors() as errors:
            self.loop.run()
        self.errors = errors

    def kill_loop(self):
        self.loop.quit()
        return False


def create_client(task, start_event, end_event):
    def f():
        if start_event:
            start_event.wait()

        task()

        if end_event:
            end_event.set()

    return f


def run_test(*tasks, timeout: float = 3):
    """Run a test."""

    events = [None] + [Event() for i in range(len(tasks) - 1)] + [None]

    clients = []
    for task, start, end in zip(tasks, events[:-1], events[1:]):
        clients.append(Thread(target=create_client(task, start, end)))

    loop_thread = MainLoopThread(timeout=timeout)
    loop_thread.start()

    for client in clients:
        client.start()

    for client in clients:
        client.join()

    loop_thread.join()

    assert not loop_thread.errors, "The loop has failed!"

    assert not loop_thread.loop.get_context().pending()


@dbus_interface("my.testing.Example")
class ExampleInterface(object):
    def __init__(self, init_value=0):
        self._knocked = False
        self._names = []
        self._values = [init_value]
        self._secrets = []

    @property
    def Value(self) -> Int:
        return self._values[-1]

    @Value.setter
    def Value(self, value: Int):
        self._values.append(value)
        self.PropertiesChanged(
            "my.testing.Example", {"Value": get_variant(Int, value)}, []
        )

    @dbus_signal
    def PropertiesChanged(
        self, interface: Str, changed: Dict[Str, Variant], invalid: List[Str]
    ):
        pass


@pytest.fixture
def bus():
    return SessionMessageBus()


def test_proxy_poke(bus, mocker):
    obj_path = "/my/testing/Example"
    service_name = "my.testing.Example"

    mocker.patch("bear.poke.GLib.idle_add", new=lambda f, *x, **y: f())
    obj = ExampleInterface()
    bus.publish_object(obj_path, obj)
    bus.register_service(service_name)

    poke = ProxyPoke(
        service_name=service_name,
        obj_path=obj_path,
        interface_name="my.testing.Example",
        property_names=["value"],
    )
    handler = Mock()

    poke.add_handler(handler)

    def t1():
        poke.register()

    def t2():
        obj.Value = 3

    run_test(t1, t2, timeout=0.5)

    handler.assert_called_once_with()
    assert poke.current_data == {"value": 3}
