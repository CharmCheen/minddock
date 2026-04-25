"""Source loader strategies and registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from urllib.parse import urlparse

from app.rag.pdf_parser import extract_page_blocks, PageBlocks

# Minimum characters on a page to consider it "has text"
_MIN_PAGE_TEXT_LENGTH = 20
from app.rag.source_models import SourceDescriptor, SourceLoadResult, utc_now_iso
from app.rag.url_loader import URLContent, fetch_url_content

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".md", ".txt", ".pdf"}
_TEXT_EXTENSIONS = {".md", ".txt"}
_PDF_EXTENSIONS = {".pdf"}


class SourceLoader(ABC):
    """Strategy interface for loading one source into normalized text."""

    source_type: str

    @abstractmethod
    def supports(self, descriptor: SourceDescriptor) -> bool:
        """Return whether this loader can process the descriptor."""

    @abstractmethod
    def load(self, descriptor: SourceDescriptor) -> SourceLoadResult:
        """Load the source into normalized text and metadata."""


class FileSourceLoader(SourceLoader):
    source_type = "file"

    def supports(self, descriptor: SourceDescriptor) -> bool:
        return descriptor.source_type == "file" and descriptor.local_path is not None

    def load(self, descriptor: SourceDescriptor) -> SourceLoadResult:
        path = descriptor.local_path
        if path is None:
            raise ValueError("file source requires local_path")

        suffix = path.suffix.lower()
        if suffix in _TEXT_EXTENSIONS:
            text = path.read_text(encoding="utf-8", errors="ignore")
            return SourceLoadResult(
                descriptor=descriptor,
                title=path.stem,
                text=text,
            )
        if suffix in _PDF_EXTENSIONS:
            return self._load_pdf(descriptor=descriptor, path=path)
        raise ValueError(f"Unsupported file extension: {suffix}")

    def _load_pdf(self, *, descriptor: SourceDescriptor, path: Path) -> SourceLoadResult:
        page_blocks_list = extract_page_blocks(path)
        if not page_blocks_list:
            logger.warning("PDF yielded no extractable text: path=%s", path)
            return SourceLoadResult(
                descriptor=descriptor,
                title=path.stem,
                text="",
            )

        # Backward-compatible plain text (used by non-structured path)
        page_texts: list[str] = []
        for pb in page_blocks_list:
            if len(pb.text.strip()) >= _MIN_PAGE_TEXT_LENGTH:
                page_texts.append(f"\n\n[page {pb.page}]\n{pb.text}")

        plain_text = "".join(page_texts).strip()

        # Convert PageBlocks dataclasses to plain dicts for metadata serialization
        pages_dicts = [
            {"page": pb.page, "text": pb.text, "blocks": pb.blocks}
            for pb in page_blocks_list
        ]

        return SourceLoadResult(
            descriptor=descriptor,
            title=path.stem,
            text=plain_text,
            metadata={"_page_blocks": pages_dicts},  # injected for structured chunker
        )


class URLSourceLoader(SourceLoader):
    source_type = "url"

    def supports(self, descriptor: SourceDescriptor) -> bool:
        return descriptor.source_type == "url"

    def load(self, descriptor: SourceDescriptor) -> SourceLoadResult:
        content = fetch_url_content(descriptor.source)
        metadata: dict[str, str] = {
            "source_media": "text",
            "source_kind": "web_page",
            "loader_name": "url.extract",
            "url": content.final_url,
            "requested_url": content.requested_url,
            "final_url": content.final_url,
            "domain": content.domain or "",
            "status_code": str(content.status_code),
            "fetched_at": content.fetched_at,
            "ssl_verified": "true" if content.ssl_verified else "false",
        }
        if content.og_description:
            metadata["og_description"] = content.og_description
        if content.og_image:
            metadata["og_image"] = content.og_image
        if content.canonical_url:
            metadata["canonical_url"] = content.canonical_url
        if content.meta_description:
            metadata["meta_description"] = content.meta_description
        return SourceLoadResult(
            descriptor=SourceDescriptor(
                source=content.final_url,
                source_type="url",
                requested_source=content.requested_url,
            ),
            title=content.title.strip() or _title_from_url(content.final_url),
            text=content.text,
            metadata=metadata,
            warnings=content.warnings,
        )


class SourceLoaderRegistry:
    """Registry-based dispatcher for source loaders."""

    def __init__(self, loaders: list[SourceLoader] | None = None) -> None:
        self._loaders = list(loaders or [FileSourceLoader(), URLSourceLoader()])

    def register(self, loader: SourceLoader) -> None:
        self._loaders.append(loader)

    def resolve(self, descriptor: SourceDescriptor) -> SourceLoader:
        for loader in self._loaders:
            if loader.supports(descriptor):
                return loader
        raise ValueError(f"No loader registered for source `{descriptor.source}` ({descriptor.source_type})")

    def load(self, descriptor: SourceDescriptor) -> SourceLoadResult:
        return self.resolve(descriptor).load(descriptor)


def build_file_descriptor(path: Path, kb_dir: Path) -> SourceDescriptor:
    relative = path.relative_to(kb_dir).as_posix()
    return SourceDescriptor(source=relative, source_type="file", local_path=path)


def build_url_descriptor(url: str) -> SourceDescriptor:
    normalized = url.strip()
    return SourceDescriptor(source=normalized, source_type="url", requested_source=normalized)


def iter_file_descriptors(kb_dir: Path) -> list[SourceDescriptor]:
    descriptors: list[SourceDescriptor] = []
    for path in kb_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            descriptors.append(build_file_descriptor(path, kb_dir))
    return descriptors


def _title_from_url(url: str) -> str:
    parsed = urlparse(url)
    tail = parsed.path.rstrip("/").split("/")[-1]
    if tail:
        return tail
    return parsed.netloc or url
