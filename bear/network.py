from bear.bear import Bear
from bear.poke import MultiProxyPoke, Poke, ProxyPoke


class NetworkManager:
    def __init__(self, bus):
        self.bus = bus
        self.proxy = bus.get_proxy(
            "org.freedesktop.NetworkManager", "/org/freedesktop/NetworkManager"
        )

    def listen(self):
        pass

    @property
    def active_connections(self):
        return self.proxy.Get("org.freedesktop.Networkmanager", "ActiveConnections")


class ActiveConnectionsPoke(ProxyPoke):
    pass


class NetworkBear(Bear):
    def __init__(self, *args, **kwargs):
        pass

    def update_widget(self):
        pass
