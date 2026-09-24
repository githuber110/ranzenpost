class NotConfiguredError(Exception):
    pass


class ConnectionChangedError(NotConfiguredError):
    pass
