FROM node:26-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY backend/resources/plate-states.json /app/backend/resources/plate-states.json
RUN npm run build

FROM python:3.15-slim
ARG VERSION=0.3.0
ARG VCS_REF=unknown
LABEL org.opencontainers.image.title="Curbwatch" \
    org.opencontainers.image.description="Self-hosted parking ticket monitoring and street activity maps" \
    org.opencontainers.image.source="https://github.com/DEADSEC-SECURITY/curbwatch" \
    org.opencontainers.image.url="https://github.com/DEADSEC-SECURITY/curbwatch" \
    org.opencontainers.image.licenses="PolyForm-Noncommercial-1.0.0" \
    org.opencontainers.image.version=$VERSION \
    org.opencontainers.image.revision=$VCS_REF
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PARKING_DATA_DIR=/data \
    PARKING_HOST=0.0.0.0 PARKING_SHARE_HOST=0.0.0.0
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt \
    && groupadd --gid 10001 curbwatch \
    && useradd --uid 10001 --gid curbwatch --no-create-home curbwatch \
    && mkdir /data && chown curbwatch:curbwatch /data
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
COPY compose.hub.yaml ./.deploy/compose.yaml
COPY .env.example ./.deploy/env.example
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
USER 10001:10001
EXPOSE 8000 8002
ENTRYPOINT ["python", "-m", "backend.entrypoint"]
CMD ["api"]
