import logging

from bear.bear import bears
from bear.eww import EwwController, eww
from bear.utils import in_debug_mode
import click
from gi.repository import GLib

logger = logging.getLogger()


@click.group()
@click.option("--color", is_flag=True)
@click.option(
    "--verbosity",
    type=click.Choice(
        ["critical", "error", "warning", "info", "debug"], case_sensitive=False
    ),
    default="info",
)
@click.option("--debug", type=str, multiple=True)
def cli(color, verbosity, debug):
    logger = logging.getLogger()
    handler = logging.StreamHandler()

    if color:
        import colorlog

        handler.setFormatter(
            colorlog.ColoredFormatter(
                "%(log_color)s%(levelname)-8s - %(asctime)s - %(name)s - %(message)s"
            )
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(levelname)-8s - %(asctime)s - %(name)s - %(message)s")
        )

    logger = logging.getLogger()
    logger.handlers = [handler]
    logger.setLevel(verbosity.upper())

    for module in debug:
        logging.getLogger(f"bear.{module}").setLevel(logging.DEBUG)


@cli.command()
@click.argument("bear_names", nargs=-1)
@click.option("--eww-no-listen", is_flag=True, default=False)
@click.option("--no-eww", is_flag=True, default=False)
def service(bear_names, eww_no_listen=False, no_eww=False):
    loop = GLib.MainLoop()

    if not bear_names:
        bears.initalize_all()
    else:
        bears.initialize_some(bear_names)

    if not bears.bears:
        logger.critical("No viable bears... Exiting.")
        exit(1)

    bears.post_init()

    eww.dry_run = no_eww
    eww.bootstrap()
    if not no_eww and not eww_no_listen:
        eww.listen_for_reloads()  # FIXME? sometimes this loops forever

    logger.info("Running loop")
    try:
        loop.run()
    except KeyboardInterrupt:
        bears.unregister()


@cli.command()
@click.argument("name")
@click.argument("command")
@click.option("--silent", is_flag=True)
@click.argument("command_args", nargs=-1)
def client(name, command, command_args, silent=False):
    logger = logging.getLogger("bear")
    if silent:
        logger.setLevel(logging.ERROR)
    else:
        logger.setLevel(logging.INFO)

    logger.info(f"Debug mode is {'on' if in_debug_mode() else 'off'}")

    client = bears.get_client(name)

    client.call(command, command_args)

    logger.info("Ta-ta mr bear!")


def main():
    cli()


if __name__ == "__main__":
    main()
