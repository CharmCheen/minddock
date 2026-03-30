"""Generate demo PDF files for the MindDock knowledge base.

Run with:
    python scripts/create_demo_pdf.py

Creates two multi-page PDF files in knowledge_base/ for testing
the PDF ingest pipeline.
"""

from __future__ import annotations

from pathlib import Path


def _create_pdf(path: Path, pages: list[dict[str, str]]) -> None:
    """Create a simple text-based PDF with the given pages."""

    import pymupdf

    doc = pymupdf.open()

    for page_data in pages:
        page = doc.new_page(width=595, height=842)  # A4
        title = page_data.get("title", "")
        body = page_data.get("body", "")

        # Title
        if title:
            page.insert_text(
                (72, 72),
                title,
                fontsize=18,
                fontname="helv",
            )

        # Body text — wrap manually at ~80 chars per line
        y = 110
        line_height = 16
        for line in body.split("\n"):
            words = line.split()
            current_line = ""
            for word in words:
                test = f"{current_line} {word}".strip()
                if len(test) > 80:
                    page.insert_text((72, y), current_line, fontsize=11, fontname="helv")
                    y += line_height
                    current_line = word
                else:
                    current_line = test
            if current_line:
                page.insert_text((72, y), current_line, fontsize=11, fontname="helv")
                y += line_height
            y += 4  # paragraph spacing

    doc.save(str(path))
    doc.close()
    print(f"Created: {path} ({len(pages)} pages)")


def main() -> None:
    kb_dir = Path("knowledge_base")
    kb_dir.mkdir(exist_ok=True)

    # --- PDF 1: knowledge management concepts ---
    _create_pdf(
        kb_dir / "knowledge_management.pdf",
        [
            {
                "title": "What is Personal Knowledge Management",
                "body": (
                    "Personal Knowledge Management (PKM) is a set of processes that individuals use to "
                    "gather, classify, store, search, and retrieve knowledge in their daily activities. "
                    "The goal is to turn information into actionable knowledge that supports decision making.\n\n"
                    "PKM tools help users organize notes, articles, bookmarks, and documents into a "
                    "searchable and interconnected knowledge base. Modern PKM systems leverage AI to "
                    "automatically categorize, summarize, and surface relevant information."
                ),
            },
            {
                "title": "The Role of AI in Knowledge Management",
                "body": (
                    "Artificial Intelligence transforms knowledge management by enabling semantic search, "
                    "automatic summarization, and intelligent recommendations. Unlike traditional keyword-based "
                    "search, AI-powered systems understand the meaning behind queries and can retrieve "
                    "conceptually relevant documents even when exact keywords do not match.\n\n"
                    "Retrieval-Augmented Generation (RAG) is a key technique in AI knowledge management. "
                    "RAG combines a retrieval system that finds relevant document chunks with a language model "
                    "that generates grounded answers based on the retrieved evidence. This approach ensures "
                    "that AI responses are traceable back to source documents through citations."
                ),
            },
            {
                "title": "Building a PKM System",
                "body": (
                    "A practical PKM system consists of several components working together. First, a document "
                    "ingestion pipeline reads files from local storage or cloud sources and converts them into "
                    "chunks suitable for embedding. Second, a vector database stores these chunks along with "
                    "their embeddings and metadata for fast similarity search.\n\n"
                    "Third, a query engine handles user questions by embedding the query, searching the vector "
                    "store, and assembling the most relevant chunks as context. Finally, a generation component "
                    "uses a language model to produce answers that are grounded in the retrieved evidence, "
                    "accompanied by structured citations that point back to the original source material."
                ),
            },
        ],
    )

    # --- PDF 2: vector databases ---
    _create_pdf(
        kb_dir / "vector_databases.pdf",
        [
            {
                "title": "Introduction to Vector Databases",
                "body": (
                    "Vector databases are specialized storage systems designed to store, index, and query "
                    "high-dimensional vector embeddings. Unlike traditional relational databases that match "
                    "on exact values, vector databases perform approximate nearest neighbor (ANN) search "
                    "to find the most similar vectors to a given query vector.\n\n"
                    "Common vector databases include ChromaDB, Pinecone, Weaviate, Milvus, and Qdrant. "
                    "Each offers different trade-offs between scalability, latency, filtering capabilities, "
                    "and ease of deployment. For local development and small-scale projects, ChromaDB provides "
                    "a lightweight embedded option that requires no external infrastructure."
                ),
            },
            {
                "title": "Embeddings and Similarity Search",
                "body": (
                    "Embeddings are dense numerical representations of text, images, or other data types. "
                    "Text embeddings capture semantic meaning so that similar concepts are mapped to nearby "
                    "points in the vector space. Models like all-MiniLM-L6-v2 produce 384-dimensional vectors "
                    "that can be compared using cosine similarity or Euclidean distance.\n\n"
                    "During ingestion, each document chunk is converted into an embedding vector and stored "
                    "alongside its text and metadata. At query time, the user question is embedded using the "
                    "same model, and the database returns the top-k most similar stored vectors. This process "
                    "is the foundation of semantic search in RAG systems."
                ),
            },
        ],
    )

    print("Demo PDFs created successfully.")


if __name__ == "__main__":
    main()
