import pydbus

I3_STATUS_NAME = "i3.status.rs"

class I3StatusBlock(object):
    def __init__(self, block_name):
        self.block_name = block_name

    def set_i3_block(self, message, icon, state):
        bus = pydbus.SessionBus()

        bluetooth_block = bus.get(I3_STATUS_NAME, f"/{self.block_name}")
        bluetooth_block.SetStatus(message, icon, state)
