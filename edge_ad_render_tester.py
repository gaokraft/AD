"""Edge Selenium script to validate ad rendering and interact with Sushi recipe.

This script is intended for local debugging of ad placement. It opens the SweetMuse
homepage in a Microsoft Edge browser (headless by default), cycles through page views,
clicks on the Sushi recipe card and its favourite button, automatically closes
occasional ad popups, and inspects for ad-related elements such as scripts or
iframes. The script relies on Selenium Manager (bundled with Selenium 4.6+) to locate
the Microsoft Edge WebDriver, so no manual driver installation is required. A custom
driver path can still be provided through CLI flags or environment variables when
needed.
"""

import argparse
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import List, Optional, Tuple

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


def setup_logger() -> logging.Logger:
    """Configure a console logger for the test run."""
    logger = logging.getLogger("edge_ad_navigation_test")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def resolve_driver_path(cli_driver_path: Optional[str], logger: logging.Logger) -> Optional[Path]:
    """Return a resolved driver path from CLI flag or environment variables if provided."""
    candidates = [
        cli_driver_path,
        os.environ.get("EDGE_WEBDRIVER"),
        os.environ.get("EDGE_DRIVER_PATH"),
        os.environ.get("MS_EDGE_DRIVER_PATH"),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        driver_path = Path(candidate).expanduser().resolve()
        if driver_path.exists():
            logger.info("Using configured Edge driver at %s", driver_path)
            return driver_path
        logger.warning("Configured driver path %s was not found", driver_path)

    logger.info("No explicit driver path provided; Selenium Manager will resolve the driver")
    return None


def apply_stealth_settings(driver: webdriver.Edge, logger: logging.Logger) -> None:
    """Minimize automation fingerprints so the session resembles a manual browser."""
    try:
        user_agent: str = driver.execute_script("return navigator.userAgent")
        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                           "Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});"
                           "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
                           "const getParameter = Object.getOwnPropertyDescriptor(Notification, 'permission');"
                           "if (getParameter && getParameter.get) {"
                           "  Object.defineProperty(Notification, 'permission', {get: () => 'default'});"
                           "}"
            },
        )
        if "Headless" in user_agent:
            driver.execute_cdp_cmd(
                "Network.setUserAgentOverride",
                {"userAgent": user_agent.replace("Headless", "")},
            )
        logger.info("Applied stealth CDP overrides")
    except WebDriverException as exc:
        logger.debug("Unable to apply stealth settings: %s", exc)


def create_edge_driver(headless: bool, driver_path: Optional[Path], logger: logging.Logger) -> webdriver.Edge:
    """Spin up an Edge WebDriver instance with sensible defaults."""
    options = EdgeOptions()
    options.use_chromium = True
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    if headless:
        options.add_argument("--headless=new")

    logger.info("Launching Microsoft Edge (headless=%s)", headless)
    if driver_path:
        service = EdgeService(executable_path=str(driver_path))
    else:
        service = EdgeService()
    driver = webdriver.Edge(service=service, options=options)
    driver.set_page_load_timeout(60)
    apply_stealth_settings(driver, logger)
    return driver


def wait_for_page_ready(driver: webdriver.Edge, timeout: int = 30, logger: Optional[logging.Logger] = None) -> None:
    """Block until document.readyState is complete or a timeout occurs."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda web_driver: web_driver.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        if logger:
            logger.warning("Timed out waiting for page to reach readyState complete")


def close_unexpected_windows(driver: webdriver.Edge, main_handle: str, logger: logging.Logger) -> str:
    """Close any secondary windows that may have opened (e.g. ad pop-ups)."""
    current_handles = driver.window_handles
    for handle in current_handles:
        if handle == main_handle:
            continue
        driver.switch_to.window(handle)
        logger.info("Closing unexpected window: %s", driver.title or "untitled")
        driver.close()

    if main_handle not in driver.window_handles and driver.window_handles:
        main_handle = driver.window_handles[0]
        driver.switch_to.window(main_handle)
        logger.warning("Main window changed; switched control to handle %s", main_handle)
    else:
        driver.switch_to.window(main_handle)
    return main_handle


def close_ad_popup_if_present(driver: webdriver.Edge, logger: logging.Logger) -> bool:
    """Dismiss modal ad popups that expose a close button labelled 'Закрыть'."""
    popup_locators = [
        (By.XPATH, "/html/body/div[3]/div/div[2]/span"),
        (By.XPATH, "/html/body/div/div"),
        (By.XPATH, "//span[normalize-space()='Закрыть']"),
    ]

    for locator in popup_locators:
        try:
            candidate = WebDriverWait(driver, 2).until(EC.element_to_be_clickable(locator))
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", candidate)
            candidate.click()
            logger.info("Closed ad popup using locator %s", locator)
            return True
        except TimeoutException:
            continue
        except WebDriverException as exc:
            logger.debug("Attempt to close popup with locator %s failed: %s", locator, exc)
            continue

    try:
        fallback_buttons = driver.find_elements(
            By.XPATH,
            "//span[contains(@class, 'close') and contains(translate(text(),'ЗАКРЫТЬ','закрыть'),'закрыть')]",
        )
        for button in fallback_buttons:
            if button.is_displayed() and button.is_enabled():
                button.click()
                logger.info("Closed ad popup via fallback close button search")
                return True
    except WebDriverException as exc:
        logger.debug("Fallback popup close search failed: %s", exc)

    return False


def inspect_for_ad_elements(driver: webdriver.Edge, logger: logging.Logger) -> bool:
    """Look for ad-related script or iframe tags and log what is discovered."""
    ad_keywords = ("ads", "advert", "doubleclick", "googlesyndication", "adservice", "adnxs", "taboola", "outbrain")
    found_elements: List[Tuple[str, str]] = []

    for script_tag in driver.find_elements(By.TAG_NAME, "script"):
        descriptor = (script_tag.get_attribute("src") or script_tag.get_attribute("outerHTML") or "").lower()
        if any(keyword in descriptor for keyword in ad_keywords):
            found_elements.append(("script", descriptor[:160]))

    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
        descriptor = (iframe.get_attribute("src") or iframe.get_attribute("outerHTML") or "").lower()
        if any(keyword in descriptor for keyword in ad_keywords):
            found_elements.append(("iframe", descriptor[:160]))

    if not found_elements:
        logger.warning("Did not detect any ad-related elements on the current view")
        return False

    for element_type, detail in found_elements:
        logger.info("Detected %s with ad signature: %s", element_type, detail)
    return True


def interact_with_sushi_card(driver: webdriver.Edge, wait: WebDriverWait, logger: logging.Logger) -> None:
    """Click the Sushi recipe card to mimic user navigation."""
    sushi_card_locator = (By.CSS_SELECTOR, "div.row[role='option'][data-id='53065']")
    sushi_card = wait.until(EC.element_to_be_clickable(sushi_card_locator))
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", sushi_card)
    sushi_card.click()
    logger.info("Clicked Sushi recipe card")


def toggle_sushi_favourite(driver: webdriver.Edge, wait: WebDriverWait, logger: logging.Logger) -> None:
    """Toggle the Sushi favourite star button if available."""
    fav_button_locator = (By.CSS_SELECTOR, "div.row[role='option'][data-id='53065'] button.fav")
    favourite_button = wait.until(EC.element_to_be_clickable(fav_button_locator))
    driver.execute_script("arguments[0].scrollIntoView({behavior: 'instant', block: 'center'});", favourite_button)
    favourite_button.click()
    logger.info("Clicked Sushi favourite button")


def run_ad_navigation_test(
    iterations: int,
    min_wait: float,
    max_wait: float,
    url: str,
    headless: bool,
    driver_path_override: Optional[str] = None,
) -> None:
    logger = setup_logger()
    if min_wait > max_wait:
        min_wait, max_wait = max_wait, min_wait
        logger.warning("Swapped wait bounds so that min_wait <= max_wait")

    resolved_driver_path = resolve_driver_path(driver_path_override, logger)
    driver: Optional[webdriver.Edge] = None
    max_iterations = iterations if iterations and iterations > 0 else None
    iteration_counter = 1

    try:
        driver = create_edge_driver(headless=headless, driver_path=resolved_driver_path, logger=logger)
        while True:
            loop_descriptor = (
                f"{iteration_counter}/{max_iterations}" if max_iterations else f"{iteration_counter}"
            )
            logger.info("Iteration %s: loading %s", loop_descriptor, url)
            driver.get(url)
            logger.info("Waiting for homepage to become ready")
            main_handle = driver.current_window_handle
            wait_for_page_ready(driver, logger=logger)
            logger.info("Homepage ready")
            close_ad_popup_if_present(driver, logger)
            main_handle = close_unexpected_windows(driver, main_handle, logger)
            wait = WebDriverWait(driver, 20)
            inspect_for_ad_elements(driver, logger)

            try:
                interact_with_sushi_card(driver, wait, logger)
                time.sleep(2)
                close_ad_popup_if_present(driver, logger)
                main_handle = close_unexpected_windows(driver, main_handle, logger)
            except TimeoutException:
                logger.error("Timed out waiting for Sushi recipe card; continuing")
            except WebDriverException as exc:
                logger.error("Error while clicking Sushi recipe card: %s", exc)

            logger.info("Returning to homepage")
            driver.get(url)
            main_handle = driver.current_window_handle
            wait_for_page_ready(driver, logger=logger)
            logger.info("Homepage reloaded")
            close_ad_popup_if_present(driver, logger)
            main_handle = close_unexpected_windows(driver, main_handle, logger)
            wait = WebDriverWait(driver, 20)

            try:
                toggle_sushi_favourite(driver, wait, logger)
                time.sleep(1)
                close_ad_popup_if_present(driver, logger)
                main_handle = close_unexpected_windows(driver, main_handle, logger)
            except TimeoutException:
                logger.error("Timed out waiting for Sushi favourite button; continuing")
            except (NoSuchElementException, WebDriverException) as exc:
                logger.error("Error while clicking Sushi favourite button: %s", exc)

            inspect_for_ad_elements(driver, logger)
            wait_duration = random.uniform(min_wait, max_wait)
            logger.info("Sleeping %.1f seconds before refresh", wait_duration)
            time.sleep(wait_duration)

            logger.info("Refreshing page")
            driver.refresh()
            wait_for_page_ready(driver, logger=logger)
            logger.info("Refresh complete")
            close_ad_popup_if_present(driver, logger)
            main_handle = close_unexpected_windows(driver, main_handle, logger)
            inspect_for_ad_elements(driver, logger)

            if max_iterations and iteration_counter >= max_iterations:
                logger.info("Completed configured iteration count; exiting loop")
                break

            iteration_counter += 1
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received; stopping test loop")
    except WebDriverException as exc:
        logger.exception("WebDriver raised an exception: %s", exc)
        raise
    finally:
        if driver is not None:
            logger.info("Shutting down Edge driver")
            driver.quit()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Edge Selenium ad navigation tester")
    parser.add_argument(
        "--iterations",
        type=int,
        default=0,
        help="Number of navigation loops to perform (0 runs until interrupted)",
    )
    parser.add_argument(
        "--min-wait",
        type=float,
        default=10.0,
        help="Lower bound for wait duration between actions (seconds)",
    )
    parser.add_argument(
        "--max-wait",
        type=float,
        default=30.0,
        help="Upper bound for wait duration between actions (seconds)",
    )
    parser.add_argument("--url", type=str, default="https://sweetmuse.shop/", help="Target URL to test against")
    parser.add_argument("--headed", action="store_true", help="Run browser in headed mode for debugging")
    parser.add_argument(
        "--driver-path",
        type=str,
        default=None,
        help="Optional path to a local msedgedriver executable (overrides Selenium Manager)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    run_ad_navigation_test(
        iterations=max(0, arguments.iterations),
        min_wait=max(0.0, arguments.min_wait),
        max_wait=max(0.0, arguments.max_wait),
        url=arguments.url,
        headless=not arguments.headed,
        driver_path_override=arguments.driver_path,
    )
