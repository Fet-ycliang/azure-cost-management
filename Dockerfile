FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AZURE_COST_MCP_TRANSPORT=streamable-http \
    AZURE_COST_MCP_HOST=0.0.0.0 \
    AZURE_COST_MCP_PORT=8000 \
    AZURE_COST_MCP_STREAMABLE_HTTP_PATH=/mcp

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["azure-cost-mcp", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000", "--path", "/mcp"]
