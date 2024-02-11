from bear.bear import Bear, bears, dbus_method
from bear.eww import EwwPrefixView
from bear.poke import ProxyPoke
from bear.utils import BearLevel


@bears.recruit
class DunstBear(Bear):
    name = "dunst"
    dunst = ProxyPoke(
        service_name="org.freedesktop.Notifications",
        obj_path="/org/freedesktop/Notifications",
        interface_name="org.dunstproject.cmd0",
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
        dunst_proxy = self.dunst.get_proxy()
        if dunst_proxy.paused:
            dunst_proxy.paused = False
        else:
            dunst_proxy.paused = True
