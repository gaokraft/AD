"""Visible Edge Selenium workflow to observe ad rendering and navigation.

This runner reuses the core ad navigation logic but defaults to launching a headed
Microsoft Edge window so you can observe every interaction. Selenium Manager will
resolve the required msedgedriver automatically, so you do not need to download a
driver binary manually. Provide --headless to suppress the UI, or --driver-path to
point at a custom driver executable.
"""

import argparse

from edge_ad_render_tester import run_ad_navigation_test


DEFAULT_ITERATIONS = 0
DEFAULT_MIN_WAIT_SECONDS = 10.0
DEFAULT_MAX_WAIT_SECONDS = 30.0
DEFAULT_URL = "https://sweetmuse.shop/"


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Edge Selenium ad navigation tester (headed by default)",
    )
    parser.add_argument(
        "--iterations",
        type=int,
        default=DEFAULT_ITERATIONS,
        help="Number of navigation loops to perform (0 runs until interrupted)",
    )
    parser.add_argument(
        "--min-wait",
        type=float,
        default=DEFAULT_MIN_WAIT_SECONDS,
        help=f"Lower bound for wait duration between actions in seconds (default: {DEFAULT_MIN_WAIT_SECONDS})",
    )
    parser.add_argument(
        "--max-wait",
        type=float,
        default=DEFAULT_MAX_WAIT_SECONDS,
        help=f"Upper bound for wait duration between actions in seconds (default: {DEFAULT_MAX_WAIT_SECONDS})",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_URL,
        help=f"Target URL to test against (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Microsoft Edge in headless mode instead of headed",
    )
    parser.add_argument(
        "--driver-path",
        type=str,
        default=None,
        help="Optional path to a local msedgedriver executable",
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    run_ad_navigation_test(
        iterations=max(0, arguments.iterations),
        min_wait=max(0.0, arguments.min_wait),
        max_wait=max(0.0, arguments.max_wait),
        url=arguments.url,
        headless=arguments.headless,
        driver_path_override=arguments.driver_path,
    )


if __name__ == "__main__":
    main()
