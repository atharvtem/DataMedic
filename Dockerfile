FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN pip install --no-cache-dir uv==0.9.8 && uv sync --frozen --no-dev
COPY datamedic ./datamedic
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER 10001
CMD ["python", "-m", "datamedic.app"]
