from functools import wraps

from dasbus.connection import SessionMessageBus
from dasbus.loop import EventLoop

from bear import ServiceBear
from i3status import I3StatusBlock
from systemd import ServiceCtl, SystemdManager


def main():
    bus = SessionMessageBus()
    systemd_manager = SystemdManager(bus=bus)

    loop = EventLoop()

    redshift_bear = ServiceBear(
        name="redshift",
        servicectl=ServiceCtl(service_name="redshift.service", systemd=systemd_manager),
        i3status=I3StatusBlock(block_name="RedshiftService"),
    )

    redshift_bear.register(bus)


    loop.run()


if __name__ == "__main__":
    main()
