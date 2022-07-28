import logging
from abc import ABC, abstractmethod
from typing import Union

from dasbus.connection import SessionMessageBus
from dasbus.error import DBusError


class BearView(ABC):
    @abstractmethod
    def update(self, message: str, icon: Union[str, None], state: str):
        raise NotImplementedError

    def update_simple_icon(self, icon, state):
        self.update(icon, None, state)


POSSIBLE_I3_STATUS_NAMES = ["rs.i3status", "rs.i3status.bottom", "rs.i3status.top"]


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
        self._block = None

    @property
    def block(self):
        if not self._block:
            self._block = self.get_block()

        return self._block

    def get_block(self):
        for name in POSSIBLE_I3_STATUS_NAMES:
            block = self.bus.get_proxy(name, f"/{self.block_name}")

            try:
                # block is only checked when we try to find one of its attrs
                assert block.SetText
                logger.debug(f"Got {self.block_name} block proxy")
                return block
            except DBusError:
                continue

        raise Exception(
            f"Unable to find {self.block_name} anywhere in any of {POSSIBLE_I3_STATUS_NAMES}"
        )

    def update(self, message: str, icon: str, state: str):

        self.block.SetText(f"{message}", f"{message}")
        self.block.SetState(state)

        if icon:
            self.block.SetIcon(icon)

        return


class Printer(BearView):
    def update(self, message, icon, state):
        print(f"msg: {message}, icon: {icon}, state: {state}")
