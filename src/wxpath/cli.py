import argparse
import json
import sys

from wxpath.core.parser import parse_wxpath_expr
from wxpath.core.runtime.engine import WXPathEngine, wxpath_async_blocking_iter
from wxpath.hooks import builtin, registry
from wxpath.util.serialize import simplify


def main():
    registry.register(builtin.SerializeXPathMapAndNodeHook)
    parser = argparse.ArgumentParser(description="Run wxpath expression.")
    parser.add_argument("expression", help="The wxpath expression")
    parser.add_argument("--depth", type=int, default=1, help="Recursion depth")
    # debug
    parser.add_argument("--debug", action="store_true", help="Debug mode")
    # verbose
    parser.add_argument("--verbose", action="store_true", help="Verbose mode")
    
    parser.add_argument("--concurrency", type=int, default=16, help="Number of concurrent fetches")
    parser.add_argument(
        "--concurrency-per-host", 
        type=int,
        default=8,
        help="Number of concurrent fetches per host"
    )

    args = parser.parse_args()

    if args.verbose:
        print("wxpath expression:", args.expression)
        print("parsed expression:", parse_wxpath_expr(args.expression))

    if args.debug:
        from wxpath import configure_logging
        configure_logging('DEBUG')

    engine = WXPathEngine(
        concurrency=args.concurrency,
        per_host=args.concurrency_per_host,
    )
    try:
        for r in wxpath_async_blocking_iter(args.expression, args.depth, engine):
            clean = simplify(r)
            print(json.dumps(clean, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    main()
