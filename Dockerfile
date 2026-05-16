FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY db ./db
COPY investment_knowledge_mcp ./investment_knowledge_mcp
COPY scripts ./scripts

EXPOSE 8000

CMD ["python", "-m", "investment_knowledge_mcp.server"]
