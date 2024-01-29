from functools import wraps
import logging
import os
import sys

import click
from dasbus.connection import SessionMessageBus, SystemMessageBus
from dasbus.loop import EventLoop
from gi.repository import GLib

from bear.battery import Battery, BatteryBear
from bear.bluetooth import BluetoothBear, BluezAdapter, DasBusBluetoothDevice
from bear.dpms import DPMSBear
from bear.exceptions import error_mapper
from bear.icons import Icons
from bear.lorri import LorriBear
from bear.monitor import BearMonitorBear, CPUBear, LoadAverageBear, MemoryBear
from bear.systemd import (
    PauseableServiceLabelBear,
    ServiceCtl,
    ServiceLabelBear,
    SystemdManager,
)
from bear.views import (
    CombinedLabel,
    EwwController,
    EwwServiceWidget,
    EwwStateBlock,
    I3StatusBlock,
    NotificationCtl,
)


logger = logging.getLogger()


def build_bears():
    session_bus = SessionMessageBus(error_mapper=error_mapper)
    system_bus = SystemMessageBus(error_mapper=error_mapper)

    sys_systemd_manager = SystemdManager(bus=system_bus)
    bluetooth_service = ServiceCtl("bluetooth.service", systemd=sys_systemd_manager)

    ses_systemd_manager = SystemdManager(bus=session_bus)

    eww_controller = EwwController()

    bears = [
        # BatteryBear(
        #     bus=session_bus,
        #     name="battery",
        #     battery=Battery(system_bus),
        #     bounds=(10, 30, 100),
        #     notifications=NotificationCtl(session_bus=session_bus),
        # ),
        BluetoothBear(
            name="bluephones",
            bus=session_bus,
            service=bluetooth_service,
            device=DasBusBluetoothDevice(
                mac_address="38:18:4C:E9:00:D8", bus=system_bus
            ),
            adapter=BluezAdapter(bus=system_bus),
            view=CombinedLabel(
                I3StatusBlock(block_name="BluephonesBlock", session_bus=session_bus),
            ),
            icon="bluetooth",
        ),
        # PauseableServiceLabelBear(
        #     name="redshift",
        #     bus=session_bus,
        #     servicectl=ServiceCtl(
        #         service_name="redshift.service", systemd=ses_systemd_manager
        #     ),
        #     view=CombinedLabel(
        #         I3StatusBlock(block_name="RedshiftBlock", session_bus=session_bus),
        #     ),
        #     icon=Icons.EYE,
        # ),
        ServiceLabelBear(
            name="dropbox",
            bus=session_bus,
            servicectl=ServiceCtl(
                service_name="dropbox.service", systemd=ses_systemd_manager
            ),
            widget=EwwServiceWidget(eww=eww_controller, service_name="dropbox"),
        ),
        DPMSBear(
            name="dpms",
            bus=session_bus,
            widget=EwwServiceWidget(eww=eww_controller, service_name="dpms"),
            interval=1,
        ),
        LoadAverageBear(
            name="loadavg",
            bus=session_bus,
            view=EwwStateBlock(eww=eww_controller, block_name="loadavg"),
            levels=(0.3, 0.6, 0.9),
            icon=Icons.GEAR,
            interval=1,
        ),
        MemoryBear(
            name="memory",
            bus=session_bus,
            view=EwwStateBlock(eww=eww_controller, block_name="memory"),
            levels=(10, 60, 90),
            interval=1,
            icon=Icons.SD_CARD,
        ),
        CPUBear(
            name="cpu",
            bus=session_bus,
            view=EwwStateBlock(eww=eww_controller, block_name="cpu"),
            levels=(10, 60, 90),
            interval=1,
            icon=Icons.CALCULATOR,
        ),
        BearMonitorBear(
            name="bear",
            bus=session_bus,
            view=EwwStateBlock(eww=eww_controller, block_name="bear"),
            levels=(10, 60, 90),
            interval=1,
            icon=Icons.BEAR,
        ),
    ]

    return bears


@click.group()
def cli():
    pass


@cli.command()
@click.option(
    "--verbosity",
    type=click.Choice(
        ["critical", "error", "warning", "info", "debug"], case_sensitive=False
    ),
    default="info",
)
@click.argument("bears", nargs=-1)
def service(bears, verbosity):
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
    logger = logging.getLogger()
    logger.handlers = [handler]

    logger.setLevel(logging.getLevelName(verbosity.upper()))

    logger.info("Starting GLib main loop")
    loop = GLib.MainLoop()

    logger.info("Bootstrapping client into eww")
    EwwController.bootstrap()

    logger.info("Building a small but formidable army of bears...")
    all_bears = build_bears()

    if bears:
        bears_to_register = [b for b in all_bears if b.name in bears]
    else:
        bears_to_register = all_bears

    for bear in bears_to_register:
        bear.register()

        logger.info(f"Sucessfully initialized {bear.name} bear")

    logger.info("Running loop")
    loop.run()


@cli.command()
@click.argument("name")
@click.argument("command")
@click.option("--silent", is_flag=True)
@click.argument("command_args", nargs=-1)
def client(name, command, command_args, silent=False):
    logger = logging.getLogger()
    if silent:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.INFO)

    try:
        bear = next(b for b in build_bears() if b.name == name)
    except StopIteration:
        print("who?")
        exit(1)

    client = bear.get_client()

    client.call(command, command_args)

    logger.info("Ta-ta mr bear!")


def main():
    cli()


if __name__ == "__main__":
    main()
