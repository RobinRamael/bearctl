import logging
import multiprocessing
import queue
import sys
import threading

from dasbus.connection import AddressedMessageBus
from dasbus.error import DBusError
from gi.repository import GObject
from pulsectl import Pulse, PulseLoopStop
from pulsectl.pulsectl import PulseEventMaskEnum, PulseEventTypeEnum

from bear.bear import Bear, dbus_method

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

logger = logging.getLogger()


DEVICE_INTERFACE = "org.bluez.Device1"
PROPERTIES_INTERFACE = "org.freedesktop.DBus.Properties"
BLUEZ_DBUS_NAME = "org.bluez"


class DasBusBluetoothDevice:
    def __init__(self, mac_address, bus):
        self.bus = bus
        self.mac_address = mac_address
        self.device = self.bus.get_proxy(
            BLUEZ_DBUS_NAME, self._as_object_name(mac_address)
        )

        self.new_sinks_queue = multiprocessing.Queue()
        self.remove_sinks_queue = multiprocessing.Queue()
        self.pulse_thread = PulseThread(self.new_sinks_queue, self.remove_sinks_queue)

        self._sink_index = None

        self.pulse = Pulse("bear")

        self.new_sink_listeners = []
        self.removed_sink_listeners = []

    def _as_object_name(self, mac_address: str):
        return f"/org/bluez/hci0/dev_{mac_address.replace(':', '_')}"

    @property
    def sink_name(self):
        return f"bluez_sink.{self.mac_address.replace(':', '_')}.a2dp_sink"

    def get_info(self):
        return dict(self.device.GetAll(DEVICE_INTERFACE))

    @property
    def alias(self):
        return self.device.Get(DEVICE_INTERFACE, "Alias").get_string()

    def check_connection(self):
        return self.device.Get(DEVICE_INTERFACE, "Connected").get_boolean()

    def check_sink(self):
        return any(sink.name == self.sink_name for sink in self.pulse.sink_list())

    def connect(self):
        self.device.Connect()

    def connect_audio(self):
        self.connect()

    def disconnect(self):
        self.device.Disconnect()

    def register_property_listener(self, listener):
        self.device.PropertiesChanged.connect(listener)

    def _on_new_sink_event(self, *args):
        try:
            new_event = self.new_sinks_queue.get_nowait()
        except queue.Empty:
            return True
        else:
            logger.info(f"A sink with index {new_event.index} was added")

            new_sink = self.pulse.sink_info(new_event.index)
            if new_sink.name == self.sink_name:
                self._sink_index = new_sink.index
                logger.info(f"The sink for device {self.mac_address} was added!")
                for listener in self.new_sink_listeners:
                    listener(new_sink)

        # we return true to indicate to glib that this callback has to be called
        # again.
        return True

    def _on_removed_sink_event(self, *args):
        try:
            removed_event = self.remove_sinks_queue.get_nowait()
        except queue.Empty:
            return True
        else:
            logger.info(f"A sink with index {removed_event.index} was removed")

            if removed_event.index == self._sink_index and self._sink_index is not None:
                self._sink_index = None

                logger.info(f"The sink for device {self.mac_address} was removed!")

                for listener in self.removed_sink_listeners:
                    listener()

        # we return true to indicate to glib that this callback has to be called
        # again.
        return True

    def register_new_sink_listener(self, listener):
        self.pulse_thread.start()

        # this is some magic to integrate pulseaudio's event stuff with glib.
        # Whenever there's new data in the queue (put there by the above started
        # thread) the on_<new|removed>_sink_event handler is called in the glib
        # main loop.
        # see
        # https://github.com/mk-fg/python-pulse-control/issues/11#issuecomment-261543399
        # using multiprocessing.Queue is probably notthe most efficient approach
        # but it works so hey
        GObject.io_add_watch(
            self.new_sinks_queue._reader,
            GObject.IO_IN | GObject.IO_PRI,
            self._on_new_sink_event,
        )
        self.pulse_thread.ensure_started()

        self.new_sink_listeners.append(listener)

    def register_removed_sink_listener(self, listener):

        GObject.io_add_watch(
            self.remove_sinks_queue._reader,
            GObject.IO_IN | GObject.IO_PRI,
            self._on_removed_sink_event,
        )

        self.pulse_thread.ensure_started()
        self.removed_sink_listeners.append(listener)


class NoSinkAdded(Exception):
    pass


class PulseThread(threading.Thread):
    def __init__(self, new_queue, remove_queue):
        threading.Thread.__init__(self)
        self.new_queue = new_queue
        self.remove_queue = remove_queue
        self.daemon = True

    def ensure_started(self):
        if not self.is_alive():
            self.start()

    def on_event(self, event):
        logger.debug(f"PulseAudio event rcvd: {event}")
        if event.t == PulseEventTypeEnum.new:
            self.new_queue.put(event)
        elif event.t == PulseEventTypeEnum.remove:
            self.remove_queue.put(event)

    def run(self):
        pulse = Pulse("bear-sink-listener")
        pulse.event_mask_set(PulseEventMaskEnum.sink)
        pulse.event_callback_set(self.on_event)
        pulse.event_listen()


class BluetoothBear(Bear):
    def __init__(self, service, device, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.service = service
        self.device = device

        self.bluetooth_connected = False
        self.sink_added = False

    def register(self):
        super().register()
        self.device.register_property_listener(self.on_bluetooth_property_change)
        self.device.register_new_sink_listener(self.on_new_sink_event)
        self.device.register_removed_sink_listener(self.on_removed_sink_event)

    def show_fully_connected(self):
        self.view.update(self.device.alias, "headphones", "Good")

    def show_half_connected(self):
        self.view.update(self.device.alias, "bluetooth", "Warning")

    def show_disconnected(self):
        self.view.update("", "bluetooth", "Idle")

    def on_new_sink_event(self, _):
        self.sink_added = True
        self.show_fully_connected()

    def on_removed_sink_event(self):
        self.sink_added = False
        if self.bluetooth_connected:
            self.show_half_connected()

    def on_bluetooth_property_change(self, name, changed_props, _):
        try:
            is_connected = changed_props["Connected"]
            logger.info(f"Connected changed to {is_connected}")
        except KeyError:
            return

        if is_connected:
            self.bluetooth_connected = True
            if self.sink_added:
                self.show_fully_connected()
            else:
                self.show_half_connected()

        else:
            self.bluetooth_connected = False
            self.show_disconnected()

    def initialize_view(self):
        if self.device.check_connection():
            self.bluetooth_connected = True
            if self.device.check_sink():
                self.sink_added = True
                self.show_fully_connected()
            else:
                self.show_half_connected()
        else:
            self.show_disconnected()

    @dbus_method
    def connect(self):
        self.view.update("...", "bluetooth", "Warning")
        try:
            self.device.connect()
        except DBusError as e:
            logger.exception(e)
            self.view.update("err", "bluetooth", "Error")

    @dbus_method
    def disconnect(self):
        self.view.update("...", "bluetooth", "Warning")
        self.device.disconnect()
