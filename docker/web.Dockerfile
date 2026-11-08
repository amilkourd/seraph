# Next.js apps (dashboard, talkie). Build context: the repository root (their build scripts read contracts/).
#   docker build -f docker/web.Dockerfile --build-arg APP=dashboard .
FROM node:24-slim

ARG APP
ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app
COPY . /app
RUN test -n "$APP" && cd "/app/$APP" && npm ci --no-audit --no-fund && npm run build \
    && chown -R node:node "/app/$APP"

ENV NODE_ENV=production
USER node
WORKDIR /app/$APP
CMD ["npm", "run", "start"]
