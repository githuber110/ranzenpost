import socket

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0", "::"})
ORIGINALS = "_ranzenpost_network_originals"


class NetworkBlocked(OSError):
    pass


def _host_text(host):
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    return str(host or "").strip("[]").lower()


def _local_address(address):
    if not isinstance(address, tuple):
        return True
    return _host_text(address[0]) in LOCAL_HOSTS


def _local_host(host):
    return _host_text(host) in LOCAL_HOSTS


def _local_lookup(host):
    return host is None or _local_host(host)


GUARDED = (
    (socket.socket, "connect", 1, _local_address),
    (socket.socket, "connect_ex", 1, _local_address),
    (socket, "getaddrinfo", 0, _local_lookup),
    (socket, "gethostbyname", 0, _local_host),
    (socket, "gethostbyname_ex", 0, _local_host),
)


def _originals():
    return getattr(socket, ORIGINALS)


def _guard(name, position, allowed):
    def guarded(*args, **kwargs):
        target = args[position] if len(args) > position else kwargs.get("host")
        if not allowed(target):
            raise NetworkBlocked("tests may not reach the network: %s" % (target,))
        return _originals()[name](*args, **kwargs)

    guarded.__name__ = "guarded_" + name
    return guarded


def install():
    if hasattr(socket, ORIGINALS):
        return
    setattr(socket, ORIGINALS, {name: getattr(owner, name) for owner, name, _position, _allowed in GUARDED})
    for owner, name, position, allowed in GUARDED:
        setattr(owner, name, _guard(name, position, allowed))


def uninstall():
    originals = getattr(socket, ORIGINALS, None)
    if originals is None:
        return
    for owner, name, _position, _allowed in GUARDED:
        setattr(owner, name, originals[name])
    delattr(socket, ORIGINALS)


install()
