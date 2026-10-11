FROM node:24.21.0-bookworm-slim AS javascript
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN npm --prefix frontend ci
COPY frontend/ ./frontend/
RUN npm --prefix frontend run build
COPY swarm/package.json swarm/package-lock.json ./swarm/
RUN npm --prefix swarm ci
COPY swarm/ ./swarm/
RUN npm --prefix swarm run build && npm --prefix swarm prune --omit=dev
COPY xrpl/package.json xrpl/package-lock.json ./xrpl/
RUN npm --prefix xrpl ci
COPY xrpl/ ./xrpl/
RUN npm --prefix xrpl run check

FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 libatomic1 ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=javascript /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/requirements.lock ./backend/requirements.lock
RUN pip install --no-cache-dir -r backend/requirements.lock
COPY backend/ ./backend/
COPY --from=javascript /app/frontend/dist ./frontend/dist
COPY --from=javascript /app/swarm ./swarm
COPY --from=javascript /app/xrpl ./xrpl
COPY scripts/start_prod.sh ./scripts/start_prod.sh
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHON_DOTENV_DISABLED=1 APP_ENV=production TRADING_MODE=paper XRPL_NETWORK=testnet DATABASE_URL=sqlite:////data/spare_change.db
EXPOSE 8000
CMD ["sh", "/app/scripts/start_prod.sh"]
