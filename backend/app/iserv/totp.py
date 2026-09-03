import pyotp


def normalize_secret(secret):
    return secret.replace(" ", "").upper()


def generate_code(secret, at=None):
    totp = pyotp.TOTP(normalize_secret(secret))
    if at is None:
        return totp.now()
    return totp.at(at)
