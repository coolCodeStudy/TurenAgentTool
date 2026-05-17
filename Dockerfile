FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_DEFAULT_TIMEOUT=120
ENV PIP_DISABLE_PIP_VERSION_CHECK=1

ARG PIP_INDEX_URL=https://pypi.org/simple

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt

COPY db ./db
COPY investment_knowledge_mcp ./investment_knowledge_mcp
COPY scripts ./scripts

EXPOSE 8000

CMD ["python", "-m", "investment_knowledge_mcp.server"]
