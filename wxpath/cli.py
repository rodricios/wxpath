import argparse
import json
from wxpath.core import wxpath_iter, WxStr, parse_wxpath_expr


def _simplify(obj):
    """
    Recursively convert custom wrapper types (e.g., WxStr / ExtractedStr,
    lxml elements) into plain built‑in Python types so that printing or
    JSON serialising shows clean values.
    """
    # Scalars
    if isinstance(obj, WxStr):
        return str(obj)

    # Mapping
    if isinstance(obj, dict):
        return {k: _simplify(v) for k, v in obj.items()}

    # Sequence (but not str/bytes)
    if isinstance(obj, (list, tuple, set)):
        return type(obj)(_simplify(v) for v in obj)

    return obj


def main():
    parser = argparse.ArgumentParser(description="Run wxpath expression.")
    parser.add_argument("expression", help="The wxpath expression")
    parser.add_argument("--depth", type=int, default=1, help="Recursion depth")
    # debug
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    # verbose
    parser.add_argument("--verbose", action="store_true", help="Verbose mode")
    
    args = parser.parse_args()

    if args.verbose:
        print("wxpath expression:", args.expression)
        print("parsed expression:", parse_wxpath_expr(args.expression))

    if args.debug:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    for r in wxpath_iter(args.expression, args.depth):
        clean = _simplify(r)
        print(json.dumps(clean, ensure_ascii=False))


if __name__ == "__main__":
    main()
