from functools import wraps

import click
from dasbus.connection import SessionMessageBus
from dasbus.loop import EventLoop
from gi.repository import GLib

from bear import ServiceBear
from systemd import ServiceCtl, SystemdManager
from views import I3StatusBlock, Printer

FOLDER_ICON = "\uf07b"
EYE_ICON = "\uf06e"

import logging
import sys

logging.basicConfig(stream=sys.stdout, level=logging.INFO)

logger = logging.getLogger()


def build_bears():
    bus = SessionMessageBus()
    systemd_manager = SystemdManager(bus=bus)

    bears = [
        ServiceBear(
            bus=bus,
            name="redshift",
            servicectl=ServiceCtl(
                service_name="redshift.service", systemd=systemd_manager
            ),
            # i3status=I3StatusBlock(block_name="RedshiftService", session_bus=bus),
            view=Printer(),
            icon=FOLDER_ICON,
        ),
        ServiceBear(
            bus=bus,
            name="dropbox",
            servicectl=ServiceCtl(
                service_name="dropbox.service", systemd=systemd_manager
            ),
            # i3status=I3StatusBlock(block_name="DropboxService", session_bus=bus),
            view=Printer(),
            icon=FOLDER_ICON,
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




if __name__ == "__main__":
    cli()
