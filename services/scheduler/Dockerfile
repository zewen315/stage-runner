FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY services/scheduler/pyproject.toml services/scheduler/uv.lock ./
RUN uv sync --frozen --no-dev

COPY services/scheduler/src/ ./src/
COPY lib/ ./lib/

ENV PYTHONPATH=/app/lib

CMD ["uv", "run", "--no-dev", "python", "src/poller.py"]
