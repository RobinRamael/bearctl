import logging
import os
import sys
from functools import wraps

import click
from dasbus.connection import SessionMessageBus, SystemMessageBus
from dasbus.loop import EventLoop
from gi.repository import GLib

from bear.battery import Battery, BatteryBear
from bear.bluetooth import BluetoothBear, BluezAdapter, DasBusBluetoothDevice
from bear.dpms import DPMSBear
from bear.icons import Icons
from bear.lorri import LorriBear
from bear.systemd import (PauseableServiceLabelBear, ServiceCtl,
                          ServiceLabelBear, SystemdManager)
from bear.views import I3StatusBlock, NotificationCtl

logging.basicConfig(stream=sys.stdout, level=logging.INFO)


logger = logging.getLogger()


def build_bears():
    session_bus = SessionMessageBus()
    system_bus = SystemMessageBus()

    sys_systemd_manager = SystemdManager(bus=system_bus)
    bluetooth_service = ServiceCtl("bluetooth.service", systemd=sys_systemd_manager)

    ses_systemd_manager = SystemdManager(bus=session_bus)

    bears = [
        BatteryBear(
            bus=session_bus, name="battery", battery=Battery(system_bus), nag_lobound=10
        ),
        LorriBear(
            bus=session_bus,
            name="lorri",
            icon=Icons.TROWEL,
            view=I3StatusBlock(block_name="LorriBlock", session_bus=session_bus),
        ),
        BluetoothBear(
            name="bluephones",
            bus=session_bus,
            service=bluetooth_service,
            device=DasBusBluetoothDevice(
                mac_address="38:18:4C:E9:00:D8", bus=system_bus
            ),
            adapter=BluezAdapter(bus=system_bus),
            view=I3StatusBlock(block_name="BluephonesBlock", session_bus=session_bus),
            icon="bluetooth",
        ),
        PauseableServiceLabelBear(
            name="redshift",
            bus=session_bus,
            servicectl=ServiceCtl(
                service_name="redshift.service", systemd=ses_systemd_manager
            ),
            view=I3StatusBlock(block_name="RedshiftBlock", session_bus=session_bus),
            # view=Printer(),
            icon=Icons.EYE,
        ),
        ServiceLabelBear(
            name="dropbox",
            bus=session_bus,
            servicectl=ServiceCtl(
                service_name="dropbox.service", systemd=ses_systemd_manager
            ),
            view=I3StatusBlock(block_name="DropboxBlock", session_bus=session_bus),
            # view=Printer(),
            icon=Icons.FOLDER,
        ),
        DPMSBear(
            name="dpms",
            bus=session_bus,
            view=I3StatusBlock(block_name="DPMSBlock", session_bus=session_bus),
            icon=Icons.EYE,
        ),
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

        logger.info(f"Sucessfully initialized {bear.name} bear")

    logger.info("Running loop")
    loop.run()


@cli.command()
@click.argument("name")
@click.argument("command")
@click.argument("command_args", nargs=-1)
def client(name, command, command_args):

    try:
        bear = next(b for b in build_bears() if b.name == name)
    except StopIteration:
        print("who?")
        exit(1)

    client = bear.get_client()

    client.call(command, command_args)


def main():
    cli()


if __name__ == "__main__":
    main()
