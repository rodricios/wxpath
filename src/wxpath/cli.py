import argparse
import json
import sys

from wxpath.core import parser as wxpath_parser
from wxpath.core.runtime.engine import WXPathEngine, wxpath_async_blocking_iter
from wxpath.hooks import builtin, registry
from wxpath.http.client.crawler import Crawler
from wxpath.util.serialize import simplify


def main():
    registry.register(builtin.SerializeXPathMapAndNodeHook)
    arg_parser = argparse.ArgumentParser(description="Run wxpath expression.")
    arg_parser.add_argument("expression", help="The wxpath expression")
    arg_parser.add_argument("--depth", type=int, default=1, help="Recursion depth")
    # debug
    arg_parser.add_argument("--debug", action="store_true", help="Debug mode")
    # verbose
    arg_parser.add_argument("--verbose", action="store_true", help="Verbose mode")
    
    arg_parser.add_argument(
        "--concurrency", 
        type=int, 
        default=16, 
        help="Number of concurrent fetches"
    )
    arg_parser.add_argument(
        "--concurrency-per-host", 
        type=int,
        default=8,
        help="Number of concurrent fetches per host"
    )
    arg_parser.add_argument(
        "--header",
        action="append",
        dest="header_list",
        default=[],
        help="Add a custom header (e.g., 'Key:Value'). Can be used multiple times.",
    )
    arg_parser.add_argument(
        "--respect-robots",
        action="store_true",
        help="Respect robots.txt",
        default=True
    )

    args = arg_parser.parse_args()

    if args.verbose:
        segments = wxpath_parser.parse(args.expression)
        print("parsed expression:\n\nSegments([")
        for s in segments:
            print(f"\t{s},")
        print("])")
        print()

    if args.debug:
        from wxpath import configure_logging
        configure_logging('DEBUG')

    custom_headers = {}
    if args.header_list:
        for header_item in args.header_list:
            try:
                key, value = header_item.split(':', 1)
                custom_headers[key.strip()] = value.strip()
            except ValueError:
                print(f"Warning: Invalid header format '{header_item}'. Use 'Key:Value'.")

    if custom_headers and args.verbose:
        print(f"Using custom headers: {custom_headers}")
        print()

    crawler = Crawler(
        concurrency=args.concurrency,
        per_host=args.concurrency_per_host,
        respect_robots=args.respect_robots,
        headers=custom_headers
    )
    engine = WXPathEngine(crawler=crawler)

    try:
        for r in wxpath_async_blocking_iter(args.expression, args.depth, engine):
            clean = simplify(r)
            print(json.dumps(clean, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        sys.exit(0)


if __name__ == "__main__":
    main()
