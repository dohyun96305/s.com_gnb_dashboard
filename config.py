import csv
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# All timing values are milliseconds unless noted otherwise.
REQUEST_GAP_MS = 2000
PAGE_LOAD_TIMEOUT_MS = 90000
# Time for the homepage and its consent UI to settle before GNB inspection.
INITIAL_WAIT_MS = 2500
COOKIE_APPEAR_WAIT_MS = 1500
COOKIE_SETTLE_MS = 1000
COOKIE_CLICK_TIMEOUT_MS = 1500
HOVER_WAIT_MS = 1300
HOVER_TIMEOUT_MS = 2500
MENU_COLLAPSE_WAIT_MS = 250

# Shared paths. All outputs stay under the project-level output directory.
SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT_DIR = SCRIPT_DIR / "output"
GNB_OUTPUT_DIR = OUTPUT_ROOT_DIR / "capture_gnb"
URLS_CSV_PATH = SCRIPT_DIR / "urls.csv"
DEEPL_TRANSLATION_CACHE_PATH = OUTPUT_ROOT_DIR / "translation_cache.json"

# URL validation and output naming helpers.
URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
SLUG_INVALID_CHARS = re.compile(r"[^A-Za-z0-9_-]+")
SAMSUNG_PATH_CODE_PATTERN = re.compile(r"^[a-z0-9-]{1,10}$", re.IGNORECASE)
RUN_DIRECTORY_ATTEMPTS = 100

# DeepL API Free settings. The key is read only from the DEEPL_API_KEY
# environment variable and is never written to JSON or source files.
DEEPL_API_KEY_ENV = "DEEPL_API_KEY"
DEEPL_FREE_TRANSLATE_URL = "https://api-free.deepl.com/v2/translate"
DEEPL_TARGET_LANGUAGE = "EN-US"
DEEPL_REQUEST_TIMEOUT_SECONDS = 20
DEEPL_TEXTS_PER_REQUEST = 100
DEEPL_ENGLISH_COUNTRY_CODES = {"uk", "us"}
DEEPL_SOURCE_ONLY_COUNTRY_CODES = {"sec"}
DEEPL_TRANSLATION_CONTEXT = (
    "Samsung website global navigation menu labels. "
    "Keep product names and brand names unchanged."
)

# Desktop-only browser baseline used for GNB inspection and hover captures.
DESKTOP_VIEWPORT = {"width": 1440, "height": 2200}

# Captures only the GNB hover area while keeping the page header visible.
GNB_HOVER_SCREENSHOT_WIDTH = 1420
GNB_HOVER_SCREENSHOT_HEIGHT = 700
GNB_HOVER_SCREENSHOT_TYPE = "jpeg"
GNB_HOVER_SCREENSHOT_EXTENSION = ".jpg"
GNB_HOVER_SCREENSHOT_QUALITY = 85
GNB_HOVER_SCREENSHOT_DIR = "hover_screenshots"
GNB_HOVER_SCREENSHOT_CLIP = {
    "x": 0,
    "y": 0,
    "width": min(DESKTOP_VIEWPORT["width"], GNB_HOVER_SCREENSHOT_WIDTH),
    "height": min(DESKTOP_VIEWPORT["height"], GNB_HOVER_SCREENSHOT_HEIGHT),
}
GNB_HOVER_MARKER_BORDER = "4px solid #ff0000"
GNB_HOVER_MARKER_PADDING_PX = 4
GNB_HOVER_MARKER_ATTRIBUTE = "data-gnb-explorer-hover-marker"
GNB_HOVER_MARKER_SELECTOR = f"[{GNB_HOVER_MARKER_ATTRIBUTE}]"
# Hover item collection can look below the saved screenshot area because some
# countries render taller menu panels that still need link extraction.
GNB_HOVER_ITEM_MAX_TOP = 1100
GNB_TRIGGER_INTERACTIVE_SELECTOR = (
    "a[href], button, [role='button'], [aria-expanded], [aria-haspopup]"
)
GNB_BASELINE_LINK_SELECTOR = "a[href]"
GNB_SCOPE_SELECTOR = ", ".join(
    [
        "header",
        "[data-gnb-explorer-root='true']",
        "[class*='gnb' i]",
        "[id*='gnb' i]",
        "[class*='nv00-' i]",
        "[id*='nv00-' i]",
    ]
)
GNB_ROOT_CANDIDATE_SELECTOR = ", ".join(
    [
        "header nav",
        "header [role='navigation']",
        "header [class*='gnb' i]",
        "header [class*='nav' i]",
        "nav",
        "[role='navigation']",
    ]
)

# Dashboard layout settings are centralized here for easy tuning.
DASHBOARD_TITLE = "S.com GNB Dashboard"
DASHBOARD_DESCRIPTION = "Review hover screenshots and collected GNB links."
DASHBOARD_TRANSLATION_NOTICE = (
    "English translations are for reference. Verify local context and product or brand names "
    "before analysis or reporting."
)
DASHBOARD_SIDEBAR_WIDTH_PX = 420
DASHBOARD_MENU_HEADER_HEIGHT_PX = 48
DASHBOARD_MENU_HEADER_GAP_REM = 1
DASHBOARD_DETAIL_COLUMNS = [1.25, 1]
DASHBOARD_MENU_COLUMNS = 4
DASHBOARD_MENU_BUTTON_LINE_MAX_CHARS = 16
DASHBOARD_NARROW_SCREEN_WIDTH_PX = 1200

# Collected Links table settings. Only the Text/Link divider is draggable.
DASHBOARD_LINK_TABLE_MIN_HEIGHT = 520
DASHBOARD_LINK_TABLE_MAX_HEIGHT = 860
DASHBOARD_LINK_TABLE_ROW_HEIGHT = 56
DASHBOARD_LINK_TABLE_NO_WIDTH_PX = 48
DASHBOARD_LINK_TABLE_TEXT_MIN_WIDTH_PX = 110
DASHBOARD_LINK_TABLE_LINK_MIN_WIDTH_PX = 130
DASHBOARD_EMPTY_LINK_SPACER_LINES = 9
DASHBOARD_MENU_LINK_ROW_BACKGROUND = "#eaf7ee"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
BROWSER_CONTEXT_OPTIONS = {
    "user_agent": DEFAULT_USER_AGENT,
    "viewport": DESKTOP_VIEWPORT,
    "device_scale_factor": 1,
}

# Shared consent handling. Prefer explicit reject/decline actions before fallback hiding.
COOKIE_REJECT_SELECTORS = [
    "#onetrust-reject-all-handler",
    "#truste-consent-required",
    "button[data-testid*='reject' i]",
    "button[id*='reject' i]",
    "button[class*='reject' i]",
    "button[id*='decline' i]",
    "button[class*='decline' i]",
    "button[id*='refuse' i]",
    "button[class*='refuse' i]",
    "button[aria-label*='reject' i]",
    "button[aria-label*='decline' i]",
    "button[aria-label*='refuser' i]",
    "button[aria-label*='tout refuser' i]",
]

COOKIE_FALLBACK_HIDE_SCRIPT = """
() => {
    const consentWords = /cookie|consent|privacy|confidentialit|donn.es personnelles/i;
    const selectors = [
        "#onetrust-banner-sdk",
        "#onetrust-consent-sdk",
        "#truste-consent-track",
        "#consent_blackbar",
        "[class*='cookie' i]",
        "[id*='cookie' i]",
        "[class*='consent' i]",
        "[id*='consent' i]",
        "[role='dialog']",
        "[aria-modal='true']",
    ];

    for (const selector of selectors) {
        document.querySelectorAll(selector).forEach((element) => {
            const text = element.innerText || "";
            if (consentWords.test(text) || /onetrust|truste/i.test(element.id + element.className)) {
                element.style.setProperty("display", "none", "important");
                element.style.setProperty("pointer-events", "none", "important");
            }
        });
    }

    for (const element of [document.documentElement, document.body]) {
        element.style.removeProperty("overflow");
        element.style.removeProperty("position");
        element.style.removeProperty("pointer-events");
        element.classList.remove("modal-open", "no-scroll", "overflow-hidden");
    }
}
"""

COOKIE_OVERLAY_CLEANUP_SCRIPT = """
() => {
    const selectors = [
        "#mask[data-mask-target='popupGatherRefuse']",
        "[data-mask-target='popupGatherRefuse']",
        "#popupGatherRefuse",
    ];

    for (const selector of selectors) {
        document.querySelectorAll(selector).forEach((element) => {
            element.style.setProperty("display", "none", "important");
            element.style.setProperty("pointer-events", "none", "important");
            element.setAttribute("aria-hidden", "true");
        });
    }

    for (const element of [document.documentElement, document.body]) {
        element.style.removeProperty("overflow");
        element.style.removeProperty("position");
        element.style.removeProperty("pointer-events");
        element.classList.remove("modal-open", "no-scroll", "overflow-hidden");
    }
}
"""

DIRECT_REJECT_SCRIPT = """
() => {
    const normalize = (text) => (text || "").replace(/\\s+/g, " ").trim().toLowerCase();
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" &&
            style.visibility !== "hidden" &&
            rect.width > 0 &&
            rect.height > 0;
    };

    const rejectPatterns = [
        /decline/i, /reject/i, /refuse/i, /disagree/i, /deny/i,
        /essential only/i, /only necessary/i, /continue without accepting/i,
        /\\uAC70\\uBD80/i, /\\uD544\\uC218\\uB9CC/i, /\\uB3D9\\uC758\\s*\\uC548\\s*\\uD568/i,
        /refuser/i, /rejeter/i,
        /rechazar/i, /denegar/i,
        /ablehnen/i, /nur notwendige/i,
        /recusar/i, /somente necess.rio/i,
        /rifiuta/i, /solo necessari/i,
        /reddet/i, /yaln.zca gerekli/i,
        /afwijzen/i, /alleen noodzakelijke/i,
        /odm.tnout/i, /jen nezbytn/i
    ];

    const acceptPatterns = [
        /accept/i, /agree/i, /allow/i, /ok/i, /got it/i,
        /\\uC218\\uB77D/i, /\\uB3D9\\uC758/i,
        /accepter/i, /autoriser/i,
        /aceptar/i,
        /akzeptieren/i,
        /accetta/i,
        /aceitar/i,
        /aanvaarden/i,
        /souhlas/i
    ];

    const buttons = Array.from(
        document.querySelectorAll("button, a, [role='button'], input[type='button'], input[type='submit']")
    ).filter(isVisible);

    const rankedButtons = buttons
        .map((button) => {
            const label = normalize(
                button.innerText ||
                button.value ||
                button.getAttribute("aria-label") ||
                button.title
            );
            return { button, label };
        })
        .filter(({ label }) => label)
        .filter(({ label }) => rejectPatterns.some((pattern) => pattern.test(label)))
        .filter(({ label }) => !acceptPatterns.some((pattern) => pattern.test(label)))
        .map(({ button, label }) => {
            const root = button.closest(
                "[id*='cookie' i], [class*='cookie' i], [id*='consent' i], [class*='consent' i], [role='dialog'], [aria-modal='true']"
            );
            const score = (root ? 3 : 0) - label.length / 1000;
            return { button, label, score };
        });

    rankedButtons.sort((a, b) => b.score - a.score);
    const best = rankedButtons[0];
    if (!best) return "";
    best.button.click();
    return best.label;
}
"""


def normalize_urls(rows: Iterable[list[str]]) -> list[str]:
    """Return unique valid URL strings from CSV rows."""
    seen: set[str] = set()
    urls: list[str] = []

    for row in rows:
        if not row:
            continue

        url = row[0].strip()
        if not url or url.startswith("#") or not URL_PATTERN.match(url) or url in seen:
            continue

        seen.add(url)
        urls.append(url)

    return urls


def load_urls(csv_path: Path = URLS_CSV_PATH) -> list[str]:
    """Load URLs from the first column of a CSV file."""
    with csv_path.open(newline="", encoding="utf-8") as csv_file:
        return normalize_urls(csv.reader(csv_file))


def samsung_url_from_country_code(country_code: str) -> str:
    """Build a Samsung homepage URL from a path code such as br, de, uk, or sec."""
    return f"https://www.samsung.com/{normalize_samsung_country_code(country_code)}/"


def normalize_samsung_country_code(country_code: str) -> str:
    """Normalize and validate a Samsung URL path code used by --test."""
    normalized_code = country_code.strip().strip("/").lower().replace("_", "-")
    if len(normalized_code) > 10:
        raise ValueError(
            f"Samsung country code must be 10 characters or fewer: {country_code}"
        )
    if not SAMSUNG_PATH_CODE_PATTERN.fullmatch(normalized_code):
        raise ValueError(f"Invalid Samsung country code: {country_code}")
    return normalized_code


def resolve_urls_from_args(test_country_code: str | None, csv_path: Path = URLS_CSV_PATH) -> list[str]:
    """Resolve CLI input into target URLs. --test wins over CSV."""
    if test_country_code:
        return [samsung_url_from_country_code(test_country_code)]
    return load_urls(csv_path)


def print_summary(success_count: int, failure_count: int) -> None:
    print(f"[summary] success={success_count}, failure={failure_count}")


async def dismiss_cookie_banner(page) -> None:
    """Dismiss Samsung consent UI using reject selectors, text matching, then fallback hide."""
    for frame in page.frames:
        for selector in COOKIE_REJECT_SELECTORS:
            try:
                locator = frame.locator(selector).first
                if await locator.count() and await locator.is_visible():
                    await locator.click(timeout=COOKIE_CLICK_TIMEOUT_MS)
                    await page.wait_for_timeout(COOKIE_SETTLE_MS)
                    await cleanup_cookie_overlays(page)
                    print(f"[cookie-dismissed] {selector}")
                    return
            except Exception:
                continue

    for frame in page.frames:
        try:
            label = await frame.evaluate(DIRECT_REJECT_SCRIPT)
            if label:
                await page.wait_for_timeout(COOKIE_SETTLE_MS)
                await cleanup_cookie_overlays(page)
                print(f"[cookie-dismissed] text-match:{label}")
                return
        except Exception:
            continue

    for frame in page.frames:
        try:
            await frame.evaluate(COOKIE_FALLBACK_HIDE_SCRIPT)
        except Exception:
            continue
    await page.wait_for_timeout(COOKIE_SETTLE_MS)
    await cleanup_cookie_overlays(page)
    print("[cookie-dismissed] fallback-hide")


async def cleanup_cookie_overlays(page) -> None:
    """Remove leftover consent overlays that can block Playwright hover/click actions."""
    for frame in page.frames:
        try:
            await frame.evaluate(COOKIE_OVERLAY_CLEANUP_SCRIPT)
        except Exception:
            continue


def create_unique_directory(parent_dir: Path, name: str) -> Path:
    """Create parent/name, adding _02, _03, ... if the directory already exists."""
    run_dir = parent_dir / name
    if not run_dir.exists():
        run_dir.mkdir(parents=True, exist_ok=True)
        return run_dir

    for index in range(2, RUN_DIRECTORY_ATTEMPTS):
        candidate = parent_dir / f"{name}_{index:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate

    raise RuntimeError(f"Could not create a unique directory under {parent_dir}")


def create_run_label() -> str:
    """Return the run timestamp label used under each country folder."""
    return datetime.now().strftime("%Y-%m-%d-%H%M")


def create_country_run_directories(
    urls: Iterable[str],
    base_dir: Path,
    run_label: str | None = None,
) -> dict[str, Path]:
    """Create one run directory per Samsung path/country code for the URL list."""
    label = run_label or create_run_label()
    countries = sorted({country_code_from_url(url) for url in urls})
    return {
        country: create_unique_directory(base_dir / country, label)
        for country in countries
    }


def samsung_path_code_from_url(url: str) -> str:
    """Return the first samsung.com/{code}/ path segment when it is valid."""
    parsed = urlparse(url)
    first_segment = parsed.path.strip("/").split("/", 1)[0]
    try:
        return normalize_samsung_country_code(first_segment)
    except ValueError:
        return ""


def country_code_from_url(url: str) -> str:
    """Infer the storage code from a Samsung URL path or fallback to TLD/global."""
    path_code = samsung_path_code_from_url(url)
    if path_code:
        return path_code

    parsed = urlparse(url)
    top_level_domain = parsed.netloc.lower().split(":", 1)[0].split(".")[-1]
    return top_level_domain if re.fullmatch(r"[a-z]{2}", top_level_domain) else "global"


def slugify_url(url: str) -> str:
    """Create a filesystem-safe filename stem from a URL."""
    parsed = urlparse(url)
    host = parsed.netloc.replace(".", "_")
    path = parsed.path.strip("/").replace("/", "_")
    slug = f"{host}_{path}" if path else host
    return SLUG_INVALID_CHARS.sub("_", slug).strip("_") or "page"


def slugify_text(text: str, fallback: str = "item") -> str:
    """Create a short filesystem-safe filename part from visible text."""
    slug = SLUG_INVALID_CHARS.sub("_", text.strip()).strip("_")
    return slug[:80] or fallback
