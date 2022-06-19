from abc import ABC, abstractmethod

from dasbus.connection import SessionMessageBus


class BearView(ABC):
    @abstractmethod
    def update(self, message: str, icon: str, state: str):
        raise NotImplementedError


I3_STATUS_NAME = "i3.status.rs"

import logging

logger = logging.getLogger(__name__)


class I3StatusBlock(BearView):
    def __init__(self, block_name, session_bus=None):
        self.block_name = block_name
        self.bus = session_bus or SessionMessageBus()

    def update(self, message, icon, state):

        block = self.bus.get_proxy(I3_STATUS_NAME, f"/{self.block_name}")
        logger.debug(f"Got {self.block_name} block proxy")

        block.SetStatus(f"{message}", icon, state)
        logger.debug(f"Called SetStatus")


class Printer(BearView):
    def update(self, message, icon, state):
        print(f"msg: {message}, icon: {icon}, state: {state}")
