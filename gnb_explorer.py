import argparse
import asyncio
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from playwright.async_api import async_playwright

from config import (
    BROWSER_CONTEXT_OPTIONS,
    COOKIE_APPEAR_WAIT_MS,
    DEEPL_API_KEY_ENV,
    DEEPL_ENGLISH_COUNTRY_CODES,
    DEEPL_FREE_TRANSLATE_URL,
    DEEPL_REQUEST_TIMEOUT_SECONDS,
    DEEPL_SOURCE_ONLY_COUNTRY_CODES,
    DEEPL_TARGET_LANGUAGE,
    DEEPL_TEXTS_PER_REQUEST,
    DEEPL_TRANSLATION_CACHE_PATH,
    DEEPL_TRANSLATION_CONTEXT,
    DESKTOP_VIEWPORT,
    GNB_HOVER_MARKER_ATTRIBUTE,
    GNB_HOVER_MARKER_BORDER,
    GNB_HOVER_MARKER_PADDING_PX,
    GNB_HOVER_MARKER_SELECTOR,
    GNB_HOVER_SCREENSHOT_DIR,
    GNB_HOVER_SCREENSHOT_CLIP,
    GNB_HOVER_SCREENSHOT_EXTENSION,
    GNB_HOVER_SCREENSHOT_QUALITY,
    GNB_HOVER_SCREENSHOT_TYPE,
    GNB_HOVER_ITEM_MAX_TOP,
    GNB_BASELINE_LINK_SELECTOR,
    HOVER_WAIT_MS,
    HOVER_TIMEOUT_MS,
    INITIAL_WAIT_MS,
    GNB_OUTPUT_DIR,
    GNB_ROOT_CANDIDATE_SELECTOR,
    GNB_TRIGGER_INTERACTIVE_SELECTOR,
    MENU_COLLAPSE_WAIT_MS,
    PAGE_LOAD_TIMEOUT_MS,
    GNB_SCOPE_SELECTOR,
    REQUEST_GAP_MS,
    URLS_CSV_PATH,
    country_code_from_url,
    create_country_run_directories,
    cleanup_cookie_overlays,
    dismiss_cookie_banner,
    print_summary,
    resolve_urls_from_args,
    slugify_text,
    slugify_url,
)


LINK_HELPER_SCRIPT = """
const linkOf = (element) => {
    const onclick = element.getAttribute("onclick") || "";
    const onclickMatch = onclick.match(/https?:\\/\\/[^'")\\s]+/);
    if (onclickMatch) return onclickMatch[0];

    const argumentMatch = onclick.match(/openCtaLink(?:Call)?\\(\\s*['"]([^'"]+)['"]/);
    if (argumentMatch) {
        try {
            return new URL(argumentMatch[1], location.origin).href;
        } catch {
            return argumentMatch[1];
        }
    }

    const href = element.href || element.getAttribute("href") || "";
    if (!href || href.toLowerCase().startsWith("javascript:")) return "";
    return href;
};
"""


@dataclass(frozen=True)
class TranslationResult:
    """Translations and cache activity recorded for one page's unique labels."""

    translations: dict[str, str]
    cache_hit_count: int
    cache_saved_count: int
    untranslated_count: int


class DeepLTranslator:
    """Translate GNB labels once and reuse saved results across capture runs."""

    def __init__(self, cache_path: Path, enabled: bool = True) -> None:
        self.cache_path = cache_path
        self.enabled = enabled
        self.api_key = os.getenv(DEEPL_API_KEY_ENV, "").strip() if enabled else ""
        self.translations = self._load_cache()
        self._missing_key_logged = False

    def _load_cache(self) -> dict[str, str]:
        if not self.cache_path.exists():
            return {}

        try:
            with self.cache_path.open("r", encoding="utf-8") as cache_file:
                payload = json.load(cache_file)
            translations = payload.get("translations", {})
            return {
                str(source): str(translated)
                for source, translated in translations.items()
                if source and translated
            }
        except (OSError, json.JSONDecodeError, AttributeError):
            print(f"[translation-cache-invalid] {self.cache_path}")
            return {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_suffix(".tmp")
        payload = {
            "provider": "DeepL API Free",
            "targetLanguage": DEEPL_TARGET_LANGUAGE,
            "translations": dict(sorted(self.translations.items())),
        }
        with temporary_path.open("w", encoding="utf-8") as cache_file:
            json.dump(payload, cache_file, ensure_ascii=False, indent=2)
        temporary_path.replace(self.cache_path)

    async def translate_texts(
        self,
        texts: Iterable[str],
        country_code: str,
    ) -> TranslationResult:
        """Return cached or DeepL-translated English labels for unique source texts."""
        unique_texts = unique_nonempty_texts(texts)
        if not unique_texts:
            return TranslationResult({}, 0, 0, 0)

        if not self.enabled:
            return TranslationResult({}, 0, 0, len(unique_texts))

        cache_hit_count = sum(text in self.translations for text in unique_texts)

        if country_code in DEEPL_ENGLISH_COUNTRY_CODES:
            cache_saved_count = 0
            for text in unique_texts:
                if text not in self.translations:
                    self.translations[text] = text
                    cache_saved_count += 1
            if cache_saved_count:
                self._save_cache()
            return build_translation_result(
                unique_texts,
                self.translations,
                cache_hit_count,
                cache_saved_count,
            )

        missing_texts = [text for text in unique_texts if text not in self.translations]
        if missing_texts and not self.api_key:
            if not self._missing_key_logged:
                print(f"[translation-skipped] Set {DEEPL_API_KEY_ENV} to enable DeepL translation.")
                self._missing_key_logged = True
            return build_translation_result(
                unique_texts,
                self.translations,
                cache_hit_count,
                0,
            )

        cache_saved_count = 0
        for start in range(0, len(missing_texts), DEEPL_TEXTS_PER_REQUEST):
            batch = missing_texts[start:start + DEEPL_TEXTS_PER_REQUEST]
            try:
                translated_batch = await asyncio.to_thread(
                    request_deepl_translations,
                    self.api_key,
                    batch,
                )
            except RuntimeError as exc:
                print(f"[translation-failed] {exc}")
                break

            self.translations.update(zip(batch, translated_batch, strict=True))
            cache_saved_count += len(translated_batch)
            self._save_cache()

        return build_translation_result(
            unique_texts,
            self.translations,
            cache_hit_count,
            cache_saved_count,
        )


def unique_nonempty_texts(texts: Iterable[str]) -> list[str]:
    """Return stripped source labels once while preserving their first-seen order."""
    return list(dict.fromkeys(text.strip() for text in texts if text.strip()))


def build_translation_result(
    texts: list[str],
    translations: dict[str, str],
    cache_hit_count: int,
    cache_saved_count: int,
) -> TranslationResult:
    """Package translated labels and counts for one page-level translation attempt."""
    translated = {text: translations[text] for text in texts if text in translations}
    return TranslationResult(
        translations=translated,
        cache_hit_count=cache_hit_count,
        cache_saved_count=cache_saved_count,
        untranslated_count=len(texts) - len(translated),
    )


def request_deepl_translations(api_key: str, texts: list[str]) -> list[str]:
    """Send one UTF-8 JSON batch to the DeepL API Free translation endpoint."""
    request_body = json.dumps(
        {
            "text": texts,
            "target_lang": DEEPL_TARGET_LANGUAGE,
            "context": DEEPL_TRANSLATION_CONTEXT,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        DEEPL_FREE_TRANSLATE_URL,
        data=request_body,
        headers={
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=DEEPL_REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"DeepL HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"DeepL connection error: {exc.reason}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"DeepL request error: {exc}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError("DeepL returned an invalid translation response.")
    translations = payload.get("translations", [])
    translated_texts = [item.get("text", "").strip() for item in translations]
    if len(translated_texts) != len(texts) or any(not text for text in translated_texts):
        raise RuntimeError("DeepL returned an incomplete translation response.")
    return translated_texts


def build_hover_item_query() -> str:
    """Build the browser-side query used to collect links revealed by hover."""
    return """
    ({ baseline, triggerIndex, scopeSelector }) => {
        const baselineIds = new Set(baseline);
        const trigger = document.querySelector(
            `[data-gnb-explorer-trigger="${triggerIndex}"]`
        );
        const visible = (element) => {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return style.display !== "none" && style.visibility !== "hidden" &&
                Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
        };
        __LINK_HELPER__
        // Preserve repeated items because Samsung panels can expose the same label
        // in different columns or groups.
        const items = [...document.querySelectorAll("a[href]")]
            .filter(visible)
            .filter((element) => {
                const rect = element.getBoundingClientRect();
                return rect.top < Math.min(innerHeight, __HOVER_ITEM_MAX_TOP__);
            })
            .filter((element) => element !== trigger)
            .filter((element) => !baselineIds.has(element.dataset.gnbExplorerId || ""))
            .filter((element) => element.closest(scopeSelector))
            .map((element) => {
                return {
                    text: (element.innerText || element.getAttribute("aria-label") || "")
                        .replace(/\\s+/g, " ").trim(),
                    href: linkOf(element),
                    ariaLabel: element.getAttribute("aria-label") || "",
                };
            })
            .filter((item) => item.text || item.href);

        return items;
    }
    """.replace("__LINK_HELPER__", LINK_HELPER_SCRIPT).replace(
        "__HOVER_ITEM_MAX_TOP__",
        str(GNB_HOVER_ITEM_MAX_TOP),
    )


HOVER_ITEM_QUERY = build_hover_item_query()


HOVER_MARKER_SCRIPT = """
({ triggerIndex, markerAttribute, markerBorder, markerPadding, markerSelector }) => {
    document.querySelectorAll(markerSelector).forEach(
        (element) => element.remove()
    );

    const trigger = document.querySelector(
        `[data-gnb-explorer-trigger="${triggerIndex}"]`
    );
    if (!trigger) return;

    const rect = trigger.getBoundingClientRect();
    const marker = document.createElement("div");
    marker.setAttribute(markerAttribute, "true");
    marker.style.position = "fixed";
    marker.style.left = `${rect.left - markerPadding}px`;
    marker.style.top = `${rect.top - markerPadding}px`;
    marker.style.width = `${rect.width + markerPadding * 2}px`;
    marker.style.height = `${rect.height + markerPadding * 2}px`;
    marker.style.border = markerBorder;
    marker.style.boxSizing = "border-box";
    marker.style.pointerEvents = "none";
    marker.style.zIndex = "2147483647";
    document.body.appendChild(marker);
}
"""


REMOVE_HOVER_MARKER_SCRIPT = """
({ markerSelector }) => {
    document.querySelectorAll(markerSelector).forEach(
        (element) => element.remove()
    );
}
"""


def parse_args() -> argparse.Namespace:
    """Parse CLI options for CSV/test input, headed preview, and hover screenshots."""
    parser = argparse.ArgumentParser(
        description="Inspect a page's desktop GNB using DOM structure and hover changes."
    )
    parser.add_argument(
        "--test",
        metavar="COUNTRY_CODE",
        help="Inspect one test URL, e.g. --test br opens https://www.samsung.com/br/.",
    )
    parser.add_argument("--csv", type=Path, default=URLS_CSV_PATH)
    parser.add_argument("--headed", action="store_true", help="Show the browser while inspecting.")
    parser.add_argument(
        "--preview-wait",
        type=int,
        default=0,
        help="Extra milliseconds to wait after each hover so the opened menu is easier to see.",
    )
    parser.add_argument(
        "--no-hover-screenshots",
        action="store_true",
        help="Do not save screenshots for each hovered GNB menu.",
    )
    parser.add_argument(
        "--no-translation",
        action="store_true",
        help="Skip DeepL translation and save only the collected source labels.",
    )
    parser.add_argument(
        "--translation-cache",
        type=Path,
        default=DEEPL_TRANSLATION_CACHE_PATH,
        help="DeepL translation cache path (default: output/translation_cache.json).",
    )
    parser.add_argument("--output", type=Path, default=GNB_OUTPUT_DIR)
    return parser.parse_args()


async def locate_gnb_root(page) -> dict | None:
    """Find the most likely desktop GNB root using structure, position, and link count."""
    return await page.evaluate(
        """
        (candidateSelector) => {
            const visible = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== "none" &&
                    style.visibility !== "hidden" &&
                    Number(style.opacity || 1) > 0 &&
                    rect.width > 0 && rect.height > 0;
            };
            const candidates = [...new Set(document.querySelectorAll(candidateSelector))]
                .filter(visible)
                .map((element) => {
                    const rect = element.getBoundingClientRect();
                    const interactiveCount = element.querySelectorAll(
                        "a[href], button, [role='button'], [aria-expanded]"
                    ).length;
                    let score = 0;
                    if (element.closest("header")) score += 50;
                    if (element.tagName === "NAV") score += 25;
                    if (element.getAttribute("role") === "navigation") score += 20;
                    if (rect.top <= 180) score += 25;
                    if (rect.width >= innerWidth * 0.6) score += 20;
                    score += Math.min(interactiveCount, 20);
                    score -= Math.max(rect.top, 0) / 100;
                    return { element, rect, score, interactiveCount };
                })
                .filter((entry) => entry.rect.top < innerHeight * 0.4)
                .sort((a, b) => b.score - a.score);

            const best = candidates[0];
            if (!best) return null;

            best.element.setAttribute("data-gnb-explorer-root", "true");
            return {
                selector: best.element.tagName.toLowerCase(),
                role: best.element.getAttribute("role") || "",
                id: best.element.id || "",
                className: typeof best.element.className === "string" ? best.element.className : "",
                score: Math.round(best.score * 10) / 10,
                interactiveCount: best.interactiveCount,
            };
        }
        """,
        GNB_ROOT_CANDIDATE_SELECTOR,
    )


async def open_page_for_inspection(page, url: str) -> None:
    """Open a URL and clear consent UI after giving it time to render."""
    print(f"[open] {url}")
    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
    await page.wait_for_timeout(INITIAL_WAIT_MS + COOKIE_APPEAR_WAIT_MS)
    await dismiss_cookie_banner(page)


async def mark_top_level_triggers(page) -> list[dict]:
    """Mark visible top-level GNB triggers and return their title/link metadata."""
    return await page.evaluate(
        """
        () => {
            const root = document.querySelector("[data-gnb-explorer-root='true']");
            if (!root) return [];

            const visible = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== "none" && style.visibility !== "hidden" &&
                    rect.width >= 16 && rect.height >= 12;
            };
            __LINK_HELPER__
            const rootRect = root.getBoundingClientRect();
            const candidates = [...root.querySelectorAll("__TRIGGER_SELECTOR__")]
                .filter(visible)
                .filter((element) => {
                    const rect = element.getBoundingClientRect();
                    return rect.top <= rootRect.top + Math.min(rootRect.height, 120) &&
                        rect.bottom >= rootRect.top;
                });

            const deduped = [];
            const boxes = [];
            for (const element of candidates) {
                const rect = element.getBoundingClientRect();
                const duplicate = boxes.some((box) =>
                    Math.abs(box.x - rect.x) < 4 && Math.abs(box.y - rect.y) < 4
                );
                if (duplicate) continue;
                boxes.push(rect);
                deduped.push(element);
            }

            return deduped.map((element, index) => {
                element.setAttribute("data-gnb-explorer-trigger", String(index));
                return {
                    index,
                    text: (element.innerText || element.getAttribute("aria-label") || "")
                        .replace(/\\s+/g, " ").trim(),
                    href: linkOf(element),
                    ariaLabel: element.getAttribute("aria-label") || "",
                };
            });
        }
        """.replace("__LINK_HELPER__", LINK_HELPER_SCRIPT).replace(
            "__TRIGGER_SELECTOR__",
            GNB_TRIGGER_INTERACTIVE_SELECTOR,
        )
    )


async def visible_link_ids(page) -> list[str]:
    """Snapshot visible links so hover-revealed GNB links can be isolated."""
    return await page.evaluate(
        """
        () => {
            const visible = (element) => {
                const style = getComputedStyle(element);
                const rect = element.getBoundingClientRect();
                return style.display !== "none" && style.visibility !== "hidden" &&
                    Number(style.opacity || 1) > 0 && rect.width > 0 && rect.height > 0;
            };
            return [...document.querySelectorAll("__BASELINE_LINK_SELECTOR__")]
                .filter(visible)
                .map((element, index) => {
                    if (!element.dataset.gnbExplorerId) {
                        element.dataset.gnbExplorerId = `baseline-${index}`;
                    }
                    return element.dataset.gnbExplorerId;
                });
        }
        """.replace("__BASELINE_LINK_SELECTOR__", GNB_BASELINE_LINK_SELECTOR)
    )


async def capture_hover_screenshot(page, screenshot_path: Path) -> str:
    """Capture the top page area while a GNB hover panel is open."""
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    await page.screenshot(
        path=screenshot_path,
        type=GNB_HOVER_SCREENSHOT_TYPE,
        quality=GNB_HOVER_SCREENSHOT_QUALITY,
        clip=GNB_HOVER_SCREENSHOT_CLIP,
    )
    return screenshot_path.name


async def add_hover_marker(page, trigger: dict) -> None:
    """Draw a red marker around the top-level GNB trigger before screenshot."""
    await page.evaluate(HOVER_MARKER_SCRIPT, hover_marker_payload(trigger))


async def remove_hover_marker(page) -> None:
    """Remove the screenshot-only hover marker overlay."""
    await page.evaluate(
        REMOVE_HOVER_MARKER_SCRIPT,
        {"markerSelector": GNB_HOVER_MARKER_SELECTOR},
    )


def hover_marker_payload(trigger: dict) -> dict:
    """Build options passed to the browser-side hover marker script."""
    return {
        "triggerIndex": trigger["index"],
        "markerAttribute": GNB_HOVER_MARKER_ATTRIBUTE,
        "markerBorder": GNB_HOVER_MARKER_BORDER,
        "markerPadding": GNB_HOVER_MARKER_PADDING_PX,
        "markerSelector": GNB_HOVER_MARKER_SELECTOR,
    }


def build_hover_screenshot_path(
    screenshot_dir: Path | None,
    url_slug: str,
    trigger: dict,
) -> Path | None:
    """Build the screenshot path for one hovered top-level GNB menu."""
    if not screenshot_dir:
        return None

    menu_slug = slugify_text(trigger["text"], fallback=f"menu_{trigger['index']}")
    return screenshot_dir / (
        f"{url_slug}_{trigger['index']:02d}_{menu_slug}"
        f"{GNB_HOVER_SCREENSHOT_EXTENSION}"
    )


def build_menu_result(
    trigger: dict,
    hover_items: list[dict] | None = None,
    hover_screenshot: str = "",
) -> dict:
    """Build the JSON shape for a top-level menu and its hover items."""
    result = {
        "menu": trigger["text"],
        "menuHref": trigger.get("href", ""),
        "menuAriaLabel": trigger.get("ariaLabel", ""),
        "hoverItems": hover_items or [],
    }
    if hover_screenshot:
        result["hoverScreenshot"] = f"{GNB_HOVER_SCREENSHOT_DIR}/{hover_screenshot}"
    return result


async def collect_hover_items(page, trigger: dict, baseline_ids: set[str]) -> list[dict]:
    """Return visible links after hover, preserving repeated panel items."""
    return await page.evaluate(
        HOVER_ITEM_QUERY,
        {
            "baseline": list(baseline_ids),
            "triggerIndex": trigger["index"],
            "scopeSelector": GNB_SCOPE_SELECTOR,
        },
    )


def trigger_locator(page, trigger: dict):
    """Return the locator for a marked top-level GNB trigger."""
    return page.locator(
        f"[data-gnb-explorer-trigger='{trigger['index']}']"
    ).first


async def inspect_hover(
    page,
    trigger: dict,
    baseline_ids: set[str],
    screenshot_path: Path | None = None,
) -> dict:
    """Hover one top-level menu, optionally screenshot it, and collect revealed items."""
    await cleanup_cookie_overlays(page)
    await trigger_locator(page, trigger).hover(timeout=HOVER_TIMEOUT_MS)
    await page.wait_for_timeout(HOVER_WAIT_MS)

    hover_screenshot = ""
    if screenshot_path:
        await add_hover_marker(page, trigger)
        try:
            hover_screenshot = await capture_hover_screenshot(page, screenshot_path)
        finally:
            await remove_hover_marker(page)

    items = await collect_hover_items(page, trigger, baseline_ids)

    return build_menu_result(trigger, items, hover_screenshot)


async def collapse_menu(page) -> None:
    """Move the mouse away so the next hover starts from a neutral GNB state."""
    await page.mouse.move(
        DESKTOP_VIEWPORT["width"] - 5,
        DESKTOP_VIEWPORT["height"] - 5,
    )
    await page.wait_for_timeout(MENU_COLLAPSE_WAIT_MS)


async def collect_menus(
    page,
    triggers: list[dict],
    baseline_ids: set[str],
    screenshot_dir: Path | None = None,
    url_slug: str = "",
    preview_wait_ms: int = 0,
) -> list[dict]:
    """Iterate every top-level trigger and collect hover details."""
    menus: list[dict] = []

    for trigger in triggers:
        menu = build_menu_result(trigger)
        screenshot_path = build_hover_screenshot_path(screenshot_dir, url_slug, trigger)

        try:
            menu = await inspect_hover(page, trigger, baseline_ids, screenshot_path)
        except Exception as exc:
            print(f"[hover-failed] {trigger['text']} :: {exc}")

        menus.append(menu)
        if preview_wait_ms > 0:
            await page.wait_for_timeout(preview_wait_ms)

        await collapse_menu(page)

    return menus


def build_payload(url: str, root: dict, menus: list[dict]) -> dict:
    """Build the final GNB JSON payload for one URL."""
    return {
        "url": url,
        "capturedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "detection": "structure-and-hover-diff",
        "root": root,
        "menus": menus,
    }


async def add_english_labels(
    menus: list[dict],
    translator: DeepLTranslator,
    country_code: str,
) -> None:
    """Add cached English labels to top-level menus and hover items in place."""
    if country_code in DEEPL_SOURCE_ONLY_COUNTRY_CODES:
        print("[translation] skipped=source-language")
        return

    translation_result = await translator.translate_texts(
        translation_source_texts(menus),
        country_code,
    )
    apply_english_labels(menus, translation_result.translations)
    print_translation_summary(translation_result)


def print_translation_summary(result: TranslationResult) -> None:
    """Log cache reuse and cache additions for one captured page."""
    print(
        "[translation] "
        f"cache-hit={result.cache_hit_count}, "
        f"cache-saved={result.cache_saved_count}, "
        f"untranslated={result.untranslated_count}"
    )


def translation_source_texts(menus: Iterable[dict]) -> list[str]:
    """Collect top-level and hover labels that can be sent to DeepL."""
    source_texts: list[str] = []
    for menu in menus:
        source_texts.append(menu.get("menu", ""))
        source_texts.extend(
            item.get("text", "") for item in menu.get("hoverItems", [])
        )
    return source_texts


def apply_english_labels(menus: Iterable[dict], translations: dict[str, str]) -> None:
    """Attach translated menu and hover labels to the existing JSON-ready records."""
    for menu in menus:
        menu_text = menu.get("menu", "")
        if english_text := translations.get(menu_text):
            menu["menuEnglish"] = english_text
        for item in menu.get("hoverItems", []):
            item_text = item.get("text", "")
            if english_text := translations.get(item_text):
                item["textEnglish"] = english_text


async def extract_gnb_payload(
    page,
    url: str,
    country_run_dir: Path,
    capture_hover_screenshots: bool,
    preview_wait_ms: int,
    translator: DeepLTranslator,
) -> dict:
    """Locate the page GNB, hover every top-level trigger, and build the payload."""
    root = await locate_gnb_root(page)
    if not root:
        raise RuntimeError("No structural GNB candidate was found.")

    triggers = await mark_top_level_triggers(page)
    baseline_ids = set(await visible_link_ids(page))
    screenshot_dir = (
        country_run_dir / GNB_HOVER_SCREENSHOT_DIR
        if capture_hover_screenshots
        else None
    )
    menus = await collect_menus(
        page,
        triggers,
        baseline_ids,
        screenshot_dir=screenshot_dir,
        url_slug=slugify_url(url),
        preview_wait_ms=preview_wait_ms,
    )
    await add_english_labels(menus, translator, country_code_from_url(url))

    return build_payload(url, root, menus)


def save_result(payload: dict, url: str, output_dir: Path) -> Path:
    """Save one GNB JSON file in the country/run directory."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{slugify_url(url)}_gnb.json"
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(f"[saved] {output_path}")
    return output_path


async def inspect_page(
    browser,
    url: str,
    country_run_dir: Path,
    capture_hover_screenshots: bool = True,
    preview_wait_ms: int = 0,
    translator: DeepLTranslator | None = None,
) -> Path:
    """Open a page, locate GNB, hover every top-level menu, and save JSON."""
    context = await browser.new_context(**BROWSER_CONTEXT_OPTIONS)
    try:
        page = await context.new_page()
        await open_page_for_inspection(page, url)
        payload = await extract_gnb_payload(
            page,
            url,
            country_run_dir,
            capture_hover_screenshots,
            preview_wait_ms,
            translator or DeepLTranslator(DEEPL_TRANSLATION_CACHE_PATH, enabled=False),
        )
        return save_result(payload, url, country_run_dir)
    finally:
        await context.close()


async def inspect_urls(
    browser,
    urls: list[str],
    args: argparse.Namespace,
    country_run_dirs: dict[str, Path],
    translator: DeepLTranslator,
) -> tuple[int, int]:
    """Inspect every URL and return success/failure counts."""
    success_count = 0
    failure_count = 0

    for index, url in enumerate(urls, start=1):
        print()
        started_at = datetime.now().astimezone().isoformat(timespec="seconds")
        print(f"[start] {index}/{len(urls)} [{started_at}]")
        try:
            country_run_dir = country_run_dirs[country_code_from_url(url)]
            await inspect_page(
                browser,
                url,
                country_run_dir,
                capture_hover_screenshots=not args.no_hover_screenshots,
                preview_wait_ms=args.preview_wait,
                translator=translator,
            )
            success_count += 1
        except Exception as exc:
            failure_count += 1
            print(f"[failed] {url} :: {exc}")

        if index < len(urls):
            await asyncio.sleep(REQUEST_GAP_MS / 1000)

    return success_count, failure_count


async def main() -> None:
    """Entry point for CLI execution."""
    args = parse_args()
    urls = resolve_urls_from_args(args.test, args.csv)
    print(f"[total-urls] {len(urls)}")
    if not urls:
        print_summary(0, 0)
        return

    country_run_dirs = create_country_run_directories(urls, args.output)
    print(f"[output-dir] {args.output}")
    translator = DeepLTranslator(
        args.translation_cache,
        enabled=not args.no_translation,
    )

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=not args.headed)
        try:
            success_count, failure_count = await inspect_urls(
                browser,
                urls,
                args,
                country_run_dirs,
                translator,
            )
        finally:
            await browser.close()

    print_summary(success_count, failure_count)


if __name__ == "__main__":
    asyncio.run(main())
