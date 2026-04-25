"""Minimal URL ingestion helpers for fetching and extracting article text."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.rag.source_models import utc_now_iso

logger = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_BLOCK_TAGS = {"p", "li", "blockquote", "pre", "code", "h1", "h2", "h3", "h4", "h5", "h6"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "iframe"}
_NOISY_STRUCTURAL_TAGS = {"nav", "footer", "header", "aside"}
_NOISY_CONTAINER_HINTS = (
    "nav",
    "menu",
    "footer",
    "header",
    "sidebar",
    "cookie",
    "comment",
    "share",
    "related",
    "breadcrumb",
    "advert",
)


@dataclass(frozen=True)
class URLContent:
    """Normalized fetched URL content ready for chunking."""

    requested_url: str
    final_url: str
    title: str
    text: str
    status_code: int
    fetched_at: str
    ssl_verified: bool
    domain: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    og_image: str | None = None
    canonical_url: str | None = None
    meta_description: str | None = None
    warnings: tuple[str, ...] = ()


class _MainTextHTMLParser(HTMLParser):
    """Small HTML parser tuned for article-like body extraction."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._title_parts: list[str] = []
        self._preferred_text_parts: list[str] = []
        self._body_text_parts: list[str] = []
        self._current_text: list[str] = []
        self._current_preferred = False
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._prefer_depth = 0
        self._body_depth = 0
        # OG / meta fields
        self.og_title: str | None = None
        self.og_description: str | None = None
        self.og_image: str | None = None
        self.canonical_url: str | None = None
        self.meta_description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        self._tag_stack.append(lower_tag)
        attr_map = {key.lower(): (value or "") for key, value in attrs}
        attr_text = " ".join(attr_map.values()).lower()

        # Extract OG meta tags
        if lower_tag == "meta":
            prop = (attr_map.get("property", "") or attr_map.get("name", "")).lower()
            content = attr_map.get("content", "")
            if prop == "og:title" and content:
                self.og_title = content.strip()
            elif prop == "og:description" and content:
                self.og_description = content.strip()
            elif prop == "og:image" and content:
                self.og_image = content.strip()
            elif prop == "description" and content:
                self.meta_description = content.strip()
            return

        # Extract canonical link tag
        if lower_tag == "link":
            rel = attr_map.get("rel", "").lower()
            href = attr_map.get("href", "")
            if "canonical" in rel.split() and href:
                self.canonical_url = href.strip()
            return

        if lower_tag in _SKIP_TAGS or lower_tag in _NOISY_STRUCTURAL_TAGS:
            self._skip_depth += 1
            return

        if lower_tag == "body":
            self._body_depth += 1

        if lower_tag in {"article", "main"}:
            self._prefer_depth += 1
        elif lower_tag in {"section", "div"} and any(hint in attr_text for hint in _NOISY_CONTAINER_HINTS):
            self._skip_depth += 1
            return

        if lower_tag in _BLOCK_TAGS:
            self._flush_current_text()

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in _BLOCK_TAGS:
            self._flush_current_text()

        if (lower_tag in _SKIP_TAGS or lower_tag in _NOISY_STRUCTURAL_TAGS) and self._skip_depth:
            self._skip_depth -= 1
        elif lower_tag in {"section", "div"} and self._skip_depth:
            self._skip_depth -= 1
        elif lower_tag in {"article", "main"} and self._prefer_depth:
            self._prefer_depth -= 1

        if lower_tag == "body" and self._body_depth:
            self._body_depth -= 1

        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return

        current_tag = self._tag_stack[-1] if self._tag_stack else ""
        if current_tag == "title":
            self._title_parts.append(data)
            self.title = _normalize_text(" ".join(self._title_parts))
            return

        if self._skip_depth or not self._body_depth:
            return

        if self._prefer_depth or current_tag in _BLOCK_TAGS:
            self._current_text.append(data)
            self._current_preferred = self._current_preferred or bool(self._prefer_depth)

    def get_text(self) -> str:
        self._flush_current_text()
        preferred_text = "\n\n".join(part for part in self._preferred_text_parts if part)
        if preferred_text.strip():
            return preferred_text
        return "\n\n".join(part for part in self._body_text_parts if part)

    def _flush_current_text(self) -> None:
        if not self._current_text:
            return
        text = _normalize_text(" ".join(self._current_text))
        is_preferred = self._current_preferred
        self._current_text.clear()
        self._current_preferred = False
        if len(text) >= 20:
            if is_preferred:
                self._preferred_text_parts.append(text)
            else:
                self._body_text_parts.append(text)


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", unescape(text)).strip()


def fetch_url_content(url: str) -> URLContent:
    """Fetch a URL and extract a best-effort article/body text."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RuntimeError(f"invalid URL `{url}`: expected absolute http(s) URL")

    settings = get_settings()
    headers = {
        "User-Agent": settings.url_fetch_user_agent,
        "Accept": "text/html,application/xhtml+xml",
    }

    last_error: Exception | None = None
    attempts = max(1, settings.url_fetch_retry_count + 1)
    for attempt in range(1, attempts + 1):
        try:
            return _fetch_once(
                url=url,
                headers=headers,
                verify_ssl=settings.url_fetch_verify_ssl,
            )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
            last_error = exc
            if settings.url_fetch_allow_insecure_fallback and settings.url_fetch_verify_ssl and _is_ssl_error(exc):
                logger.warning("Retrying URL fetch without SSL verification: url=%s", url)
                return _fetch_once(url=url, headers=headers, verify_ssl=False)
        except Exception as exc:
            raise RuntimeError(f"failed to fetch URL `{url}`: {exc}") from exc

        if attempt < attempts:
            time.sleep(settings.url_fetch_retry_backoff_seconds)

    raise RuntimeError(f"network_error while fetching URL `{url}`: {last_error}")


def _fetch_once(url: str, headers: dict[str, str], verify_ssl: bool) -> URLContent:
    settings = get_settings()
    try:
        response = httpx.get(
            url,
            headers=headers,
            timeout=settings.url_fetch_timeout_seconds,
            follow_redirects=True,
            verify=verify_ssl,
        )
        response.raise_for_status()
    except Exception as exc:
        if isinstance(exc, httpx.HTTPStatusError):
            status_code = exc.response.status_code if exc.response is not None else "unknown"
            raise RuntimeError(f"URL `{url}` returned HTTP status {status_code}") from exc
        if isinstance(exc, httpx.HTTPError):
            raise
        raise RuntimeError(str(exc)) from exc

    content_type = response.headers.get("content-type", "").lower()
    warnings: list[str] = []
    if "html" not in content_type:
        warnings.append("non_html_content_type")
    if "html" not in content_type and "<html" not in response.text.lower():
        raise RuntimeError(
            f"URL `{url}` returned non-HTML content: status={response.status_code} content_type={content_type or 'unknown'}"
        )

    parser = _MainTextHTMLParser()
    parser.feed(response.text)
    text = parser.get_text()
    final_url = str(response.url)

    # Prefer og:title, fall back to <title>, then URL-derived name
    if parser.og_title:
        title = parser.og_title.strip()
    elif parser.title:
        title = parser.title
    else:
        title = _title_from_url(final_url)
        warnings.append("title_missing")
    if not parser.canonical_url:
        warnings.append("canonical_missing")
    if not text.strip():
        warnings.append("empty_main_text")

    domain = urlparse(final_url).netloc

    logger.info(
        "Fetched URL content: requested_url=%s final_url=%s status_code=%s chars=%d domain=%s og_title=%s og_desc=%s",
        url,
        final_url,
        response.status_code,
        len(text),
        domain,
        bool(parser.og_title),
        bool(parser.og_description),
    )
    return URLContent(
        requested_url=url,
        final_url=final_url,
        title=title,
        text=text,
        status_code=response.status_code,
        fetched_at=utc_now_iso(),
        ssl_verified=verify_ssl,
        domain=domain,
        og_title=parser.og_title,
        og_description=parser.og_description,
        og_image=parser.og_image,
        canonical_url=parser.canonical_url,
        meta_description=parser.meta_description,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _is_ssl_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "certificate" in message or "ssl" in message or "tls" in message
