"""Cleans page text from Tavily extract (markdown) before agents see it.

Raw pages are full of menus, image links and long URLs. Removing them saves tokens and lets the
6,000-character cut keep more real content, so the Fact-Checker has better evidence.
"""

from __future__ import annotations

import re

# ![alt](url) — keep the alt text only when it says something (e.g. "Which? Recommended Provider, 2025").
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")  # [text](url) → text
_BARE_URL = re.compile(r"https?://\S+")
_EMPTY_MARKUP = re.compile(r"^[\s*_#>|\-•·]*$")  # lines left with only markup: "**", "#", "- "
_BOILERPLATE = re.compile(
    r"^(skip to (main )?content|sign up|sign in|log ?in|log ?out|menu|close|search|open menu|"
    r"accept( all)?( cookies)?|reject( all)?|cookie (settings|preferences)|back to top)$",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.!?:;]$")
MIN_ALT_WORDS = 4
MENU_WORDS = 4  # a line this short, with no digits or sentence ending, looks like a menu item
MENU_RUN = 6  # this many menu-like lines in a row are treated as a menu and removed (short product lists survive)


def _alt_text(match: re.Match[str]) -> str:
    alt = match.group(1).strip()
    if len(alt.split()) < MIN_ALT_WORDS or re.search(r"\b(icon|logo)\b", alt, re.IGNORECASE):
        return ""
    return f" {alt} "


def _menu_like(line: str) -> bool:
    if line.startswith("#"):  # headings are content
        return False
    words = line.lstrip("-*• ").split()
    return 0 < len(words) <= MENU_WORDS and not any(ch.isdigit() for ch in line) and not _SENTENCE_END.search(line)


def clean_page_text(text: str) -> str:
    """Markdown page → plain, compact text: no images, link targets, menus, repeats or blank runs."""
    text = _IMAGE.sub(_alt_text, text)
    text = _LINK.sub(lambda m: m.group(1), text)
    text = _BARE_URL.sub("", text)

    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if not line:
            if lines and lines[-1]:
                lines.append("")
            continue
        key = line.lower().strip("*_# ")
        if _EMPTY_MARKUP.match(line) or _BOILERPLATE.match(key) or key in seen:
            continue
        seen.add(key)
        lines.append(line)

    return "\n".join(_drop_menus(lines)).strip()


def _drop_menus(lines: list[str]) -> list[str]:
    """Remove runs of MENU_RUN or more short, menu-like lines (blank lines don't break a run)."""
    kept: list[str] = []
    run: list[str] = []

    def flush() -> None:
        content = [line for line in run if line]
        if len(content) < MENU_RUN:
            kept.extend(run)
        run.clear()

    for line in lines:
        if not line or _menu_like(line):
            run.append(line)
        else:
            flush()
            kept.append(line)
    flush()
    # collapse blank lines left behind
    out: list[str] = []
    for line in kept:
        if line or (out and out[-1]):
            out.append(line)
    return out
