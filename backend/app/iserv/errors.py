class IServError(Exception):
    pass


class LoginError(IServError):
    pass


class TwoFactorError(IServError):
    pass


class DataError(IServError):
    pass


class PasswordError(IServError):
    pass
