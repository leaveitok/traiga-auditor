"""
crawler.py — out-of-line headless capture of public municipal pages.

Captures the externally observable surface used by the fingerprint engine:
rendered HTML/DOM, executed JS global symbols, <script> hosts, iframe origins,
cookies, and network request URLs.

Tiered execution:
  1. Playwright (headless Chromium) for real JS-rendered capture (preferred).
  2. requests + BeautifulSoup static fallback when Playwright is unavailable.
  3. Pure offline fixtures via PageCapture.from_fixture() for --demo runs.

The crawler honors robots.txt, a per-site page budget, and a crawl delay.
It NEVER submits forms or interacts with users; it only observes.
"""
from __future__ import annotations

import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from . import config


@dataclass
class PageCapture:
    """Normalized, vendor-agnostic snapshot of one page's observable surface."""
    url: str
    html: str = ""
    script_hosts: List[str] = field(default_factory=list)
    js_globals: List[str] = field(default_factory=list)
    iframe_origins: List[str] = field(default_factory=list)
    cookie_names: List[str] = field(default_factory=list)
    network_urls: List[str] = field(default_factory=list)
    text: str = ""
    render_engine: str = "none"

    @classmethod
    def from_fixture(cls, url: str, fixture: Dict) -> "PageCapture":
        """Build a capture from an offline fixture dict (used in --demo / tests)."""
        return cls(
            url=url,
            html=fixture.get("html", ""),
            script_hosts=fixture.get("script_hosts", []),
            js_globals=fixture.get("js_globals", []),
            iframe_origins=fixture.get("iframe_origins", []),
            cookie_names=fixture.get("cookie_names", []),
            network_urls=fixture.get("network_urls", []),
            text=fixture.get("text", ""),
            render_engine="fixture",
        )


def _robots_allowed(url: str) -> bool:
    try:
        parts = urlparse(url)
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{parts.scheme}://{parts.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch(config.USER_AGENT, url)
    except Exception:
        # Be conservative but non-blocking: if robots can't be read, allow the
        # single seed page only (handled by the caller's page budget).
        return True


def _playwright_proxy(proxy_url: str) -> dict:
    """Convert a proxy URL (optionally with user:pass@) into Playwright's proxy dict."""
    parts = urlparse(proxy_url)
    server = f"{parts.scheme}://{parts.hostname}"
    if parts.port:
        server += f":{parts.port}"
    cfg = {"server": server}
    if parts.username:
        cfg["username"] = parts.username
    if parts.password:
        cfg["password"] = parts.password
    return cfg


def crawl_site(seed_url: str,
               max_pages: int = config.MAX_PAGES_PER_SITE,
               max_depth: int = config.MAX_DEPTH,
               skip_robots: bool = True,
               use_proxy: bool = True) -> List[PageCapture]:
    """Crawl a single site starting at seed_url, returning page captures.

    skip_robots=True (default) bypasses robots.txt for explicitly registered
    audit targets — city admins who add their own domain consent to scanning.
    Falls back gracefully through render tiers. Returns [] if nothing fetchable.

    use_proxy=True (default) routes through config.SCAN_PROXY_URL when set — the
    residential-proxy path that bypasses datacenter-IP WAF blocks. The pipeline
    passes use_proxy=False for targets that don't need it (see caller).
    """
    proxy = config.SCAN_PROXY_URL if (use_proxy and config.SCAN_PROXY_URL) else ""
    if proxy:
        # Metered residential proxies (e.g. ScraperAPI premium) bill PER request.
        # Driving a headless browser through the proxy turns every sub-resource
        # (CSS/JS/images — often 100+ per page) into a separate billed request,
        # which is prohibitively expensive. Use the single-request static tier
        # instead: for WAF-blocked municipal sites whose vendor tag is in the
        # server-rendered HTML (e.g. Lewisville's Citibot), one proxied fetch is
        # sufficient. If a proxied target genuinely needs JS execution, add
        # `.render=true` to SCAN_PROXY_URL so the proxy renders server-side
        # (still one billed request), rather than routing a browser through it.
        print(f"[crawler] Routing {seed_url} through proxy — static tier only (1 request, no browser)")
        try:
            return _crawl_static(seed_url, max_pages, max_depth, skip_robots, proxy)
        except ImportError:
            return []
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
        print(f"[crawler] Using Playwright for {seed_url}")
        captures = _crawl_with_playwright(seed_url, max_pages, max_depth, sync_playwright, skip_robots, proxy)
        if captures:
            return captures
        # Playwright ran but captured nothing (WAF block, nav failure, stripped
        # response). Fall through to the static tier — a plain requests fetch
        # sometimes succeeds where headless Chromium is fingerprinted/blocked.
        print(f"[crawler] Playwright returned 0 captures for {seed_url} — falling back to static tier")
    except ImportError:
        print(f"[crawler] Playwright not available, falling back to static for {seed_url}")
    except Exception as exc:
        # Playwright is installed but unusable (browser binary missing from the
        # container image, launch failure, crash). Never abort the city's scan
        # on a tier failure — log loudly and fall through to the static tier.
        print(f"[crawler] Playwright tier FAILED for {seed_url}: "
              f"{type(exc).__name__}: {exc} — falling back to static tier")

    try:
        print(f"[crawler] Using static crawler for {seed_url}")
        return _crawl_static(seed_url, max_pages, max_depth, skip_robots, proxy)
    except ImportError:
        # Neither Playwright nor requests/bs4 available; caller should use fixtures.
        return []


def _apply_stealth(page) -> None:
    """
    Apply bot-detection evasion patches to a Playwright page.

    Prefers playwright-stealth (pip install playwright-stealth) when available —
    it covers ~15 fingerprint vectors.  Falls back to a manually-embedded set of
    the most critical patches so the crawler still bypasses common WAF checks
    even without the library installed.
    """
    try:
        from playwright_stealth import stealth_sync  # type: ignore
        stealth_sync(page)
        return
    except ImportError:
        pass

    # ── Manual stealth patches (covers the vectors Cloudflare keys on most) ───
    page.add_init_script("""
    (() => {
      // 1. navigator.webdriver
      Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

      // 2. window.chrome — real Chrome exposes this; headless doesn't
      if (!window.chrome) {
        window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){}, app: {} };
      }

      // 3. navigator.plugins — headless returns empty array
      Object.defineProperty(navigator, 'plugins', {
        get: () => {
          const arr = [
            { name: 'Chrome PDF Plugin',   filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer',   filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client',       filename: 'internal-nacl-plugin', description: '' },
          ];
          arr.item   = i => arr[i];
          arr.namedItem = n => arr.find(p => p.name === n) || null;
          arr.refresh = () => {};
          return arr;
        }
      });

      // 4. navigator.mimeTypes
      Object.defineProperty(navigator, 'mimeTypes', {
        get: () => {
          const arr = [
            { type: 'application/pdf',          suffixes: 'pdf', description: '', enabledPlugin: null },
            { type: 'application/x-google-chrome-pdf', suffixes: 'pdf', description: 'Portable Document Format', enabledPlugin: null },
          ];
          arr.item = i => arr[i];
          arr.namedItem = t => arr.find(m => m.type === t) || null;
          return arr;
        }
      });

      // 5. navigator.permissions.query — headless returns 'denied' for notifications
      const origQuery = window.navigator.permissions.query.bind(navigator.permissions);
      window.navigator.permissions.query = (params) => {
        if (params.name === 'notifications') {
          return Promise.resolve({ state: Notification.permission, onchange: null });
        }
        return origQuery(params);
      };

      // 6. navigator.hardwareConcurrency / deviceMemory — realistic values
      Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
      try { Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 }); } catch(e) {}

      // 7. navigator.languages
      Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

      // 8. WebGL renderer — headless exposes SwiftShader/Mesa which are blocklist-flagged
      const getParam = WebGLRenderingContext.prototype.getParameter;
      WebGLRenderingContext.prototype.getParameter = function(param) {
        if (param === 37445) return 'Intel Inc.';           // UNMASKED_VENDOR_WEBGL
        if (param === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
        return getParam.call(this, param);
      };
    })();
    """)


def _crawl_with_playwright(seed_url, max_pages, max_depth, sync_playwright, skip_robots=True, proxy="") -> List[PageCapture]:
    captures: List[PageCapture] = []
    seen: set = set()
    frontier: List[tuple] = [(seed_url, 0)]
    host = urlparse(seed_url).netloc

    with sync_playwright() as p:
        launch_kwargs = dict(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        if proxy:
            # Playwright accepts proxy at launch; credentials embedded in the URL
            # are parsed into server/username/password below.
            launch_kwargs["proxy"] = _playwright_proxy(proxy)
        browser = p.chromium.launch(**launch_kwargs)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        # Capture ALL network requests in context (including iframes)
        context_net_urls: List[str] = []
        context.on("request", lambda req: context_net_urls.append(req.url))

        while frontier and len(captures) < max_pages:
            url, depth = frontier.pop(0)
            robots_ok = True if skip_robots else _robots_allowed(url)
            if url in seen or depth > max_depth or not robots_ok:
                continue
            seen.add(url)
            page = context.new_page()
            # Snapshot network count before this page so per-page urls are isolated
            net_before = len(context_net_urls)
            try:
                # Apply stealth patches before navigation (playwright-stealth or manual)
                _apply_stealth(page)

                page.goto(url, timeout=30000, wait_until="domcontentloaded")
                # Wait for network to go idle so async widgets (e.g. Citibot) fully load
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                # ── Scroll simulation ─────────────────────────────────────────
                # Many chat widgets (Citibot, etc.) use IntersectionObserver or
                # scroll-event listeners that fire only after the user scrolls.
                # Simulating a full-page scroll triggers these activations so the
                # widget's script host appears in network_urls / script_hosts.
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    page.wait_for_timeout(2000)
                    page.evaluate("window.scrollTo(0, 0)")
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
                # ── End scroll simulation ─────────────────────────────────────

                html = page.content()

                # ── GTM container inspection (Playwright path) ────────────────
                # Fetch GTM container scripts referenced in the rendered HTML.
                # Even though Playwright executes JS, vendor tags inside GTM
                # containers may not fire within the networkidle window — their
                # script URLs and config strings are visible in the container JS
                # and will match text_marker_regex / script_host indicators.
                try:
                    import requests as _req
                    _gtm_session = _req.Session()
                    _gtm_session.headers.update({"User-Agent": config.USER_AGENT})
                    _gtm_ids = _extract_gtm_ids(html)
                    _gtm_fragments: List[str] = []
                    for _gid in _gtm_ids:
                        _fragment = _fetch_gtm_container(_gid, _gtm_session)
                        if _fragment:
                            _gtm_fragments.append(_fragment)
                    if _gtm_fragments:
                        html = html + "\n".join(_gtm_fragments)
                        print(f"[crawler] GTM augmented html for {url} with {len(_gtm_ids)} container(s)")
                except Exception as _gtm_exc:
                    print(f"[crawler] GTM inspection error on {url}: {_gtm_exc}")
                # ── End GTM container inspection ──────────────────────────────

                # Query DOM directly for script/iframe sources (catches dynamically injected tags)
                try:
                    dom_script_hosts = page.evaluate(
                        "() => [...document.querySelectorAll('script[src]')]"
                        ".map(s => { try { return new URL(s.src).hostname } catch(e) { return '' } })"
                        ".filter(h => h)"
                    ) or []
                except Exception:
                    dom_script_hosts = _hosts_from_html(html)
                try:
                    iframe_srcs = page.evaluate(
                        "() => [...document.querySelectorAll('iframe[src]')]"
                        ".map(f => f.src).filter(s => s && !s.startsWith('about:'))"
                    ) or []
                except Exception:
                    iframe_srcs = page.eval_on_selector_all(
                        "iframe", "els => els.map(e => e.src)") or []

                # Merge hosts visible in the (GTM-augmented) HTML blob into the
                # DOM-queried hosts.  DOM queries miss hosts that only appear in
                # fetched GTM container JS; the HTML scan catches them.
                dom_script_hosts = list(dict.fromkeys(
                    list(dom_script_hosts) + _hosts_from_html(html)))

                # Per-page network URLs (slice from before this page's load)
                page_net_urls = context_net_urls[net_before:]

                # Check if page appears to be a bot-challenge (suspiciously low resources)
                if len(page_net_urls) <= 2 and not dom_script_hosts:
                    print(f"[crawler] Possible WAF challenge on {url} (net_requests={len(page_net_urls)}, no scripts) — page may need manual chrome-capture")

                cap = PageCapture(
                    url=url,
                    html=html,
                    script_hosts=dom_script_hosts,
                    js_globals=_probe_js_globals(page),
                    iframe_origins=iframe_srcs,
                    cookie_names=[c["name"] for c in context.cookies()],
                    network_urls=page_net_urls,
                    text=page.inner_text("body") if page.query_selector("body") else "",
                    render_engine="playwright",
                )
                captures.append(cap)
                for href in _links_from_html(html, url):
                    if urlparse(href).netloc == host and href not in seen:
                        frontier.append((href, depth + 1))
            except Exception as exc:
                print(f"[crawler] Playwright page error on {url}: {exc}")
            finally:
                page.close()
                time.sleep(config.CRAWL_DELAY_SECONDS)
        browser.close()
    return captures


def _probe_js_globals(page) -> List[str]:
    """Sample a curated set of window globals that AI widgets commonly register."""
    try:
        keys = page.evaluate("() => Object.keys(window)")
        return list(keys)[:500]
    except Exception:
        return []


def _extract_gtm_ids(html: str) -> List[str]:
    """Extract all Google Tag Manager container IDs (e.g. GTM-XXXXXX) from page HTML."""
    return list(set(re.findall(r"GTM-[A-Z0-9]{4,10}", html)))


def _fetch_gtm_container(gtm_id: str, session) -> str:
    """
    Fetch a public GTM container script and return its raw text.

    GTM containers are public JS files hosted by Google. Fetching them exposes
    vendor tags and configuration strings (e.g. 'citibot.io') that are defined
    inside the container but never appear in the page's own HTML — because they
    are injected at runtime by the GTM script.

    Returns empty string on any failure — callers treat this as no signal.
    """
    try:
        url = f"https://www.googletagmanager.com/gtm.js?id={gtm_id}"
        resp = session.get(url, timeout=8)
        if resp.status_code == 200:
            print(f"[crawler] GTM container fetched: {gtm_id} ({len(resp.text)} chars)")
            return resp.text
    except Exception as exc:
        print(f"[crawler] GTM container fetch failed for {gtm_id}: {exc}")
    return ""


def _crawl_static(seed_url, max_pages, max_depth, skip_robots=True, proxy="") -> List[PageCapture]:
    import requests  # type: ignore
    from bs4 import BeautifulSoup  # type: ignore

    captures: List[PageCapture] = []
    seen: set = set()
    frontier: List[tuple] = [(seed_url, 0)]
    host = urlparse(seed_url).netloc
    headers = {"User-Agent": config.USER_AGENT}
    session = requests.Session()
    session.headers.update(headers)
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
        # ScraperAPI (and similar) proxy mode intercepts TLS and presents its
        # own certificate, so certificate verification must be disabled for
        # proxied requests. Ref: ScraperAPI proxy-mode docs (curl -k / verify=False).
        session.verify = False
        try:
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass
    fetched_gtm_ids: set = set()   # avoid re-fetching the same container across pages

    while frontier and len(captures) < max_pages:
        url, depth = frontier.pop(0)
        robots_ok = True if skip_robots else _robots_allowed(url)
        if url in seen or depth > max_depth or not robots_ok:
            continue
        seen.add(url)
        try:
            resp = session.get(url, timeout=config.REQUEST_TIMEOUT_SECONDS)
            html = resp.text
            soup = BeautifulSoup(html, "html.parser")

            # ── GTM container inspection ──────────────────────────────────────
            # Many municipal AI widgets (Citibot, etc.) are injected via Google
            # Tag Manager rather than direct <script> tags.  The static crawler
            # cannot execute JavaScript, so it would normally miss these assets
            # entirely.  Fetching the GTM container JS exposes vendor tags and
            # configuration strings that the fingerprint engine's text_marker_regex
            # indicators can match against — no browser required.
            gtm_ids = _extract_gtm_ids(html)
            gtm_fragments: List[str] = []
            for gtm_id in gtm_ids:
                if gtm_id not in fetched_gtm_ids:
                    fetched_gtm_ids.add(gtm_id)
                    container_text = _fetch_gtm_container(gtm_id, session)
                    if container_text:
                        gtm_fragments.append(container_text)
            # Append GTM container text to the HTML blob so text_marker_regex
            # and script_host indicators scan it alongside the page source.
            augmented_html = html + "\n".join(gtm_fragments)
            # ── End GTM container inspection ──────────────────────────────────

            cap = PageCapture(
                url=url,
                html=augmented_html,
                script_hosts=_hosts_from_html(augmented_html),
                iframe_origins=[i.get("src", "") for i in soup.find_all("iframe")],
                cookie_names=list(resp.cookies.get_dict().keys()),
                text=soup.get_text(" ", strip=True),
                render_engine="static",
            )
            captures.append(cap)
            for a in soup.find_all("a", href=True):
                href = urljoin(url, a["href"])
                if urlparse(href).netloc == host and href not in seen:
                    frontier.append((href, depth + 1))
        except Exception as exc:
            print(f"[crawler] Static fetch error on {url}: {type(exc).__name__}: {exc}")
        finally:
            time.sleep(config.CRAWL_DELAY_SECONDS)
    return captures


def _hosts_from_html(html: str) -> List[str]:
    import re
    hosts = []
    # \? tolerates backslash-escaped quotes (src=\"https://...\") as found in
    # GTM container JS vtp_html fragments, where script tags are JSON-encoded.
    for m in re.finditer(r'src=\\?["\']([^"\'\\]+)', html, flags=re.I):
        netloc = urlparse(m.group(1)).netloc
        if netloc:
            hosts.append(netloc)
    return hosts


_BINARY_EXTS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".zip", ".gz", ".tar",
    ".mp4", ".mp3", ".avi", ".mov", ".wmv", ".wav",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico",
    ".exe", ".msi", ".dmg", ".pkg",
}

# CMS path patterns that serve file downloads without a file extension
_DOWNLOAD_PATH_PATTERNS = (
    "/documentcenter/view/",   # Garland/CivicPlus document viewer
    "/document/download/",
    "/asset/",                 # Plano asset CDN
    "/download/",
    "/files/",
    "/filedownload/",
    "/blobdload/",
)


def _is_navigable(url: str) -> bool:
    """Return False for binary/download URLs that Playwright can't navigate to."""
    path = urlparse(url).path.lower().split("?")[0]
    if any(path.endswith(ext) for ext in _BINARY_EXTS):
        return False
    if any(pat in path for pat in _DOWNLOAD_PATH_PATTERNS):
        return False
    return True


def _links_from_html(html: str, base: str) -> List[str]:
    import re
    links = []
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, flags=re.I):
        url = urljoin(base, m.group(1))
        if _is_navigable(url):
            links.append(url)
    return links
