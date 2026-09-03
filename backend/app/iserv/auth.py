DIGIT_FIELD = "two_factor_login_form[two_factor_code_digit_{index}]"


def fill_two_factor_code(fields, code):
    result = dict(fields)
    filled = False
    if "otp" in result:
        result["otp"] = code
        filled = True
    for index, digit in enumerate(code, start=1):
        key = DIGIT_FIELD.format(index=index)
        if key in result:
            result[key] = digit
            filled = True
    if not filled:
        raise ValueError("form has no known two-factor fields")
    return result


def apply_login_fields(fields, username, password):
    result = dict(fields)
    result["_username"] = username
    result["_password"] = password
    if "_remember_me" in result:
        result["_remember_me"] = "on"
    return result
