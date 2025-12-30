from wxpath.core.ops import WxStr


def simplify(obj):
    """
    Recursively convert custom wrapper types (e.g., WxStr / ExtractedStr,
    lxml elements) into plain built-in Python types so that printing or
    JSON serialising shows clean values.
    """
    # Scalars
    if isinstance(obj, WxStr):
        return str(obj)

    # Mapping
    if isinstance(obj, dict):
        return {k: simplify(v) for k, v in obj.items()}

    # Sequence (but not str/bytes)
    if isinstance(obj, (list, tuple, set)):
        return type(obj)(simplify(v) for v in obj)

    return obj
