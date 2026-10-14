"""Create one isolated agent-browser session for an investigation."""
from wizard_kernel.world.browser.runtime import BrowserRuntime


def get_browser(options: dict) -> BrowserRuntime:
    return BrowserRuntime(backend=options.get("browser_backend", "local"),
                          cdp_url=options.get("browser_cdp_url"),
                          headless=options.get("browser_headless", True),
                          allowed_domains=options.get("allowed_domains") or [])
