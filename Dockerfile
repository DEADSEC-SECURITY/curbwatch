FROM node:26-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
COPY backend/resources/plate-states.json /app/backend/resources/plate-states.json
RUN npm run build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PARKING_DATA_DIR=/data \
    PARKING_HOST=0.0.0.0 PARKING_SHARE_HOST=0.0.0.0
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt \
    && groupadd --gid 10001 curbwatch \
    && useradd --uid 10001 --gid curbwatch --no-create-home curbwatch \
    && mkdir /data && chown curbwatch:curbwatch /data
COPY LICENSE NOTICE THIRD_PARTY_NOTICES.md ./
COPY backend/ ./backend/
COPY --from=frontend /app/frontend/dist ./frontend/dist
USER 10001:10001
EXPOSE 8000 8002
ENTRYPOINT ["python", "-m", "backend.entrypoint"]
CMD ["api"]
