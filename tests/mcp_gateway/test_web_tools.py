from __future__ import annotations

from pathlib import Path

import httpx

from nouse.mcp_gateway import gateway


def test_web_search_falls_back_to_duckduckgo_html(monkeypatch):
    class _BrokenDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query: str, max_results: int = 5):  # noqa: ARG002
            raise RuntimeError("ddgs unavailable")

    monkeypatch.setattr(gateway, "DDGS", _BrokenDDGS)
    monkeypatch.setattr(
        gateway,
        "_search_duckduckgo_html",
        lambda query, max_results=5: [  # noqa: ARG005
            {
                "title": "Example",
                "href": "https://example.com",
                "body": "fallback result",
            }
        ],
    )

    out = gateway.web_search("example", max_results=3)
    assert out["provider"] == "duckduckgo_html"
    assert out["results"]
    assert out["results"][0]["href"] == "https://example.com"


def test_fetch_url_handles_pdf_content(monkeypatch):
    class _DummyResp:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        text = ""
        content = b"%PDF-1.4 dummy"

        def raise_for_status(self) -> None:
            return None

    class _DummyClient:
        def __init__(self, *args, **kwargs):  # noqa: ARG002
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def get(self, url: str, **kwargs):  # noqa: ARG002
            return _DummyResp()

    monkeypatch.setattr(gateway.httpx, "Client", _DummyClient)
    monkeypatch.setattr(
        gateway,
        "_extract_pdf_from_bytes",
        lambda content, max_chars=4000: {  # noqa: ARG005
            "content": "PDF extracted text",
            "truncated": False,
        },
    )

    out = gateway.fetch_url("https://example.com/paper.pdf")
    assert out["source"] == "direct_fetch_pdf"
    assert out["content"] == "PDF extracted text"
    assert out["truncated"] is False


def test_normalize_duckduckgo_redirect_href():
    href = (
        "//duckduckgo.com/l/?uddg=https%3A%2F%2Fbase76.se%2Fen%2F"
        "&rut=abc"
    )
    out = gateway._normalize_duckduckgo_href(href)
    assert out == "https://base76.se/en/"


def test_read_pdf_text_falls_back_to_extract_text_when_pdftotext_missing(
    tmp_path: Path, monkeypatch
):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    monkeypatch.setattr(gateway.shutil, "which", lambda name: None)
    monkeypatch.setattr(gateway, "extract_text", lambda p: "fallback pdf text")  # noqa: ARG005

    out = gateway._read_pdf_text(pdf, max_chars=1000)
    assert out["content"] == "fallback pdf text"
    assert out["truncated"] is False
