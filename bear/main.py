import logging

import click
from gi.repository import GLib

from bear.bear import bears
from bear.eww import eww

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
def cli(color, verbosity):
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

    logger.setLevel(logging.getLevelName(verbosity.upper()))


@cli.command()
@click.argument("bear_names", nargs=-1)
def service(bear_names):
    loop = GLib.MainLoop()

    if not bear_names:
        bears.initalize_all()
    else:
        bears.initialize_some(bear_names)

    if not bears.bears:
        logger.critical("No viable bears... Exiting.")
        exit(1)

    bears.post_init()

    eww.bootstrap()
    # eww.listen_for_reloads()  # FIXME

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
