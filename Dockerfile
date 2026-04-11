FROM python:3.11-slim

WORKDIR /app

# Install system deps for chromadb / sentence-transformers
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package install
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Copy project files
COPY pyproject.toml .
COPY app ./app
COPY domain ./domain
COPY ports ./ports
COPY configs ./configs
COPY knowledge_base ./knowledge_base
COPY data ./data

# Install Python dependencies via uv
RUN uv sync --frozen

# Environment defaults (override via docker-compose environment or .env)
ENV KB_DIR=knowledge_base
ENV CHROMA_DIR=data/chroma
ENV LOG_DIR=logs
ENV LLM_BASE_URL=https://api.openai.com/v1
ENV LLM_MODEL=gpt-4o-mini
ENV EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV LOG_LEVEL=INFO

# Create runtime directories
RUN mkdir -p data/chroma logs

# Default: run uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
