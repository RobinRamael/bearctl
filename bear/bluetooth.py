import logging
import multiprocessing
import queue
import sys
import threading

from dasbus.connection import AddressedMessageBus
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

    def _as_object_name(self, mac_address: str):
        return f"/org/bluez/hci0/dev_{mac_address.replace(':', '_')}"

    @property
    def sink_name(self):
        return f"bluez_sink.{self.mac_address.replace(':', '_')}.a2dp_sink"

    def get_info(self):
        return dict(self.device.GetAll(DEVICE_INTERFACE))

    def connect(self):
        self.device.Connect()

    def connect_audio(self):
        self.connect()

    def disconnect(self):
        self.device.Disconnect()

    def register_listener(self, listener):
        self.device.PropertiesChanged.connect(listener)


class NoSinkAdded(Exception):
    pass


class PulseThread(threading.Thread):
    def __init__(self, new_queue, remove_queue):
        threading.Thread.__init__(self)
        self.new_queue = new_queue
        self.remove_queue = remove_queue

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

        self.new_sinks_queue = multiprocessing.Queue()
        self.remove_sinks_queue = multiprocessing.Queue()
        self.pulse_thread = PulseThread(self.new_sinks_queue, self.remove_sinks_queue)

        self._sink_index = None

        self.pulse = Pulse("bear")

    def on_new_sink_event(self, fd, condition):
        try:
            new_event = self.new_sinks_queue.get_nowait()
        except queue.Empty:
            return True
        else:
            logger.info(f"A sink with index {new_event.index} was added")

            new_sink = self.pulse.sink_info(new_event.index)
            if new_sink.name == self.device.sink_name:
                logger.info(f"The sink for this device was added!")
                self._sink_index = new_sink.index

                self.view.update("connected", "headphones", "Good")

        finally:
            # we return true to indicate to glib that this callback has to be called
            # again.
            return True

    def on_removed_sink_event(self, fd, condition):
        try:
            removed_event = self.remove_sinks_queue.get_nowait()
        except queue.Empty:
            return True
        else:
            logger.info(f"A sink with index {removed_event.index} was removed")

            if removed_event.index == self._sink_index and self._sink_index is not None:
                logger.info("The sink for this device was removed!")
                self._sink_index = None
                self.view.update("connected", "bluetooth", "Warning")
        finally:
            # we return true to indicate to glib that this callback has to be called
            # again.
            return True

    def register(self):
        super().register()
        self.device.register_listener(self.on_bluetooth_property_change)

        self.pulse_thread.daemon = True
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
            self.on_new_sink_event,
        )

        GObject.io_add_watch(
            self.remove_sinks_queue._reader,
            GObject.IO_IN | GObject.IO_PRI,
            self.on_removed_sink_event,
        )

    def on_bluetooth_property_change(self, name, changed_props, _):
        try:
            is_connected = changed_props["Connected"]
        except KeyError:
            return

        if is_connected:
            self.view.update("connected", "bluetooth", "Warning")
        else:
            self.view.update("", "bluetooth", "Idle")

    @dbus_method
    def connect(self):
        self.view.update("...", "bluetooth", "Warning")
        self.device.connect()

    @dbus_method
    def disconnect(self):
        self.view.update("...", "bluetooth", "Warning")
        self.device.disconnect()
