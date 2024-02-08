from bear.bear import Bear, bears, dbus_method
from bear.eww import EwwPrefixView
from bear.poke import PropertiesPoke
from bear.utils import BearLevel


@bears.recruit
class DunstBear(Bear):
    name = "dunst"
    dunst = PropertiesPoke(
        "org.freedesktop.Notifications",
        "/org/freedesktop/Notifications",
        "org.dunstproject.cmd0",
        property_names=["paused"],
        capitalize_first=False,
    )

    eww = EwwPrefixView(var_names=["paused", "status"])

    def get_extra_context(self):
        ctx = super().get_extra_context()
        ctx["status"] = (
            BearLevel.warning if self.dunst.data["paused"] else BearLevel.idle
        )
        return ctx

    @dbus_method()
    def toggle_pause(self):
        if self.dunst.proxy.paused:
            self.dunst.proxy.paused = False
        else:
            self.dunst.proxy.paused = True
