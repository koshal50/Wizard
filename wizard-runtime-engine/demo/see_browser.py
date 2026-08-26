import time
from wizard_kernel.world.browser import BrowserRuntime

br = BrowserRuntime(backend="local", headless=False)   # visible window
br.start()
try:
    print(br.navigate("https://example.com"))          # window opens, loads page
    print(br.snapshot()["snapshot"][:400])             # the ARIA tree the agent "sees"
    br.click("a")                                      # follows the first link
    time.sleep(6)                                      # stay open so you can watch
finally:
    br.stop()