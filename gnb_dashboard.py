import html
import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from config import (
    DASHBOARD_DESCRIPTION,
    DASHBOARD_DETAIL_COLUMNS,
    DASHBOARD_EMPTY_LINK_SPACER_LINES,
    DASHBOARD_LINK_TABLE_MAX_HEIGHT,
    DASHBOARD_LINK_TABLE_LINK_MIN_WIDTH_PX,
    DASHBOARD_LINK_TABLE_MIN_HEIGHT,
    DASHBOARD_LINK_TABLE_NO_WIDTH_PX,
    DASHBOARD_LINK_TABLE_ROW_HEIGHT,
    DASHBOARD_LINK_TABLE_TEXT_MIN_WIDTH_PX,
    DASHBOARD_MENU_BUTTON_LINE_MAX_CHARS,
    DASHBOARD_MENU_COLUMNS,
    DASHBOARD_MENU_HEADER_GAP_REM,
    DASHBOARD_MENU_HEADER_HEIGHT_PX,
    DASHBOARD_MENU_LINK_ROW_BACKGROUND,
    DASHBOARD_NARROW_SCREEN_WIDTH_PX,
    DASHBOARD_SIDEBAR_WIDTH_PX,
    DASHBOARD_TITLE,
    DASHBOARD_TRANSLATION_NOTICE,
    GNB_OUTPUT_DIR,
)
SELECTED_MENU_STATE_KEY = "selected_menu_index"
SELECTED_JSON_STATE_KEY = "selected_json_path"
EMPTY_MENU_LABEL = "(empty menu)"


st.set_page_config(
    page_title=DASHBOARD_TITLE,
    layout="wide",
)


def apply_page_styles() -> None:
    """Apply small layout overrides for the dashboard."""
    st.markdown(
        f"""
        <style>
        [data-testid="stSidebar"] {{
            min-width: {DASHBOARD_SIDEBAR_WIDTH_PX}px;
            max-width: {DASHBOARD_SIDEBAR_WIDTH_PX}px;
        }}
        [data-testid="stSidebar"] h1 {{
            font-size: 2rem;
        }}
        [data-testid="stSidebar"] hr {{
            margin: 0.75rem 0;
        }}
        .status-card {{
            padding: 0.55rem 0;
            border-bottom: 1px solid rgba(49, 51, 63, 0.18);
        }}
        .status-title {{
            font-size: 1.2rem;
            font-weight: 750;
            color: #202124;
            margin-bottom: 0.08rem;
        }}
        .status-value {{
            font-size: 1rem;
            font-weight: 520;
            color: #333;
            overflow-wrap: anywhere;
        }}
        div[data-testid="stSelectbox"] label {{
            font-size: 1.28rem;
            font-weight: 650;
            color: #1f2937;
        }}
        div[data-baseweb="select"] > div {{
            min-height: 48px;
            border-radius: 12px;
            border-color: rgba(15, 23, 42, 0.22);
        }}
        div[data-testid="stButton"] > button {{
            min-height: 86px;
            max-height: 86px;
            padding: 0.55rem 0.7rem;
            font-size: 1rem;
            font-weight: 560;
            line-height: 1.28;
            overflow: hidden;
        }}
        /* Streamlit renders a button label inside a paragraph, so preserve its newlines there. */
        div[data-testid="stButton"] > button p {{
            white-space: pre-line !important;
            margin: 0;
        }}
        .detail-panel-title {{
            font-size: 1.08rem;
            font-weight: 750;
            margin-bottom: 0.55rem;
        }}
        .menus-heading {{
            margin: 0;
            padding: 0;
        }}
        .menu-detail-title {{
            font-size: 1.6rem;
            font-weight: 750;
            min-height: {DASHBOARD_MENU_HEADER_HEIGHT_PX}px;
            display: flex;
            align-items: center;
            line-height: 1.25;
            margin: 0;
            white-space: nowrap;
        }}
        .menu-header-gap {{
            height: {DASHBOARD_MENU_HEADER_GAP_REM}rem;
        }}
        @media (max-width: {DASHBOARD_NARROW_SCREEN_WIDTH_PX}px) {{
            [data-testid="stSidebar"] {{
                min-width: 360px;
                max-width: 360px;
            }}
            div[data-testid="stButton"] > button {{
                min-height: 78px;
                max-height: 78px;
                font-size: 0.95rem;
                padding: 0.45rem 0.55rem;
            }}
            .menu-detail-title {{
                font-size: 1.35rem;
                line-height: 1.25;
            }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def list_json_files() -> list[Path]:
    """Return captured GNB JSON files, newest first."""
    if not GNB_OUTPUT_DIR.exists():
        return []
    return sorted(
        GNB_OUTPUT_DIR.glob("*/*/*_gnb.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def parse_path_info(path: Path) -> tuple[str, str]:
    """Read country and run label from capture_gnb/{country}/{run_label}/file.json."""
    relative = path.relative_to(GNB_OUTPUT_DIR)
    return relative.parts[0], relative.parts[1]


def group_by_country(paths: list[Path]) -> dict[str, list[Path]]:
    """Group JSON files by output folder country code."""
    grouped: dict[str, list[Path]] = {}
    for path in paths:
        country, _ = parse_path_info(path)
        grouped.setdefault(country, []).append(path)
    return dict(sorted(grouped.items()))


@st.cache_data(show_spinner=False)
def load_payload(path_text: str) -> dict:
    """Load a GNB JSON payload with Streamlit caching."""
    with Path(path_text).open("r", encoding="utf-8") as file:
        return json.load(file)


def group_by_run(paths: list[Path]) -> dict[str, list[Path]]:
    """Group JSON files by run label inside one country."""
    grouped: dict[str, list[Path]] = {}
    for path in paths:
        _, run_label = parse_path_info(path)
        grouped.setdefault(run_label, []).append(path)
    return dict(sorted(grouped.items(), reverse=True))


def make_run_label(run_label: str, paths: list[Path]) -> str:
    """Build a run dropdown label and show file count only when needed."""
    if len(paths) == 1:
        return run_label
    return f"{run_label} ({len(paths)} files)"


def get_menu_title(menu: dict) -> str:
    """Return a display-safe top-level menu title."""
    return menu.get("menu") or EMPTY_MENU_LABEL


def display_label(source_text: str, english_text: str = "") -> str:
    """Show the English translation on the line below when it differs."""
    source = source_text or ""
    translated = english_text or ""
    if not translated or translated.casefold() == source.casefold():
        return source
    return f"{source}\n({translated})"


def get_menu_display_title(menu: dict) -> str:
    """Return a top-level menu title with an optional English translation."""
    return display_label(get_menu_title(menu), menu.get("menuEnglish", ""))


def screenshot_path_for_menu(json_path: Path, menu: dict) -> Path | None:
    """Resolve the hover screenshot path recorded in the selected JSON."""
    screenshot = menu.get("hoverScreenshot")
    if not screenshot:
        return None
    return json_path.parent / screenshot


def payload_counts(payload: dict) -> tuple[int, int]:
    """Return menu count and total hover item count for a payload."""
    menus = payload.get("menus") or []
    total_items = sum(len(menu.get("hoverItems") or []) for menu in menus)
    return len(menus), total_items


def status_items(payload: dict) -> list[tuple[str, str]]:
    """Return sidebar status rows for the selected payload."""
    menu_count, total_items = payload_counts(payload)
    return [
        ("URL", payload.get("url", "")),
        ("Menus", str(menu_count)),
        ("Hover Items", str(total_items)),
    ]


def render_sidebar_status(payload: dict) -> None:
    """Render selected capture status in the sidebar."""
    st.sidebar.title("Status")
    for title, value in status_items(payload):
        st.sidebar.markdown(status_card_html(title, value), unsafe_allow_html=True)


def status_card_html(title: str, value: str) -> str:
    """Build one sidebar status row."""
    return f"""
    <div class="status-card">
        <div class="status-title">{html.escape(title)}</div>
        <div class="status-value">{html.escape(value)}</div>
    </div>
    """


def render_link_table(menu: dict) -> None:
    """Render hover item text and links for one selected menu."""
    rows = link_rows(menu)
    if not rows:
        render_empty_link_state()
        return

    components.html(
        resizable_link_table_html(rows),
        height=link_table_height(len(rows)),
        scrolling=False,
    )


def resizable_link_table_html(rows: list[dict]) -> str:
    """Build a table with a fixed No column and a draggable Text/Link divider."""
    body_rows = "".join(resizable_link_table_row_html(row) for row in rows)
    return f"""
    <!doctype html>
    <html>
    <head>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ margin: 0; font-family: sans-serif; color: #17233b; }}
            .table-wrap {{
                min-height: {DASHBOARD_LINK_TABLE_MIN_HEIGHT}px;
                max-height: {DASHBOARD_LINK_TABLE_MAX_HEIGHT}px;
                overflow: auto;
                border: 1px solid rgba(49, 51, 63, 0.2);
                border-radius: 0.35rem;
            }}
            table {{ width: 100%; border-collapse: collapse; table-layout: fixed; }}
            th, td {{
                height: {DASHBOARD_LINK_TABLE_ROW_HEIGHT}px;
                padding: 0.55rem 0.6rem;
                border-right: 1px solid rgba(49, 51, 63, 0.15);
                border-bottom: 1px solid rgba(49, 51, 63, 0.15);
                vertical-align: top;
                font-size: 0.86rem;
                line-height: 1.35;
            }}
            th {{
                position: relative;
                background: #f7f8fa;
                color: #68707e;
                font-size: 0.78rem;
                font-weight: 500;
                text-align: left;
            }}
            th:last-child, td:last-child {{ border-right: 0; }}
            tbody tr:last-child td {{ border-bottom: 0; }}
            .no {{ text-align: center; }}
            .cell-content {{ overflow: hidden; }}
            .text .source, .text .translation, .link .cell-content {{
                display: block;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }}
            .menu-link-row td {{ background-color: {DASHBOARD_MENU_LINK_ROW_BACKGROUND}; }}
            .column-resizer {{
                position: absolute;
                top: 0;
                right: -4px;
                width: 8px;
                height: 100%;
                cursor: col-resize;
                z-index: 2;
            }}
            .column-resizer:hover, .column-resizer.dragging {{
                background: rgba(30, 102, 245, 0.25);
            }}
        </style>
    </head>
    <body>
        <div class="table-wrap">
            <table id="collected-links-table">
                <colgroup>
                    <col id="no-column" style="width: {DASHBOARD_LINK_TABLE_NO_WIDTH_PX}px">
                    <col id="text-column" style="width: 42%">
                    <col id="link-column">
                </colgroup>
                <thead>
                    <tr>
                        <th class="no">No</th>
                        <th>Text<div class="column-resizer" id="text-link-resizer"></div></th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>{body_rows}</tbody>
            </table>
        </div>
        <script>
            const table = document.getElementById("collected-links-table");
            const resizer = document.getElementById("text-link-resizer");
            const noColumn = document.getElementById("no-column");
            const textColumn = document.getElementById("text-column");
            const linkColumn = document.getElementById("link-column");
            const minTextWidth = {DASHBOARD_LINK_TABLE_TEXT_MIN_WIDTH_PX};
            const minLinkWidth = {DASHBOARD_LINK_TABLE_LINK_MIN_WIDTH_PX};
            let startX = 0;
            let startTextWidth = 0;

            function resizeColumns(event) {{
                const tableWidth = table.getBoundingClientRect().width;
                const noWidth = noColumn.getBoundingClientRect().width;
                const maxTextWidth = tableWidth - noWidth - minLinkWidth;
                const nextTextWidth = Math.max(
                    minTextWidth,
                    Math.min(maxTextWidth, startTextWidth + event.clientX - startX)
                );
                textColumn.style.width = `${{nextTextWidth}}px`;
                linkColumn.style.width = `${{tableWidth - noWidth - nextTextWidth}}px`;
            }}

            function stopResize() {{
                resizer.classList.remove("dragging");
                document.removeEventListener("pointermove", resizeColumns);
                document.removeEventListener("pointerup", stopResize);
            }}

            resizer.addEventListener("pointerdown", (event) => {{
                startX = event.clientX;
                startTextWidth = textColumn.getBoundingClientRect().width;
                resizer.classList.add("dragging");
                resizer.setPointerCapture(event.pointerId);
                document.addEventListener("pointermove", resizeColumns);
                document.addEventListener("pointerup", stopResize);
            }});
        </script>
    </body>
    </html>
    """


def resizable_link_table_row_html(row: dict) -> str:
    """Build one escaped row for the resizable Collected Links table."""
    row_class = "menu-link-row" if row["No"] == 0 else ""
    source, translation = split_translation_label(str(row["Text"]))
    link = str(row["Link"])
    return (
        f'<tr class="{row_class}">'
        f'<td class="no">{row["No"]}</td>'
        f'<td class="text" title="{html.escape(str(row["Text"]))}">'
        f'<div class="cell-content"><span class="source">{html.escape(source)}</span>'
        f'<span class="translation">{html.escape(translation)}</span></div></td>'
        f'<td class="link" title="{html.escape(link)}">'
        f'<div class="cell-content">{html.escape(link)}</div></td>'
        "</tr>"
    )


def split_translation_label(label: str) -> tuple[str, str]:
    """Split a source label from its optional English translation line."""
    source, separator, translation = label.partition("\n")
    return source, translation if separator else ""


def link_rows(menu: dict) -> list[dict]:
    """Build collected link rows, including the top menu URL as row 0."""
    rows: list[dict] = []
    if menu.get("menuHref"):
        rows.append(
            {"No": 0, "Text": get_menu_display_title(menu), "Link": menu["menuHref"]}
        )

    rows.extend(
        {
            "No": index,
            "Text": display_label(item.get("text", ""), item.get("textEnglish", "")),
            "Link": item.get("href", ""),
        }
        for index, item in enumerate(menu.get("hoverItems") or [], start=1)
    )
    return rows


def render_empty_link_state() -> None:
    """Keep the links panel visually stable when no hover items exist."""
    st.info("No hover items were collected for this menu.")
    for _ in range(DASHBOARD_EMPTY_LINK_SPACER_LINES):
        st.write("")


def link_table_height(row_count: int) -> int:
    """Calculate a table height that avoids unnecessary internal scrolling."""
    return max(
        DASHBOARD_LINK_TABLE_MIN_HEIGHT,
        min(
            DASHBOARD_LINK_TABLE_MAX_HEIGHT,
            DASHBOARD_LINK_TABLE_ROW_HEIGHT * (row_count + 1),
        ),
    )


def render_detail_panel_title(title: str) -> None:
    """Render a consistent title inside one bordered detail panel."""
    st.markdown(
        f'<div class="detail-panel-title">{html.escape(title)}</div>',
        unsafe_allow_html=True,
    )


def render_menu_header(menu: dict, index: int) -> None:
    """Render the selected menu title."""
    display_title = html.escape(get_menu_display_title(menu).replace("\n", " "))
    st.markdown(
        f'<div class="menu-detail-title">{index}. {display_title}</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="menu-header-gap"></div>', unsafe_allow_html=True)


def render_menu_card(menu: dict, json_path: Path, index: int) -> None:
    """Render the selected menu with its hover screenshot and link table."""
    with st.container(border=True):
        render_menu_header(menu, index)
        image_col, table_col = st.columns(DASHBOARD_DETAIL_COLUMNS)

        with image_col:
            with st.container(border=True):
                render_detail_panel_title("Hover Screenshot")
                render_hover_screenshot(menu, json_path)

        with table_col:
            with st.container(border=True):
                render_detail_panel_title("Collected Links")
                render_link_table(menu)


def render_hover_screenshot(menu: dict, json_path: Path) -> None:
    """Render the selected menu hover screenshot."""
    screenshot_path = screenshot_path_for_menu(json_path, menu)
    if screenshot_path and screenshot_path.exists():
        st.image(str(screenshot_path), use_container_width=True)
    else:
        st.info("Hover screenshot is not available for this menu.")


def reset_menu_selection_for_json(json_path: Path) -> None:
    """Reset selected menu when the selected JSON file changes."""
    path_text = str(json_path)
    if st.session_state.get(SELECTED_JSON_STATE_KEY) == path_text:
        return

    st.session_state[SELECTED_JSON_STATE_KEY] = path_text
    st.session_state[SELECTED_MENU_STATE_KEY] = 0


def normalize_selected_menu_index(menu_count: int) -> None:
    """Ensure selected menu state exists and points to an available menu."""
    if SELECTED_MENU_STATE_KEY not in st.session_state:
        st.session_state[SELECTED_MENU_STATE_KEY] = 0
    if st.session_state[SELECTED_MENU_STATE_KEY] >= menu_count:
        st.session_state[SELECTED_MENU_STATE_KEY] = 0


def menu_button_label(index: int, menu: dict) -> str:
    """Build a fixed-line menu selector label with shortened long titles."""
    source, translation = split_translation_label(get_menu_display_title(menu))
    item_count = len(menu.get("hoverItems") or [])
    prefix = f"{index}. "
    title_lines = [
        f"{prefix}{shorten_menu_button_line(source, len(prefix))}",
        shorten_menu_button_line(translation) if translation else "",
        f"{item_count} items",
    ]
    return "\n".join(line for line in title_lines if line)


def shorten_menu_button_line(text: str, reserved_chars: int = 0) -> str:
    """Keep a menu button title line within its fixed visual height."""
    max_chars = DASHBOARD_MENU_BUTTON_LINE_MAX_CHARS - reserved_chars
    if len(text) <= max_chars:
        return text
    return f"{text[:max_chars - 3]}..."


def select_menu(menu_index: int) -> None:
    """Update selected menu before Streamlit rerenders button styles."""
    st.session_state[SELECTED_MENU_STATE_KEY] = menu_index


def render_menu_selector(menus: list[dict]) -> int:
    """Render menu selector buttons and return the selected menu index."""
    normalize_selected_menu_index(len(menus))

    st.markdown('<h2 class="menus-heading">Menus</h2>', unsafe_allow_html=True)
    st.caption("Select a hover menu box to review its screenshot and collected links below.")
    st.caption(DASHBOARD_TRANSLATION_NOTICE)

    for start in range(0, len(menus), DASHBOARD_MENU_COLUMNS):
        columns = st.columns(DASHBOARD_MENU_COLUMNS)
        for offset, menu in enumerate(menus[start:start + DASHBOARD_MENU_COLUMNS]):
            menu_index = start + offset
            button_type = (
                "primary"
                if menu_index == st.session_state[SELECTED_MENU_STATE_KEY]
                else "secondary"
            )
            with columns[offset]:
                st.button(
                    menu_button_label(menu_index + 1, menu),
                    key=f"menu-selector-{menu_index}",
                    use_container_width=True,
                    type=button_type,
                    on_click=select_menu,
                    args=(menu_index,),
                )

    return min(st.session_state[SELECTED_MENU_STATE_KEY], len(menus) - 1)


def render_menu_dashboard(payload: dict, json_path: Path) -> None:
    """Render menu selector boxes and one selected menu detail area."""
    menus = payload.get("menus") or []
    if not menus:
        st.warning("No menus were found in this JSON file.")
        return

    selected_index = render_menu_selector(menus)
    st.divider()
    render_menu_card(menus[selected_index], json_path, selected_index + 1)


def resolve_single_json(run_files: list[Path]) -> Path:
    """Pick the JSON file for a country/run. Newest wins if more than one exists."""
    return sorted(run_files, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def render_sidebar_filters(files_by_country: dict[str, list[Path]]) -> Path:
    """Render country/run selectors in the sidebar and return the selected JSON path."""
    render_sidebar_intro()
    st.sidebar.title("Filters")
    selected_country = select_sidebar_country(files_by_country)
    selected_run, runs_by_label = select_sidebar_run(files_by_country[selected_country])
    st.sidebar.divider()

    return resolve_single_json(runs_by_label[selected_run])


def render_sidebar_intro() -> None:
    """Render the dashboard title and short description in the sidebar."""
    st.sidebar.title(DASHBOARD_TITLE)
    st.sidebar.caption(DASHBOARD_DESCRIPTION)
    st.sidebar.divider()


def select_sidebar_country(files_by_country: dict[str, list[Path]]) -> str:
    """Render the country selector and return the selected country code."""
    countries = list(files_by_country)
    return st.sidebar.selectbox(
        "Country",
        countries,
        format_func=lambda country: country.upper(),
    )


def select_sidebar_run(country_files: list[Path]) -> tuple[str, dict[str, list[Path]]]:
    """Render the run selector and return the selected run plus grouped files."""
    runs_by_label = group_by_run(country_files)
    run_labels = list(runs_by_label)
    selected_run = st.sidebar.selectbox(
        "Date / Run",
        run_labels,
        format_func=lambda run_label: make_run_label(run_label, runs_by_label[run_label]),
    )
    return selected_run, runs_by_label


def main() -> None:
    apply_page_styles()

    json_files = list_json_files()
    if not json_files:
        st.warning(f"No GNB JSON files found under: {GNB_OUTPUT_DIR}")
        return

    selected_path = render_sidebar_filters(group_by_country(json_files))
    reset_menu_selection_for_json(selected_path)
    payload = load_payload(str(selected_path))

    render_sidebar_status(payload)
    render_menu_dashboard(payload, selected_path)


if __name__ == "__main__":
    main()
