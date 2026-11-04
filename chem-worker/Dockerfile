FROM python:3.11-slim-bookworm

WORKDIR /app
COPY pyproject.toml ./
COPY mapper ./mapper
RUN pip install --no-cache-dir ".[api]"

EXPOSE 8000
CMD ["python", "-m", "mapper"]
