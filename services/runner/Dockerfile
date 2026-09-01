FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY services/runner/pyproject.toml services/runner/uv.lock ./
RUN uv sync --frozen --no-dev

COPY services/runner/src/ ./src/
COPY lib/ ./lib/

ENV PYTHONPATH=/app/lib

CMD ["uv", "run", "--no-dev", "python", "src/worker.py"]
