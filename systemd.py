import re

import pydbus
from gi.repository import GLib

SYSTEMD_BUS_NAME = "org.freedesktop.systemd1"
SYSTEMD_PATH = "/org/freedesktop/systemd1"
SYSTEMD_MANAGER = "org.freedesktop.systemd1.Manager"

from utils import snake2camel


class SystemdManager:
    def __init__(self, bus):
        self.bus = bus
        self.manager = self.bus.get(SYSTEMD_BUS_NAME, SYSTEMD_PATH)

    def get_unit(self, service_name):
        path = self.manager.GetUnit(service_name)
        return self.bus.get(SYSTEMD_BUS_NAME, path)


class ServiceCtl(object):
    def __init__(self, service_name, systemd=None):
        # self.bus = bus or pydbus.SessionBus()
        self.service_name = service_name
        self.systemd = systemd or SystemdManager()

    def get_properties(self):
        unit = self.systemd.get_unit(self.service_name)
        return unit.GetAll("org.freedesktop.systemd1.Service")

    def __getattr__(self, name):
        unit = self.systemd.get_unit(self.service_name)
        try:
            return unit.Get("org.freedesktop.systemd1.Unit", snake2camel(name))
        except GLib.GError:
            raise AttributeError

    def start(self):
        print("start!")

    def stop(self):
        print("stop!")


