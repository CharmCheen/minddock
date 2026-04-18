from types import SimpleNamespace

import pytest
import httpx

from app.rag.url_loader import _MainTextHTMLParser, fetch_url_content


def test_html_parser_extracts_title_and_main_text() -> None:
    parser = _MainTextHTMLParser()
    parser.feed(
        """
        <html>
          <head><title>Example Title</title></head>
          <body>
            <nav>ignore me</nav>
            <main>
              <h1>Heading</h1>
              <p>Useful article body text with enough characters.</p>
              <p>Another paragraph about retrieval and citations.</p>
            </main>
          </body>
        </html>
        """
    )

    text = parser.get_text()
    assert parser.title == "Example Title"
    assert "Useful article body text" in text
    assert "ignore me" not in text


def test_fetch_url_content_uses_default_safe_ssl(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 200
        text = "<html><head><title>Title</title></head><body><main><p>Readable content for testing.</p></main></body></html>"
        headers = {"content-type": "text/html"}
        url = "https://example.com/final"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.rag.url_loader.get_settings",
        lambda: SimpleNamespace(
            url_fetch_user_agent="MindDockTest/1.0",
            url_fetch_timeout_seconds=5.0,
            url_fetch_retry_count=0,
            url_fetch_retry_backoff_seconds=0.0,
            url_fetch_verify_ssl=True,
            url_fetch_allow_insecure_fallback=False,
        ),
    )

    def fake_get(url: str, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setattr("app.rag.url_loader.httpx.get", fake_get)

    content = fetch_url_content("https://example.com/requested")

    assert content.requested_url == "https://example.com/requested"
    assert content.final_url == "https://example.com/final"
    assert content.status_code == 200
    assert content.ssl_verified is True
    assert captured["kwargs"]["verify"] is True


def test_fetch_url_content_can_insecure_fallback_on_ssl_error(monkeypatch) -> None:
    calls: list[bool] = []

    class Response:
        status_code = 200
        text = "<html><head><title>Title</title></head><body><main><p>Readable content for testing.</p></main></body></html>"
        headers = {"content-type": "text/html"}
        url = "https://example.com/final"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.rag.url_loader.get_settings",
        lambda: SimpleNamespace(
            url_fetch_user_agent="MindDockTest/1.0",
            url_fetch_timeout_seconds=5.0,
            url_fetch_retry_count=0,
            url_fetch_retry_backoff_seconds=0.0,
            url_fetch_verify_ssl=True,
            url_fetch_allow_insecure_fallback=True,
        ),
    )

    def fake_get(url: str, **kwargs):
        calls.append(bool(kwargs["verify"]))
        if kwargs["verify"] is True:
            raise httpx.ConnectError("SSL: CERTIFICATE_VERIFY_FAILED")
        return Response()

    monkeypatch.setattr("app.rag.url_loader.httpx.get", fake_get)

    content = fetch_url_content("https://example.com/requested")

    assert calls == [True, False]
    assert content.ssl_verified is False


def test_fetch_url_content_rejects_non_html(monkeypatch) -> None:
    class Response:
        status_code = 200
        text = "plain text body"
        headers = {"content-type": "application/json"}
        url = "https://example.com/file.json"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.rag.url_loader.get_settings",
        lambda: SimpleNamespace(
            url_fetch_user_agent="MindDockTest/1.0",
            url_fetch_timeout_seconds=5.0,
            url_fetch_retry_count=0,
            url_fetch_retry_backoff_seconds=0.0,
            url_fetch_verify_ssl=True,
            url_fetch_allow_insecure_fallback=False,
        ),
    )
    monkeypatch.setattr("app.rag.url_loader.httpx.get", lambda *args, **kwargs: Response())

    with pytest.raises(RuntimeError, match="non-HTML content"):
        fetch_url_content("https://example.com/file.json")


def test_html_parser_extracts_og_tags(monkeypatch) -> None:
    """OG title, description, image, and canonical are extracted."""
    parser = _MainTextHTMLParser()
    parser.feed(
        """
        <html>
          <head>
            <title>HTML Title</title>
            <meta property="og:title" content="OG Title Is Better" />
            <meta property="og:description" content="This is the article description." />
            <meta property="og:image" content="https://example.com/og-img.jpg" />
            <link rel="canonical" href="https://example.com/canonical-page" />
          </head>
          <body>
            <main><p>Some useful body text for chunking purposes.</p></main>
          </body>
        </html>
        """
    )

    assert parser.og_title == "OG Title Is Better"
    assert parser.og_description == "This is the article description."
    assert parser.og_image == "https://example.com/og-img.jpg"
    assert parser.canonical_url == "https://example.com/canonical-page"
    assert "Some useful body text" in parser.get_text()


def test_fetch_url_content_prefers_og_title_over_html_title(monkeypatch) -> None:
    """og:title takes precedence over <title> tag."""
    captured_settings = {}

    class Response:
        status_code = 200
        text = (
            "<html><head>"
            "<title>HTML Title</title>"
            "<meta property='og:title' content='OG Preferred Title' />"
            "</head><body><main><p>Readable content for chunking here.</p></main></body></html>"
        )
        headers = {"content-type": "text/html"}
        url = "https://blog.example.com/article"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(
        "app.rag.url_loader.get_settings",
        lambda: SimpleNamespace(
            url_fetch_user_agent="MindDockTest/1.0",
            url_fetch_timeout_seconds=5.0,
            url_fetch_retry_count=0,
            url_fetch_retry_backoff_seconds=0.0,
            url_fetch_verify_ssl=True,
            url_fetch_allow_insecure_fallback=False,
        ),
    )
    monkeypatch.setattr("app.rag.url_loader.httpx.get", lambda *args, **kwargs: Response())

    content = fetch_url_content("https://blog.example.com/article")

    assert content.title == "OG Preferred Title"
    assert content.og_title == "OG Preferred Title"
    assert content.domain == "blog.example.com"
    assert content.og_description is None  # not in this HTML
    assert content.canonical_url is None
