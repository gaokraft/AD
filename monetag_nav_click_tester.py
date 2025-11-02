"""
Exercise the main navigation and log when Monetag ads spawn during user interactions.

Usage:
    python monetag_nav_click_tester.py
"""

from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from typing import List, Optional, Tuple

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


TOGGLE_ITERATIONS = 16
POST_CLICK_WAIT = 2.5
POPUP_SETTLE_WAIT = 3.0

NAV_BUTTONS: Tuple[Tuple[str, Tuple[str, str]], ...] = (
    ("Home", (By.XPATH, "//*[@id='root']/div/div/div/nav/a[1]")),
    ("Games", (By.XPATH, "//*[@id='root']/div/div/div/nav/a[2]")),
)


@dataclass
class ClickResult:
    iteration: int
    clicked_label: str
    href: str
    ads_detected: bool
    both_buttons_visible: bool
    popup_urls: List[str]
    error: Optional[str] = None
    debug_notes: Optional[str] = None


def are_both_buttons_visible(driver, timeout: float = 2.5) -> bool:
    """Verify both nav buttons are visible."""
    try:
        home = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located(NAV_BUTTONS[0][1])
        )
        games = WebDriverWait(driver, timeout).until(
            EC.visibility_of_element_located(NAV_BUTTONS[1][1])
        )
        return home.is_displayed() and games.is_displayed()
    except TimeoutException:
        return False


def prepare_main_view(driver, iteration_label: str) -> None:
    """Ensure only the primary tab is open and overlays are dismissed."""
    close_additional_windows(driver)
    dismiss_initial_overlay(driver, debug_label=iteration_label)


def exercise_navigation(iterations: int = TOGGLE_ITERATIONS) -> list[ClickResult]:
    """Toggle between the Home and Games buttons, logging when ads appear."""
    results: list[ClickResult] = []
    with managed_driver(headless=False) as driver:
        driver.get(HOME_URL)
        time.sleep(1.5)

        main_handle = driver.current_window_handle
        prepare_main_view(driver, "initial load")

        button_index = 0

        for iteration in range(1, iterations + 1):
            label = f"iteration {iteration}"
            try:
                target_label, target_locator = NAV_BUTTONS[button_index]
                button_index = (button_index + 1) % len(NAV_BUTTONS)

                print(f"[{label}] Clicking '{target_label}'.")

                button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable(target_locator)
                )
                href = button.get_attribute("href") or ""

                before_handles = set(driver.window_handles)
                button.click()
                time.sleep(POST_CLICK_WAIT)

                both_buttons_visible = are_both_buttons_visible(driver)
                print(
                    f"[{label}] Both buttons visible after click: {both_buttons_visible}."
                )

                popup_urls: list[str] = []
                ads_detected = False
                debug_notes: list[str] = []

                after_handles = set(driver.window_handles)
                new_handles = list(after_handles - before_handles)
                if new_handles:
                    debug_notes.append(f"new handles: {len(new_handles)}")

                for handle in new_handles:
                    try:
                        driver.switch_to.window(handle)
                        print(f"[{label}] Popup window detected: {driver.current_url}")
                        time.sleep(POPUP_SETTLE_WAIT)
                        popup_urls.append(driver.current_url)
                        if wait_for_ads(driver, timeout=3):
                            ads_detected = True
                            debug_notes.append("popup contained Monetag elements")
                    except (TimeoutException, WebDriverException) as exc:
                        debug_notes.append(f"popup handling error: {exc}")
                    finally:
                        with contextlib.suppress(WebDriverException):
                            driver.close()

                with contextlib.suppress(WebDriverException):
                    driver.switch_to.window(main_handle)

                if new_handles:
                    debug_notes.append("returned to main handle after popup(s)")
                    driver.get(HOME_URL)
                    time.sleep(1.2)
                    prepare_main_view(driver, label)
                    both_buttons_visible = are_both_buttons_visible(driver, timeout=4)
                    debug_notes.append(
                        f"buttons visible after reload: {both_buttons_visible}"
                    )

                if not both_buttons_visible:
                    debug_notes.append("buttons missing, retrying overlay dismissal")
                    dismiss_initial_overlay(driver, debug_label=label)
                    both_buttons_visible = are_both_buttons_visible(driver, timeout=3)
                    debug_notes.append(
                        f"buttons visible after overlay retry: {both_buttons_visible}"
                    )

                ads_detected = ads_detected or not both_buttons_visible
                if not ads_detected:
                    if wait_for_ads(driver, timeout=2):
                        ads_detected = True
                        debug_notes.append("Monetag elements detected on main page")

                results.append(
                    ClickResult(
                        iteration=iteration,
                        clicked_label=target_label,
                        href=href,
                        ads_detected=ads_detected,
                        both_buttons_visible=both_buttons_visible,
                        popup_urls=popup_urls,
                        debug_notes="; ".join(debug_notes) if debug_notes else None,
                    )
                )

                if ads_detected:
                    print(
                        f"[+] {label}: ad activity observed "
                        f"(clicked='{target_label}', popups={len(popup_urls)})"
                    )
                else:
                    print(
                        f"[-] {label}: no ad activity (clicked='{target_label}')"
                    )
            except Exception as exc:
                results.append(
                    ClickResult(
                        iteration=iteration,
                        clicked_label="<unknown>",
                        href="",
                        ads_detected=False,
                        both_buttons_visible=False,
                        popup_urls=[],
                        error=str(exc),
                    )
                )
                print(f"[!] {label}: error -> {exc}")

                with contextlib.suppress(WebDriverException):
                    driver.switch_to.window(main_handle)
                driver.get(HOME_URL)
                time.sleep(1.5)
                prepare_main_view(driver, f"{label} recovery")

    return results


def main() -> int:
    try:
        results = exercise_navigation()
    except WebDriverException as exc:
        print(f"Failed to initialise Edge WebDriver: {exc}")
        return 1

    issues = [result for result in results if result.error]
    if issues:
        print(f"\nCompleted with {len(issues)} error(s).")
    else:
        detected = [result for result in results if result.ads_detected]
        print(
            f"\n{len(detected)} of {len(results)} interactions surfaced Monetag ad activity."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
