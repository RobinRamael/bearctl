import logging
import sys

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


class BluetoothBear(Bear):
    def __init__(self, service, device, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.service = service
        self.device = device

    def register(self):
        super().register()
        self.device.register_listener(self.on_property_change)

    def on_property_change(self, name, changed_props, _):
        logger.info(changed_props)
        try:
            is_connected = changed_props["Connected"]
        except KeyError:
            return

        if is_connected:
            self.view.update("connected", "bt", "Good")
        else:
            self.view.update("disconnected", "bt", "Idle")

    @dbus_method
    def connect(self):
        self.device.connect()

    @dbus_method
    def disconnect(self):
        self.device.disonnect()
