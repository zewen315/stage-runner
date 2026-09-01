FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY services/workflow_service/pyproject.toml services/workflow_service/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY services/workflow_service/src/ ./src/
COPY lib/ ./lib/

ENV PYTHONPATH=/app/lib

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
