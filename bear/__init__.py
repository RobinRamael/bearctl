import logging

from . import battery
from . import systemd
from . import monitor
from . import dpms
from . import i3
from . import dunst

logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(
    logging.Formatter("%(levelname)-8s - %(asctime)s - %(name)s - %(message)s")
)
logger = logging.getLogger()
logger.handlers = [handler]
