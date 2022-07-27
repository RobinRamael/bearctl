import logging
from abc import ABC, abstractmethod
from typing import Union

from dasbus.connection import SessionMessageBus


class BearView(ABC):
    @abstractmethod
    def update(self, message: str, icon: Union[str, None], state: str):
        raise NotImplementedError

    def update_simple_icon(self, icon, state):
        self.update(icon, None, state)


I3_STATUS_NAME = "rs.i3status"


logger = logging.getLogger(__name__)


class BlockState:
    good = "good"
    warning = "warning"
    error = "critical"
    idle = "idle"


class I3StatusBlock(BearView):
    def __init__(self, block_name, session_bus=None):
        self.block_name = block_name
        self.bus = session_bus or SessionMessageBus()

    def get_block(self):
        try:
            block = self.bus.get_proxy(I3_STATUS_NAME, f"/{self.block_name}")
            logger.debug(f"Got {self.block_name} block proxy")
            return block
        except:
            logger.error(
                f"Could not find proxy for block {self.block_name}, not updating."
            )
            raise

    def update(self, message: str, icon: str, state: str):

        try:
            block = self.get_block()
        except:
            return

        block.SetText(f"{message}", f"{message}")
        block.SetState(state)

        if icon:
            block.SetIcon(icon)

        return


class Printer(BearView):
    def update(self, message, icon, state):
        print(f"msg: {message}, icon: {icon}, state: {state}")
