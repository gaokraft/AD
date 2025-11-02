"""
Basic Selenium harness to sanity-check Monetag ad rendering on https://logovobezdelnikov.com/.

Run locally after installing Selenium and the Microsoft Edge WebDriver that matches your browser.
Example setup (PowerShell):
    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    python -m pip install selenium

Usage:
    python monetag_ad_tester.py
"""

from __future__ import annotations

import contextlib
import sys
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


HOME_URL = "https://logovobezdelnikov.com/"
AD_IDENTIFIERS: Iterable[tuple[str, str]] = (
    (By.CSS_SELECTOR, "iframe[src*='monetag']"),
    (By.CSS_SELECTOR, "script[src*='monetag']"),
)
DEFAULT_VIEW_COUNT = 3
DEFAULT_VIEW_DELAY = 5.0  # seconds to keep the page open before refresh/navigation
WAIT_TIMEOUT = 12  # seconds to wait for ad resources to appear
CLOSE_BUTTON_LOCATORS: tuple[tuple[str, str], ...] = (
    (By.XPATH, "//*[@id='root']/div/div[2]/div/button"),
    (By.XPATH, "//button[@aria-label='Close']"),
    (By.XPATH, "/html/body/div/div/div[2]/div/button"),
    (By.CSS_SELECTOR, "button[aria-label='Close']"),
    (By.XPATH, "//button[contains(normalize-space(.),'✕')]"),
)
OVERLAY_WAIT = 6


@dataclass
class ViewResult:
    number: int
    ads_detected: bool
    error: Optional[str] = None


def build_edge_driver(headless: bool = True) -> webdriver.Edge:
    """Configure and return an Edge WebDriver instance."""
    options = EdgeOptions()
    options.use_chromium = True

    if headless:
        # "new" headless mode keeps parity with visible Edge across versions 118+.
        options.add_argument("--headless=new")

    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--log-level=3")  # suppress noisy driver logs

    return webdriver.Edge(options=options)


def close_additional_windows(driver: webdriver.Edge) -> None:
    """Close any secondary windows Edge may have opened (e.g., welcome or ad popups)."""
    try:
        primary_handle = driver.current_window_handle
    except WebDriverException:
        return

    for handle in list(driver.window_handles):
        if handle == primary_handle:
            continue
        with contextlib.suppress(WebDriverException):
            driver.switch_to.window(handle)
            driver.close()

    with contextlib.suppress(WebDriverException):
        driver.switch_to.window(primary_handle)


def dismiss_initial_overlay(driver: webdriver.Edge, debug_label: str = "") -> None:
    """Attempt to click the first-visit close button or dismiss overlay ads."""
    label = f"[overlay {debug_label}]".strip() if debug_label else "[overlay]"

    def log(message: str) -> None:
        print(f"{label} {message}")

    try:
        primary_handle = driver.current_window_handle
    except WebDriverException:
        return

    # Try each provided locator in order.
    for locator_by, locator_value in CLOSE_BUTTON_LOCATORS:
        try:
            button = WebDriverWait(driver, OVERLAY_WAIT).until(
                EC.element_to_be_clickable((locator_by, locator_value))
            )
            button.click()
            log(f"Closed via locator {locator_by} => {locator_value}")
            return
        except TimeoutException:
            log(f"Locator timed out: {locator_by} => {locator_value}")
        except WebDriverException as exc:
            log(f"Locator click failed: {locator_by} => {locator_value} ({exc})")

    # If an ad overlay blocks the button, click the page and retry once.
    current_url = driver.current_url
    before_handles = set(driver.window_handles)
    log("Attempting body click to dismiss blocking overlay.")
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        body.click()
        time.sleep(0.5)
    except WebDriverException as exc:
        log(f"Body click failed: {exc}; trying offset click.")
        try:
            ActionChains(driver).move_by_offset(10, 10).click().perform()
            time.sleep(0.5)
        except WebDriverException as nested_exc:
            log(f"Offset click failed: {nested_exc}")
            return

    after_handles = set(driver.window_handles)
    new_handles = list(after_handles - before_handles)

    for handle in new_handles:
        with contextlib.suppress(WebDriverException):
            driver.switch_to.window(handle)
            log(f"Closing new window: {driver.current_url}")
            driver.close()

    with contextlib.suppress(WebDriverException):
        driver.switch_to.window(primary_handle)

    if new_handles:
        log("Reloading page after closing popup(s).")
        with contextlib.suppress(WebDriverException):
            driver.get(current_url)
            time.sleep(0.8)

    for locator_by, locator_value in CLOSE_BUTTON_LOCATORS:
        try:
            button = driver.find_element(locator_by, locator_value)
            button.click()
            log(f"Closed after retry via {locator_by}.")
            return
        except WebDriverException as exc:
            log(f"Retry close failed for {locator_by}: {exc}")


def wait_for_ads(driver: webdriver.Edge, timeout: int = WAIT_TIMEOUT) -> bool:
    """Return True once any Monetag-related resource becomes visible, else False."""
    wait = WebDriverWait(driver, timeout)
    for locator in AD_IDENTIFIERS:
        try:
            wait.until(EC.presence_of_element_located(locator))
            return True
        except TimeoutException:
            continue
    return False


def simulate_view(
    driver: webdriver.Edge,
    view_number: int,
    url: str = HOME_URL,
    dwell_seconds: float = DEFAULT_VIEW_DELAY,
) -> ViewResult:
    """Open the target URL, wait for ads, and keep the tab alive briefly."""
    try:
        driver.get(url)
        time.sleep(1.0)  # allow any first-visit popups to spawn
        close_additional_windows(driver)
        dismiss_initial_overlay(driver, debug_label=f"view {view_number}")
        ads_visible = wait_for_ads(driver)

        time.sleep(max(dwell_seconds, 0))
        return ViewResult(number=view_number, ads_detected=ads_visible)
    except WebDriverException as exc:
        return ViewResult(number=view_number, ads_detected=False, error=str(exc))


@contextlib.contextmanager
def managed_driver(headless: bool = True):
    """Context manager that ensures the WebDriver shuts down cleanly."""
    driver = None
    try:
        driver = build_edge_driver(headless=headless)
        yield driver
    finally:
        if driver:
            driver.quit()


def perform_test_cycle(
    views: int = DEFAULT_VIEW_COUNT,
    dwell_seconds: float = DEFAULT_VIEW_DELAY,
    headless: bool = True,
) -> list[ViewResult]:
    """Run the requested number of simulated views."""
    results: list[ViewResult] = []
    with managed_driver(headless=headless) as driver:
        for view_number in range(1, views + 1):
            result = simulate_view(
                driver, view_number=view_number, dwell_seconds=dwell_seconds
            )
            if result.error:
                print(f"[!] View {view_number}: error -> {result.error}")
            else:
                verb = "found" if result.ads_detected else "missing"
                print(f"[+] View {view_number}: ads {verb}")
            results.append(result)

            if view_number != views:
                driver.refresh()

    return results


def main(argv: list[str]) -> int:
    try:
        results = perform_test_cycle()
    except WebDriverException as exc:
        print(f"Failed to initialise Edge WebDriver: {exc}")
        return 1

    failures = [result for result in results if result.error or not result.ads_detected]
    if failures:
        print(f"\nCompleted with {len(failures)} issue(s) detected.")
        return 2

    print("\nAll views detected Monetag ad activity.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
