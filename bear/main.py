from functools import wraps

import click
from dasbus.connection import SessionMessageBus, SystemMessageBus
from dasbus.loop import EventLoop
from gi.repository import GLib

from bear.bluetooth import BluetoothBear, DasBusBluetoothDevice
from bear.systemd import (PauseableServiceBear, ServiceBear, ServiceCtl,
                          SystemdManager)
from bear.views import I3StatusBlock, Printer

FOLDER_ICON = "\uf07b"
EYE_ICON = "\uf06e"

import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

logger = logging.getLogger()


def build_bears():
    session_bus = SessionMessageBus()
    system_bus = SystemMessageBus()

    sys_systemd_manager = SystemdManager(bus=system_bus)
    bluetooth_service = ServiceCtl("bluetooth.service", systemd=sys_systemd_manager)

    # boom_mac =  "C0:28:8D:D7:12:87"
    bears = [
        BluetoothBear(
            device=DasBusBluetoothDevice(
                mac_address="38:18:4C:E9:00:D8", bus=system_bus
            ),
            service=bluetooth_service,
            bus=session_bus,
            name="bluephones",
            view=I3StatusBlock(block_name="BluephonesBlock", session_bus=session_bus),
            icon="bluetooth",
        )
        # PauseableServiceBear(
        #     bus=bus,
        #     name="redshift",
        #     servicectl=ServiceCtl(
        #         service_name="redshift.service", systemd=systemd_manager
        #     ),
        #     # i3status=I3StatusBlock(block_name="RedshiftService", session_bus=bus),
        #     view=Printer(),
        #     icon=FOLDER_ICON,
        # ),
        # ServiceBear(
        #     bus=bus,
        #     name="dropbox",
        #     servicectl=ServiceCtl(
        #         service_name="dropbox.service", systemd=systemd_manager
        #     ),
        #     # i3status=I3StatusBlock(block_name="DropboxService", session_bus=bus),
        #     view=Printer(),
        #     icon=FOLDER_ICON,
        # ),
    ]

    return bears


@click.group()
def cli():
    pass


@cli.command()
def service():

    loop = GLib.MainLoop()

    for bear in build_bears():
        bear.register()
        bear.initialize_view()

    logger.info("Running loop")
    loop.run()


@cli.command()
@click.argument("name")
@click.argument("command")
def client(name, command):

    try:
        bear = next(b for b in build_bears() if b.name == name)
    except StopIteration:
        print("who?")
        exit(1)

    client = bear.get_client()

    client.call(command)


def main():
    cli()


if __name__ == "__main__":
    main()
