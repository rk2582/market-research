"""Page cleaning: remove menus, images and link targets; keep the real content."""

from __future__ import annotations

from tools.page_text import clean_page_text


def test_links_keep_their_text_and_images_keep_useful_alt_text():
    raw = (
        "[Skip to Content](#main)\n"
        "![Monzo logo](/logo.svg)![icon](/a.svg)\n"
        "![Which? Recommended Provider for Current Accounts, 2025](https://img.example/x.png)\n"
        "Open a [free account](https://monzo.com/sign-up) today. See https://monzo.com/legal for terms.\n"
    )
    assert clean_page_text(raw) == (
        "Which? Recommended Provider for Current Accounts, 2025\nOpen a free account today. See for terms."
    )


def test_menus_are_removed_but_short_lists_and_headings_survive():
    menu = "\n".join(f"* [{w}](/{w})" for w in ["Home", "Personal", "Business", "Help", "Blog", "Careers"])
    products = "- Pots\n- Savings\n- Credit"
    raw = f"{menu}\n\n# Spend smarter\n\n{products}\n\nGrow your money with up to 3.65% AER.\n"
    assert (
        clean_page_text(raw)
        == "# Spend smarter\n\n- Pots\n- Savings\n- Credit\n\nGrow your money with up to 3.65% AER."
    )


def test_repeats_boilerplate_and_blank_runs_are_dropped():
    raw = "Sign in\n\n\n\nBank on your terms.\n**\n\nBank on your terms.\nAccept all cookies\nFees: none.\n"
    assert clean_page_text(raw) == "Bank on your terms.\n\nFees: none."


def test_lines_with_numbers_or_sentences_are_not_menu_items():
    raw = "\n".join(["Founded 2015", "Pricing: free", "Teams", "Docs", "Wikis", "Projects", "AI."])
    assert clean_page_text(raw) == raw


def test_empty_text():
    assert clean_page_text("") == ""
