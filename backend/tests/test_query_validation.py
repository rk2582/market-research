"""Input rules for the research query (plan §13.1): name vs URL, public http(s) hosts only."""

from __future__ import annotations

import pytest

from db.models.research import InputType
from schemas.api import classify_query


@pytest.mark.parametrize(
    ("raw", "query"),
    [
        ("Notion", "Notion"),
        ("  Notion \n  Labs\t", "Notion Labs"),  # trimmed, whitespace collapsed
        ("Dr. Martens", "Dr. Martens"),  # a dot plus a space → a name, not a domain
        ("AT&T", "AT&T"),
        ("Yahoo!", "Yahoo!"),
        ("javascript:alert(1)", "javascript:alert(1)"),  # no '://' and not a domain → just text to search
        ("Monzo\x00Bank", "Monzo Bank"),  # control characters removed
    ],
)
def test_names(raw: str, query: str):
    info = classify_query(raw)
    assert info.input_type == InputType.NAME
    assert info.query == query and info.website_url is None


@pytest.mark.parametrize(
    ("raw", "url"),
    [
        ("monzo.com", "https://monzo.com"),
        ("Booking.com", "https://booking.com"),
        (
            "https://WWW.Notion.so/Product?x=1#pricing",
            "https://www.notion.so/Product?x=1",
        ),  # host lower-cased, no fragment
        ("http://example.co.uk:8080/about", "http://example.co.uk:8080/about"),
        ("www.monzo.com/about", "https://www.monzo.com/about"),
        ("http://8.8.8.8/", "http://8.8.8.8/"),  # a public IP is allowed
    ],
)
def test_urls_are_normalised(raw: str, url: str):
    info = classify_query(raw)
    assert info.input_type == InputType.URL
    assert info.website_url == url
    assert info.query == raw.strip()


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("", "at least 2"),
        (" a ", "at least 2"),
        ("x" * 301, "under 300"),
        ("ftp://files.example.com", "http:// and https://"),
        ("file:///etc/passwd", "http:// and https://"),
        ("http://localhost:8000", "Local addresses"),
        ("http://api.localhost", "Local addresses"),
        ("printer.local", "Local addresses"),
        ("http://127.0.0.1", "IP addresses"),
        ("http://10.0.0.5/admin", "IP addresses"),
        ("http://192.168.1.1", "IP addresses"),
        ("http://169.254.169.254/latest/meta-data", "IP addresses"),  # cloud metadata address
        ("http://[::1]/", "IP addresses"),
        ("http://0.0.0.0", "IP addresses"),
        ("http://intranet/", "public website address"),
        ("http://0x7f.1/", "public website address"),
        ("http://user:secret@example.com", "username or password"),
        ("https://example.com:99999", "not valid"),
        ("https://", "not valid"),
    ],
)
def test_rejected(raw: str, message: str):
    with pytest.raises(ValueError, match=message):
        classify_query(raw)
