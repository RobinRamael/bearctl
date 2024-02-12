import logging

import click
from gi.repository import GLib

from bear.bear import bears
from bear.eww import eww

logger = logging.getLogger()


# def build_bears(system_bus, session_bus, eww):
#     sys_systemd_manager = SystemdManager(bus=system_bus)
#     bluetooth_service = ServiceCtl("bluetooth.service", systemd=sys_systemd_manager)

#     ses_systemd_manager = SystemdManager(bus=session_bus)

#     bears = [
#         # BatteryBear(
#         #     bus=session_bus,
#         #     name="battery",
#         #     battery=Battery(system_bus),
#         #     bounds=(10, 30, 100),
#         #     notifications=NotificationCtl(session_bus=session_bus),
#         # ),
#         BluetoothBear(
#             name="bluephones",
#             bus=session_bus,
#             service=bluetooth_service,
#             device=DasBusBluetoothDevice(
#                 mac_address="38:18:4C:E9:00:D8", bus=system_bus
#             ),
#             adapter=BluezAdapter(bus=system_bus),
#             view=CombinedLabel(
#                 I3StatusBlock(block_name="BluephonesBlock", session_bus=session_bus),
#             ),
#             icon="bluetooth",
#         ),
#         PauseableServiceLabelBear(
#             name="redshift",
#             bus=session_bus,
#             servicectl=ServiceCtl(
#                 service_name="redshift.service", systemd=ses_systemd_manager
#             ),
#             widget=EwwServiceWidget(eww=eww, service_name="redshift"),
#             pause_interval=60 * 60,
#         ),
#         ServiceLabelBear(
#             name="dropbox",
#             bus=session_bus,
#             servicectl=ServiceCtl(
#                 service_name="dropbox.service", systemd=ses_systemd_manager
#             ),
#             widget=EwwServiceWidget(eww=eww, service_name="dropbox"),
#         ),
#         DPMSBear(
#             name="dpms",
#             bus=session_bus,
#             widget=EwwServiceWidget(eww=eww, service_name="dpms"),
#             interval=1,
#         ),
#         LoadAverageBear(
#             name="loadavg",
#             bus=session_bus,
#             view=EwwStateBlock(eww=eww, block_name="loadavg"),
#             levels=(0.5, 0.8, 0.9),
#             icon=Icons.GEAR,
#             interval=1,
#         ),
#         MemoryBear(
#             name="memory",
#             bus=session_bus,
#             view=EwwStateBlock(eww=eww, block_name="memory"),
#             levels=(70, 80, 90),
#             interval=1,
#             icon=Icons.SD_CARD,
#         ),
#         CPUBear(
#             name="cpu",
#             bus=session_bus,
#             view=EwwStateBlock(eww=eww, block_name="cpu"),
#             levels=(50, 80, 90),
#             interval=1,
#             icon=Icons.CALCULATOR,
#         ),
#         I3Bear(
#             name="i3",
#             bus=session_bus,
#             eww_title_var=eww.var(name="i3_title"),
#         ),
#         MusicBear(
#             name="music",
#             bus=session_bus,
#             eww_track_variable=eww.var(name="mpris_track"),
#         ),
#     ]

#     return bears


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
@click.argument("bear_names", nargs=-1)
def service(bear_names, verbosity):
    logger.setLevel(logging.getLevelName(verbosity.upper()))

    loop = GLib.MainLoop()

    if not bear_names:
        bears.initalize_all()
    else:
        bears.initialize_some(bear_names)

    bears.post_init()

    eww.bootstrap()
    eww.listen_for_reloads()

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

    client = bears.get_client(name)

    client.call(command, command_args)

    logger.info("Ta-ta mr bear!")


def main():
    cli()


if __name__ == "__main__":
    main()
