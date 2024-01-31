import logging
from typing import List

from bear.bear import Bear, dbus_method

logger = logging.getLogger()


class DirectorBear(Bear):
    def __init__(self, bus, bears: List[Bear]):
        super().__init__(bus, "director")
        self.bears = bears

    @dbus_method()
    def refresh_all(self):
        logger.info("Refreshing all bears")
        for bear in self.bears:
            bear.refresh()
