FROM python:3.12-slim

WORKDIR /app

# uv for fast installs
RUN pip install --no-cache-dir uv

COPY requirements.txt .
RUN uv pip install --system --no-cache -r requirements.txt

COPY discovery/ ./discovery/
COPY scripts/   ./scripts/

# Pre-create output dirs so volume mounts land cleanly
RUN mkdir -p output architecture-overview/. cache

ENV PYTHONUNBUFFERED=1

# Default: classify all repos and generate the viewer.
# Override CMD to run a specific step:
#   docker compose run pipeline python -m discovery.main
#   docker compose run pipeline python -m scripts.pilot --top 25
ENTRYPOINT ["python", "-u", "-m"]
CMD ["scripts.pilot", "--all"]
