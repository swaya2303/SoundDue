# reasoning/service/Dockerfile
# ================================
# Python 3.12-slim image with pinned hyperon==0.2.10.
# Used for METTA_MODE=http.
#
# EXPERIMENTAL: Hyperon / MeTTa is an experimental runtime.
# See docs/reasoning-runtime.md.

FROM python:3.12-slim

LABEL maintainer="sounddue-prototype"
LABEL description="SoundDue MeTTa reasoning micro-service"

# Set working directory to repo root so "reasoning" is importable as a package
WORKDIR /app

# Install dependencies first (layer-cached when requirements don't change)
COPY reasoning/requirements.txt reasoning/requirements.txt
RUN pip install --no-cache-dir -r reasoning/requirements.txt

# Copy the reasoning package (no backend code needed in this container)
COPY reasoning/ reasoning/

# Rules are mounted read-only at runtime; copy the defaults as fallback
# (docker-compose.yml overrides this with a bind mount)

# Expose the service port
EXPOSE 8001

# Run the FastAPI service
CMD ["uvicorn", "reasoning.service.app:app", "--host", "0.0.0.0", "--port", "8001"]
