import logging
from abc import ABC, abstractmethod

from dasbus.connection import SessionMessageBus


class BearView(ABC):
    @abstractmethod
    def update(self, message: str, icon: str, state: str):
        raise NotImplementedError


I3_STATUS_NAME = "rs.i3status"


logger = logging.getLogger(__name__)


class BlockState:
    good = "good"
    warning = "warning"
    error = "error"
    idle = "idle"


class I3StatusBlock(BearView):
    def __init__(self, block_name, session_bus=None):
        self.block_name = block_name
        self.bus = session_bus or SessionMessageBus()

    def update(self, message: str, icon: str, state: str):

        try:
            block = self.bus.get_proxy(I3_STATUS_NAME, f"/{self.block_name}")
        except:
            logger.error(
                f"Could not find proxy for block {self.block_name}, not updating."
            )
            return

        logger.debug(f"Got {self.block_name} block proxy")

        block.SetText(f"{message}", f"{message}")
        block.SetIcon(icon)
        block.SetState(state)


class Printer(BearView):
    def update(self, message, icon, state):
        print(f"msg: {message}, icon: {icon}, state: {state}")
