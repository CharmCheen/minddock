from types import SimpleNamespace

import pytest
import httpx

from app.rag.ingest import build_documents_for_source
from app.rag.source_loader import SourceLoaderRegistry, URLSourceLoader, build_url_descriptor
from app.rag.url_loader import _MainTextHTMLParser, fetch_url_content


def _mock_url_settings(monkeypatch, *, insecure_fallback: bool = False) -> None:
    monkeypatch.setattr(
        "app.rag.url_loader.get_settings",
        lambda: SimpleNamespace(
            url_fetch_user_agent="MindDockTest/1.0",
            url_fetch_timeout_seconds=5.0,
            url_fetch_retry_count=0,
            url_fetch_retry_backoff_seconds=0.0,
            url_fetch_verify_ssl=True,
            url_fetch_allow_insecure_fallback=insecure_fallback,
        ),
    )


class FakeResponse:
    def __init__(
        self,
        *,
        text: str,
        url: str = "https://example.com/final",
        content_type: str = "text/html",
        status_code: int = 200,
    ) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://example.com/requested")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("bad status", request=request, response=response)


def _mock_get(monkeypatch, response: FakeResponse) -> None:
    monkeypatch.setattr("app.rag.url_loader.httpx.get", lambda *args, **kwargs: response)


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


def test_html_parser_cleans_structural_noise_and_prefers_article() -> None:
    parser = _MainTextHTMLParser()
    parser.feed(
        """
        <html>
          <head><title>Noise Test</title></head>
          <body>
            <header>site header should disappear</header>
            <nav>navigation should disappear</nav>
            <aside>aside links should disappear</aside>
            <article>
              <h1>Article Heading</h1>
              <p>Primary article content that should be extracted cleanly.</p>
            </article>
            <footer>footer should disappear</footer>
            <p>Body fallback content should not win over article content.</p>
            <script>window.noisy = true</script>
            <style>.noisy { display: block; }</style>
          </body>
        </html>
        """
    )

    text = parser.get_text()

    assert "Primary article content" in text
    assert "Body fallback content" not in text
    assert "site header" not in text
    assert "navigation" not in text
    assert "footer" not in text
    assert "window.noisy" not in text


def test_html_parser_preserves_chinese_body_text() -> None:
    parser = _MainTextHTMLParser()
    parser.feed(
        """
        <html>
          <head><title>中文页面</title></head>
          <body>
            <main>
              <p>这是一段用于测试的中文正文内容，应该被完整保留下来并参与后续切分。</p>
            </main>
          </body>
        </html>
        """
    )

    assert "中文正文内容" in parser.get_text()


def test_fetch_url_content_uses_default_safe_ssl(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        status_code = 200
        text = "<html><head><title>Title</title></head><body><main><p>Readable content for testing.</p></main></body></html>"
        headers = {"content-type": "text/html"}
        url = "https://example.com/final"

        def raise_for_status(self) -> None:
            return None

    _mock_url_settings(monkeypatch)

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

    _mock_url_settings(monkeypatch, insecure_fallback=True)

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

    _mock_url_settings(monkeypatch)
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
            <meta name="description" content="Standard meta description." />
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
    assert parser.meta_description == "Standard meta description."
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

    _mock_url_settings(monkeypatch)
    monkeypatch.setattr("app.rag.url_loader.httpx.get", lambda *args, **kwargs: Response())

    content = fetch_url_content("https://blog.example.com/article")

    assert content.title == "OG Preferred Title"
    assert content.og_title == "OG Preferred Title"
    assert content.domain == "blog.example.com"
    assert content.og_description is None  # not in this HTML
    assert content.canonical_url is None
    assert "canonical_missing" in content.warnings


def test_fetch_url_content_extracts_canonical_and_meta_description(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)
    _mock_get(
        monkeypatch,
        FakeResponse(
            text=(
                "<html><head><title>HTML Title</title>"
                "<meta name='description' content='Plain description.' />"
                "<link rel='canonical' href='https://example.com/canonical' />"
                "</head><body><article><p>Readable article body content for tests.</p></article></body></html>"
            ),
            url="https://example.com/final",
        ),
    )

    content = fetch_url_content("https://example.com/requested")

    assert content.title == "HTML Title"
    assert content.canonical_url == "https://example.com/canonical"
    assert content.meta_description == "Plain description."
    assert content.warnings == ()


def test_fetch_url_content_falls_back_to_body_when_article_is_empty(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)
    _mock_get(
        monkeypatch,
        FakeResponse(
            text=(
                "<html><head><title>Fallback</title></head><body>"
                "<article></article>"
                "<p>Fallback body paragraph with enough content to be extracted.</p>"
                "</body></html>"
            ),
        ),
    )

    content = fetch_url_content("https://example.com/requested")

    assert "Fallback body paragraph" in content.text


def test_fetch_url_content_empty_body_returns_short_warning(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)
    _mock_get(monkeypatch, FakeResponse(text="<html><head><title>Empty</title></head><body></body></html>"))

    content = fetch_url_content("https://example.com/requested")

    assert content.text == ""
    assert "empty_main_text" in content.warnings
    assert all("\n" not in warning for warning in content.warnings)


def test_fetch_url_content_network_error_is_friendly_failure(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)

    def fake_get(*args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("app.rag.url_loader.httpx.get", fake_get)

    with pytest.raises(RuntimeError, match="network_error"):
        fetch_url_content("https://example.com/requested")


def test_fetch_url_content_rejects_invalid_url(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)

    with pytest.raises(RuntimeError, match="invalid URL"):
        fetch_url_content("not-a-url")


def test_fetch_url_content_rejects_non_200_status(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)
    _mock_get(monkeypatch, FakeResponse(text="<html></html>", status_code=404))

    with pytest.raises(RuntimeError, match="HTTP status 404"):
        fetch_url_content("https://example.com/missing")


def test_url_source_loader_metadata_contract(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)
    _mock_get(
        monkeypatch,
        FakeResponse(
            text=(
                "<html><head><title>Contract</title>"
                "<meta name='description' content='Contract description.' />"
                "<link rel='canonical' href='https://example.com/canonical' />"
                "</head><body><main><p>Contract body content for chunking and metadata tests.</p></main></body></html>"
            ),
            url="https://example.com/final",
        ),
    )

    load_result = URLSourceLoader().load(build_url_descriptor("https://example.com/requested"))

    assert load_result.metadata["source_media"] == "text"
    assert load_result.metadata["source_kind"] == "web_page"
    assert load_result.metadata["loader_name"] == "url.extract"
    assert load_result.metadata["requested_url"] == "https://example.com/requested"
    assert load_result.metadata["final_url"] == "https://example.com/final"
    assert load_result.metadata["domain"] == "example.com"
    assert load_result.metadata["canonical_url"] == "https://example.com/canonical"
    assert load_result.metadata["meta_description"] == "Contract description."


def test_url_loader_warnings_flow_to_chunk_metadata(monkeypatch) -> None:
    _mock_url_settings(monkeypatch)
    _mock_get(
        monkeypatch,
        FakeResponse(
            text="<html><head><title>Warn</title></head><body><main><p>Warning metadata body content.</p></main></body></html>",
            url="https://example.com/warn",
        ),
    )

    documents = build_documents_for_source(
        build_url_descriptor("https://example.com/warn"),
        registry=SourceLoaderRegistry(loaders=[URLSourceLoader()]),
    )

    assert documents
    assert documents[0].page_content == "Warning metadata body content."
    assert documents[0].metadata["loader_warnings"] == "canonical_missing"
    assert "canonical_missing" not in documents[0].page_content
