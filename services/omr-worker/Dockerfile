FROM python:3.12-slim

# Audiveris (Java) добавляется в фазе 7, если понадобится второй движок
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml .python-version ./
COPY src ./src
RUN uv sync --no-dev
CMD ["uv", "run", "python", "-m", "omr_worker.main"]
