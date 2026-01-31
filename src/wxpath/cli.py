import argparse
import json
import sys

from wxpath.core import parser as wxpath_parser
from wxpath.core.runtime.engine import WXPathEngine, wxpath_async_blocking_iter
from wxpath.hooks import builtin, registry
from wxpath.http.client.crawler import Crawler
from wxpath.settings import SETTINGS
from wxpath.util.serialize import simplify


def main():
    registry.register(builtin.SerializeXPathMapAndNodeHook)
    arg_parser = argparse.ArgumentParser(description="Run wxpath expression.")
    arg_parser.add_argument("expression", help="The wxpath expression")
    arg_parser.add_argument("--depth", type=int, default=1, help="Recursion depth")
    # debug
    arg_parser.add_argument("--debug", action="store_true", 
                            help="Debug mode. Provides verbose runtime output and information")
    # verbose
    arg_parser.add_argument("--verbose", action="store_true", 
                            help="Verbose mode. Prints CLI level information")
    
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
    arg_parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable SSL certificate verification (use for sites with broken chains)",
    )
    arg_parser.add_argument(
        "--cache",
        action="store_true",
        help="Use cache",
        default=False
    )
    arg_parser.add_argument(
        "--cache-backend",
        type=str,
        help="Cache backend. Possible values: redis, sqlite",
        default="sqlite"
    )
    arg_parser.add_argument(
        "--cache-db-path-or-url",
        type=str,
        help="Path to cache database",
        default="cache.db"
    )

    args = arg_parser.parse_args()

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

    if args.cache:
        SETTINGS.http.client.cache.enabled = True
        if args.cache_backend == "redis":
            SETTINGS.http.client.cache.backend = "redis"
            SETTINGS.http.client.cache.redis.address = args.cache_db_path_or_url
        elif args.cache_backend == "sqlite":
            SETTINGS.http.client.cache.backend = "sqlite"
            SETTINGS.http.client.cache.sqlite.cache_name = args.cache_db_path_or_url

    if args.verbose:
        print(f"Using concurrency: {args.concurrency}")
        print(f"Using concurrency per host: {args.concurrency_per_host}")
        print(f"Using respect robots: {args.respect_robots}")
        print(f"Using cache: {args.cache}")

        segments = wxpath_parser.parse(args.expression)
        print("parsed expression:\n\nSegments([")
        for s in segments:
            print(f"\t{s},")
        print("])")
        print()
        print()

    crawler = Crawler(
        concurrency=args.concurrency,
        per_host=args.concurrency_per_host,
        respect_robots=args.respect_robots,
        verify_ssl=not args.insecure,
        headers=custom_headers
    )
    engine = WXPathEngine(crawler=crawler)

    try:
        for r in wxpath_async_blocking_iter(
            path_expr=args.expression, 
            max_depth=args.depth, 
            engine=engine):
            clean = simplify(r)
            print(json.dumps(clean, ensure_ascii=False), flush=True)
    except BrokenPipeError:
        if args.verbose:
            print("Pipe broken.")

    if args.verbose:
        print("Done. Printing crawl stats")
        print(crawler._stats)
    sys.exit(0)


if __name__ == "__main__":
    main()
