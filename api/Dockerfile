FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONUNBUFFERED=1
WORKDIR /app
COPY . .
RUN uv sync --frozen --no-install-project
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
