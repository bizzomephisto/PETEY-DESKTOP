# PETEY's web browser

PETEY can use a separate visible Chromium window as a core capability. No addon
or MCP server is needed. It starts disabled.

1. Open **Settings → Tools & integrations → Web browser**.
2. Turn on **Let Petey browse the web**.
3. Click **Open browser**, or ask Petey to browse a website or search the web.
4. If a browser is missing, click **Install Chromium** and wait for the download.

Example requests: “Search the web for the official Blender manual,” “Open
https://example.com,” then “Follow the documentation link.” PETEY's selected chat
model must support tool calls. Automatic search tries Brave and then DuckDuckGo in the visible window.
Choose Automatic, Brave, DuckDuckGo, Bing, or Google using **Search engine**
in the browser settings. Google and other protected sites may show bot checks.
When no usable results can be read, PETEY reports that limitation; complete a
challenge manually or choose another source. Browser-only search cannot guarantee
access to every protected site.

The window opens on the computer running PETEY, including for mobile chat. It is
a separate Chromium/Chrome/Edge window, so you can watch, scroll, and use its
address bar. It does not reuse the owner's normal browser profile or PETEY's
application window. Cookies and sign-ins persist locally in `browser-profile/`
under PETEY's data root. Memory management remains in PETEY; the chat provider
receives selected page text and element descriptions when browser tools run.

Switching access off removes the browser tool and revokes queued operations. It
closes the window after any running action finishes. **Close browser** closes the
window while leaving access enabled, so a later request may reopen it. Browser
access is available to desktop and mobile conversations, not Discord or autonomous
addon events. Closing PETEY or restarting it closes the browser and stops an active
Chromium installer.

PETEY can read page text, follow links, fill ordinary fields, press supported keys,
scroll, go back, and switch tabs. Interactive elements receive fresh refs after
each read/action; old refs cannot target a different page. Password and file fields
are excluded from model actions; enter passwords and select files yourself. There
is no arbitrary JavaScript, shell command, or file-reading browser tool. Page
content is untrusted source material, not instructions to change PETEY's settings.
Some websites may require manual sign-in, consent, or CAPTCHA interaction.

The Python environment needs `playwright>=1.57,<2` from `requirements.txt`.
Playwright's bundled Chromium is preferred; installed Chrome or Edge can be used
when Chromium is missing. The Settings install button downloads Chromium without
blocking chat. Alternatively, use the same Python environment that launches PETEY:

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

On Windows with the standard PETEY virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

Linux requires a desktop display and the browser's system libraries. Missing Linux
libraries can be installed with `python -m playwright install-deps chromium` using
the system's normal administrator permissions.

Policy/API tests: `python -m unittest tests.test_web_browser`. Real visible-browser
checks use a temporary local page and profile:

```bash
PETEY_BROWSER_INTEGRATION=1 python -m unittest tests.test_web_browser.BrowserIntegrationTests
```

For CI, set `PETEY_BROWSER_HEADLESS=1`; this only changes the test driver. Product
browser sessions always use a visible window.
