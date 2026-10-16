def query_key(params, ignored=()):
    if isinstance(params, (str, bytes)):
        return (("", params),)
    items = params.items() if hasattr(params, "items") else params or ()
    pairs = [(str(key), _hashable(value)) for key, value in items if key not in ignored]
    return tuple(sorted(pairs, key=repr))


def _hashable(value):
    if isinstance(value, dict):
        return query_key(value)
    if isinstance(value, (list, tuple)):
        return tuple(_hashable(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted((_hashable(item) for item in value), key=repr))
    return value
