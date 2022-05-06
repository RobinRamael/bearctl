from functools import wraps

import pydbus
from gi.repository import GLib

from bear import ServiceBear
from i3status import I3StatusBlock
from systemd import ServiceCtl, SystemdManager


def main():
    bus = pydbus.SessionBus()
    systemd_manager = SystemdManager(bus=bus)

    loop = GLib.MainLoop()

    redshift_bear = ServiceBear(
        name="redshift",
        servicectl=ServiceCtl(service_name="redshift.service", systemd=systemd_manager),
        i3status=I3StatusBlock(block_name="RedshiftService"),
    )


    print(redshift_bear.dbus)
    # pprint(getattr(redshift_bear, "dbus").decode())

    redshift_bear.register(bus)
    redshift_bear.start_updating()

    loop.run()


main()
