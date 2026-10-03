# Multi-stage build: compile the React app, then serve it and the API from one Python container.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=web /web/dist /srv/frontend/dist
ENV NFLPROPS_CACHE=/srv/backend/.cache DATABASE_URL=sqlite:////srv/backend/data/app.db
VOLUME ["/srv/backend/data", "/srv/backend/.cache"]
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
