import logging

from . import battery
from . import bluetooth
from . import dpms
from . import dunst
from . import monitor
from . import music
from . import sway
from . import systemd
from . import volume

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(levelname)-8s - %(asctime)s - %(name)s - %(message)s")
)
logger = logging.getLogger()
logger.handlers = [handler]
