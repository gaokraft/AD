"""
Looped tester that focuses on the Games button (Play) and watches for Monetag ads.

Usage:
    python monetag_play_button_tester.py
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import List, Optional

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from monetag_ad_tester import (
    HOME_URL,
    close_additional_windows,
    dismiss_initial_overlay,
    managed_driver,
    wait_for_ads,
)


INITIAL_WAIT = 5.0
RETRY_WAIT = 7.0
POST_CLICK_WAIT = 3.5
POPUP_SETTLE_WAIT = 3.5
ATTEMPTS = 12

HOME_LOCATORS = (
    (By.XPATH, "//*[@id='root']/div/div/div/nav/a[1]"),
    (By.XPATH, "/html/body/div/div/div/div/nav/a[1]"),
    (By.CSS_SELECTOR, "nav[aria-label='Main navigation'] a[href='/']"),
)
GAMES_LOCATORS = (
    (By.XPATH, "//*[@id='root']/div/div/div/nav/a[2]"),
    (By.XPATH, "/html/body/div/div/div/div/nav/a[2]"),
    (By.CSS_SELECTOR, "nav[aria-label='Main navigation'] a[href='/game']"),
    (By.LINK_TEXT, "Games"),
)


@dataclass
class PlayAttemptResult:
    attempt: int
    href: str
    ads_detected: bool
    buttons_visible: bool
    popup_urls: List[str]
    error: Optional[str] = None
    debug_notes: Optional[str] = None


def are_nav_buttons_visible(driver, timeout: float = 3.0) -> bool:
    """Return True if both Home and Games buttons are present and displayed."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        home = find_first_visible(driver, HOME_LOCATORS)
        games = find_first_visible(driver, GAMES_LOCATORS)
        if home and games:
            return True
        time.sleep(0.2)
    return False


def find_first_visible(driver, locators):
    """Return the first element located via any locator that is displayed."""
    for by, value in locators:
        try:
            element = WebDriverWait(driver, 1.5).until(
                EC.presence_of_element_located((by, value))
            )
            if element.is_displayed():
                return element
        except TimeoutException:
            continue
        except WebDriverException:
            continue
    return None


def prepare_main_view(driver, context_label: str) -> None:
    """Ensure the main window is focused and overlays are cleared."""
    close_additional_windows(driver)
    dismiss_initial_overlay(driver, debug_label=context_label)


def click_games_button(
    driver, attempt: int, main_handle: str
) -> PlayAttemptResult:
    """Click the Games button, monitor for ads, and return the outcome."""
    label = f"attempt {attempt}"
    debug: list[str] = []

    try:
        button = find_first_visible(driver, GAMES_LOCATORS)
        if button is None:
            raise TimeoutException("Games button not visible via known locators.")
        WebDriverWait(driver, 2.5).until(lambda d: button.is_enabled())
    except TimeoutException as exc:
        return PlayAttemptResult(
            attempt=attempt,
            href="",
            ads_detected=False,
            buttons_visible=False,
            popup_urls=[],
            error=f"Games button not clickable: {exc}",
        )

    href = button.get_attribute("href") or ""
    with contextlib.suppress(WebDriverException):
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            button,
        )
        time.sleep(0.2)

    before_handles = set(driver.window_handles)
    print(f"[{label}] Clicking Games button -> {href or '<no href>'}")
    try:
        button.click()
    except WebDriverException as exc:
        debug.append(f"native click failed: {exc}; using JS click")
        driver.execute_script("arguments[0].click();", button)

    time.sleep(POST_CLICK_WAIT)

    dismiss_initial_overlay(driver, debug_label=f"{label} post-click")

    both_visible = are_nav_buttons_visible(driver)
    print(f"[{label}] Both buttons visible after click: {both_visible}")

    popup_urls: list[str] = []
    ads_detected = False

    after_handles = set(driver.window_handles)
    new_handles = list(after_handles - before_handles)
    if new_handles:
        debug.append(f"popup handles: {len(new_handles)}")

    for handle in new_handles:
        try:
            driver.switch_to.window(handle)
            print(f"[{label}] Popup opened: {driver.current_url}")
            time.sleep(POPUP_SETTLE_WAIT)
            popup_urls.append(driver.current_url)
            if wait_for_ads(driver, timeout=3):
                ads_detected = True
                debug.append("Monetag elements detected in popup")
        except (TimeoutException, WebDriverException) as exc:
            debug.append(f"popup error: {exc}")
        finally:
            with contextlib.suppress(WebDriverException):
                driver.close()

    with contextlib.suppress(WebDriverException):
        driver.switch_to.window(main_handle)

    if new_handles:
        debug.append("returned to main window after closing popup(s)")

    if not both_visible:
        debug.append("nav buttons missing; likely overlay/ad")

    if not ads_detected and wait_for_ads(driver, timeout=2):
        ads_detected = True
        debug.append("Monetag elements detected on main page")

    return PlayAttemptResult(
        attempt=attempt,
        href=href,
        ads_detected=ads_detected or bool(new_handles) or not both_visible,
        buttons_visible=both_visible,
        popup_urls=popup_urls,
        debug_notes="; ".join(debug) if debug else None,
    )


def exercise_games_button(attempts: int = ATTEMPTS) -> list[PlayAttemptResult]:
    """Run repeated Games-button clicks as described."""
    results: list[PlayAttemptResult] = []
    with managed_driver(headless=False) as driver:
        driver.get(HOME_URL)
        time.sleep(1.5)
        prepare_main_view(driver, "initial load")

        print(f"[setup] Waiting {INITIAL_WAIT} seconds before first click.")
        time.sleep(INITIAL_WAIT)

        main_handle = driver.current_window_handle

        for attempt in range(1, attempts + 1):
            if attempt > 1:
                print(
                    f"[cycle] Waiting {RETRY_WAIT} seconds before next click."
                )
                time.sleep(RETRY_WAIT)

            prepare_main_view(driver, f"attempt {attempt} pre-click")
            result = click_games_button(driver, attempt, main_handle)
            results.append(result)

            if result.error:
                print(f"[!] attempt {attempt}: error -> {result.error}")
            else:
                descriptor = "ads detected" if result.ads_detected else "no ads"
                print(
                    f"[+] attempt {attempt}: {descriptor} "
                    f"(buttons_visible={result.buttons_visible}, "
                    f"popups={len(result.popup_urls)})"
                )

            # Always return to the home page as requested.
            driver.get(HOME_URL)
            time.sleep(1.0)
            prepare_main_view(driver, f"attempt {attempt} post-home")

    return results


def main() -> int:
    try:
        results = exercise_games_button()
    except WebDriverException as exc:
        print(f"Failed to initialise Edge WebDriver: {exc}")
        return 1

    ads = [r for r in results if r.ads_detected]
    errors = [r for r in results if r.error]

    print(
        f"\nCompleted {len(results)} attempts → "
        f"{len(ads)} with ad activity, {len(errors)} errors."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
