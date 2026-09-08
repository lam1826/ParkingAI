# syntax=docker/dockerfile:1.7
FROM python:3.14.7-slim-bookworm@sha256:9ab8d9c8514b44f90cf0029dd42fdd7e9e211e639c8b995304cc04568dee900f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
ARG INSTALL_VISION=0

RUN addgroup --system --gid 10001 parkingai \
    && adduser --system --uid 10001 --ingroup parkingai --home /nonexistent parkingai

COPY requirements.txt ./requirements.txt
COPY requirements-vision.txt vision_model_install.py ./
RUN python -m pip install --upgrade pip \
    && python -m pip install --requirement requirements.txt

# CPU-only optional image; weights are fetched at build time by immutable digest.
# Runtime inference never downloads code or weights and remains single-worker.
RUN if [ "$INSTALL_VISION" = "1" ]; then \
      apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
      && rm -rf /var/lib/apt/lists/* \
      && python -m pip install --requirement requirements-vision.txt \
      && python vision_model_install.py --output /opt/parkingai-models; \
    fi

COPY --chown=parkingai:parkingai . .

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/ready', timeout=4).read()"]

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1 --proxy-headers --forwarded-allow-ips=\"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
