"""Playwright browser manager — shared async context manager for 4A and 4E."""

from __future__ import annotations

import base64
import logging
from types import TracebackType

from playwright.async_api import async_playwright, Browser, Page, Playwright

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages a shared Playwright Chromium instance.

    Usage::

        async with BrowserManager() as bm:
            html = await bm.get_page_html("https://example.com")
            screenshot_b64 = await bm.take_screenshot("https://example.com")
    """

    def __init__(self) -> None:
        self._pw: Playwright | None = None
        self._browser: Browser | None = None
        self.captured_screenshots: list[dict] = []

    async def __aenter__(self) -> "BrowserManager":
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        logger.info("Browser launched")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        logger.info("Browser closed")

    async def _new_page(self) -> Page:
        assert self._browser is not None, "BrowserManager not entered"
        return await self._browser.new_page()

    async def get_page_html(self, url: str, *, wait_ms: int = 1000) -> str:
        """Navigate to URL and return the rendered HTML."""
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="load", timeout=30_000)
            await page.wait_for_timeout(wait_ms)
            return await page.content()
        finally:
            await page.close()

    async def get_page_text(self, url: str) -> str:
        """Navigate to URL and return structured text content (stripped HTML).

        Extracts headings, navigation, links, main content, and semantic
        structure without the full DOM — much cheaper for token usage.
        """
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="load", timeout=30_000)
            result = await page.evaluate(r"""() => {
                const sections = [];

                // Page title and meta
                sections.push('# ' + document.title);
                const desc = document.querySelector('meta[name="description"]');
                if (desc) sections.push('Description: ' + desc.content);

                // Navigation
                const navEls = document.querySelectorAll('nav');
                if (navEls.length) {
                    sections.push('\n## Navigation');
                    navEls.forEach((nav, i) => {
                        const links = [...nav.querySelectorAll('a')].map(a =>
                            `  - [${a.textContent.trim()}](${a.href})`
                        ).filter(l => l.length > 6);
                        if (links.length) sections.push(links.join('\n'));
                    });
                }

                // Headings hierarchy
                const headings = [...document.querySelectorAll('h1,h2,h3,h4')];
                if (headings.length) {
                    sections.push('\n## Content Structure');
                    headings.forEach(h => {
                        const level = parseInt(h.tagName[1]);
                        const indent = '  '.repeat(level - 1);
                        sections.push(`${indent}${h.tagName}: ${h.textContent.trim().slice(0, 120)}`);
                    });
                }

                // Main content text (truncated)
                const main = document.querySelector('main') || document.body;
                const text = main.innerText.slice(0, 3000);
                sections.push('\n## Main Content (truncated)');
                sections.push(text);

                // Interactive elements
                const forms = document.querySelectorAll('form');
                const buttons = document.querySelectorAll('button, [role="button"]');
                const inputs = document.querySelectorAll('input, select, textarea');
                if (forms.length || buttons.length > 2) {
                    sections.push('\n## Interactive Elements');
                    sections.push(`Forms: ${forms.length}, Buttons: ${buttons.length}, Inputs: ${inputs.length}`);
                    [...buttons].slice(0, 10).forEach(b =>
                        sections.push(`  - Button: ${b.textContent.trim().slice(0, 60)}`)
                    );
                }

                // Semantic landmarks
                const landmarks = ['header','main','footer','aside','section','article'];
                const found = landmarks.filter(l => document.querySelector(l));
                if (found.length) {
                    sections.push('\n## Semantic Landmarks: ' + found.join(', '));
                }

                // ARIA roles
                const ariaEls = document.querySelectorAll('[role]');
                if (ariaEls.length) {
                    const roles = [...new Set([...ariaEls].map(e => e.getAttribute('role')))];
                    sections.push('ARIA roles: ' + roles.join(', '));
                }

                return sections.join('\n');
            }""")
            return result
        finally:
            await page.close()

    async def discover_links(self, url: str, *, same_origin: bool = True) -> list[dict[str, str]]:
        """Discover navigation links on a page.

        Returns a list of {url, text} dicts for internal links found in
        nav elements and the main content area.
        """
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="load", timeout=30_000)
            links = await page.evaluate("""(sameOrigin) => {
                const origin = window.location.origin;
                const seen = new Set();
                const results = [];

                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    if (!href || href.startsWith('javascript:') || href.startsWith('#')) return;
                    if (sameOrigin && !href.startsWith(origin)) return;
                    if (seen.has(href)) return;
                    seen.add(href);

                    const text = a.textContent.trim().slice(0, 80);
                    if (text) results.push({url: href, text});
                });

                return results.slice(0, 30);
            }""", same_origin)
            return links
        finally:
            await page.close()

    async def take_screenshot(self, url: str) -> list[str]:
        """Navigate to URL and return viewport-height tiles of the full page as base64 JPEG strings.

        Also captures a single full-page image (not sent to the model) for
        use in the HTML dashboard.
        """
        page = await self._new_page()
        try:
            await page.set_viewport_size({"width": 1280, "height": 800})
            await page.goto(url, wait_until="load", timeout=30_000)
            page_height = await page.evaluate("() => document.body.scrollHeight")
            tile_height = 800
            tiles: list[str] = []
            for y in range(0, page_height, tile_height):
                await page.evaluate(f"window.scrollTo(0, {y})")
                await page.wait_for_timeout(100)
                raw = await page.screenshot(full_page=False, type="jpeg", quality=70)
                tiles.append(base64.b64encode(raw).decode())

            # Single full-page capture for the dashboard
            await page.evaluate("window.scrollTo(0, 0)")
            full_raw = await page.screenshot(full_page=True, type="jpeg", quality=80)
            full_page_b64 = base64.b64encode(full_raw).decode()

            self.captured_screenshots.append({
                "url": url, "tiles": tiles, "full_page": full_page_b64,
            })
            return tiles
        finally:
            await page.close()

    async def extract_css(self, url: str) -> str:
        """Extract all CSS custom properties and computed styles from a page."""
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="load", timeout=30_000)
            css_data = await page.evaluate("""() => {
                const root = getComputedStyle(document.documentElement);
                const props = {};
                for (const sheet of document.styleSheets) {
                    try {
                        for (const rule of sheet.cssRules) {
                            if (rule.style) {
                                for (let i = 0; i < rule.style.length; i++) {
                                    const name = rule.style[i];
                                    if (name.startsWith('--')) {
                                        props[name] = rule.style.getPropertyValue(name).trim();
                                    }
                                }
                            }
                        }
                    } catch (e) {
                        // Cross-origin stylesheet, skip
                    }
                }
                // Cap custom properties at 50 entries
                const entries = Object.entries(props);
                const capped = Object.fromEntries(entries.slice(0, 50));
                return {
                    custom_properties: capped,
                    custom_properties_total: entries.length,
                    fonts: root.fontFamily,
                    colors: {
                        background: root.backgroundColor,
                        color: root.color,
                    }
                };
            }""")
            import json
            return json.dumps(css_data, indent=2)
        finally:
            await page.close()

    async def run_axe(self, url: str) -> str:
        """Run axe-core accessibility audit on a page.

        Injects axe-core from CDN and returns slimmed-down results
        (top 20 violations by severity with node counts only).
        """
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="load", timeout=30_000)
            # Inject axe-core
            await page.add_script_tag(
                url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
            )
            results = await page.evaluate("() => axe.run()")
            import json

            severity_order = {"critical": 0, "serious": 1, "moderate": 2, "minor": 3}
            all_violations = results.get("violations", [])
            violations = sorted(
                all_violations,
                key=lambda v: severity_order.get(v.get("impact", "minor"), 4),
            )[:20]
            slim = [
                {
                    "id": v["id"],
                    "impact": v["impact"],
                    "description": v["description"],
                    "help": v["help"],
                    "helpUrl": v["helpUrl"],
                    "nodes_affected": len(v.get("nodes", [])),
                }
                for v in violations
            ]
            return json.dumps(
                {"violations": slim, "total_violations": len(all_violations)}
            )
        finally:
            await page.close()

    async def measure_vitals(self, url: str) -> str:
        """Measure basic performance metrics for a page."""
        page = await self._new_page()
        try:
            await page.goto(url, wait_until="load", timeout=30_000)
            metrics = await page.evaluate("""() => {
                const nav = performance.getEntriesByType('navigation')[0];
                const paint = performance.getEntriesByType('paint');
                const lcp = new Promise(resolve => {
                    new PerformanceObserver(list => {
                        const entries = list.getEntries();
                        resolve(entries[entries.length - 1]?.startTime || null);
                    }).observe({type: 'largest-contentful-paint', buffered: true});
                    setTimeout(() => resolve(null), 5000);
                });
                return {
                    dom_content_loaded: nav?.domContentLoadedEventEnd,
                    load_complete: nav?.loadEventEnd,
                    first_paint: paint.find(p => p.name === 'first-paint')?.startTime,
                    first_contentful_paint: paint.find(p => p.name === 'first-contentful-paint')?.startTime,
                    transfer_size: nav?.transferSize,
                    dom_interactive: nav?.domInteractive,
                };
            }""")
            import json
            return json.dumps(metrics, indent=2)
        finally:
            await page.close()
