class IServError(Exception):
    def __init__(self, note="", message_key="", detail=None):
        super().__init__(note)
        self.message_key = message_key
        self.detail = dict(detail or {})


class LoginError(IServError):
    pass


class TwoFactorError(IServError):
    pass


class DataError(IServError):
    pass


class PasswordError(IServError):
    pass
