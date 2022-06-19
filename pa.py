import os

import dbus
import gobject
from dbus.mainloop.glib import DBusGMainLoop


def pulse_bus_address():
    if "PULSE_DBUS_SERVER" in os.environ:
        address = os.environ["PULSE_DBUS_SERVER"]
    else:
        bus = dbus.SessionBus()
        server_lookup = bus.get_object(
            "org.PulseAudio1", "/org/pulseaudio/server_lookup1"
        )
        address = server_lookup.Get(
            "org.PulseAudio.ServerLookup1",
            "Address",
            dbus_interface="org.freedesktop.DBus.Properties",
        )
        print(address)

    return address


# convert byte array to string
def dbus2str(db):
    if type(db) == dbus.Struct:
        return str(tuple(dbus2str(i) for i in db))
    if type(db) == dbus.Array:
        return "".join([dbus2str(i) for i in db])
    if type(db) == dbus.Dictionary:
        return dict((dbus2str(k), dbus2str(v)) for k, v in db.items())
    if type(db) == dbus.String:
        return db + ""
    if type(db) == dbus.UInt32:
        return str(db + 0)
    if type(db) == dbus.Byte:
        return chr(db)
    if type(db) == dbus.Boolean:
        return db == True
    if type(db) == dict:
        return dict((dbus2str(k), dbus2str(v)) for k, v in db.items())
    return "(%s:%s)" % (type(db), db)


def sig_handler(state):
    print("State changed to %s" % state)
    if state == 0:
        print("Pulseaudio running.")
    elif state == 1:
        print("Pulseaudio idle.")
    elif state == 2:
        print("Pulseaudio suspended")

    dbus_pstreams = (
        dbus.Interface(
            pulse_bus.get_object(object_path=path),
            dbus_interface="org.freedesktop.DBus.Properties",
        )
        for path in pulse_core.Get(
            "org.PulseAudio.Core1",
            "PlaybackStreams",
            dbus_interface="org.freedesktop.DBus.Properties",
        )
    )
    pstreams = {}
    for pstream in dbus_pstreams:
        try:
            pstreams[pstream.Get("org.PulseAudio.Core1.Stream", "Index")] = pstream
        except dbus.exceptions.DBusException:
            pass
    if pstreams:
        for stream in pstreams.keys():
            plist = pstreams[stream].Get("org.PulseAudio.Core1.Stream", "PropertyList")
            appname = dbus2str(plist.get("application.name", None))
            artist = dbus2str(plist.get("media.artist", None))
            title = dbus2str(plist.get("media.title", None))
            name = dbus2str(plist.get("media.name", None))
            print(appname, artist, title, name)


# setup the glib mainloop

DBusGMainLoop(set_as_default=True)

loop = gobject.MainLoop()

pulse_bus = dbus.connection.Connection(pulse_bus_address())
pulse_core = pulse_bus.get_object(object_path="/org/pulseaudio/core1")
# pulse_clients = pulse_bus.get_object(object_path='/org/pulseaudio/core1/Clients')
# print dir(pulse_clients)
pulse_core.ListenForSignal(
    "org.PulseAudio.Core1.Device.StateUpdated",
    dbus.Array(signature="o"),
    dbus_interface="org.PulseAudio.Core1",
)

pulse_bus.add_signal_receiver(sig_handler, "StateUpdated")
loop.run()
