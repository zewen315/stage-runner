FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "src"]
