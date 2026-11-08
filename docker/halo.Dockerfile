# Halo kit server: serves halo/kit/ (the shell Devin's views run in). No dependencies.
FROM node:24-slim

WORKDIR /app/halo
COPY halo/server.mjs ./server.mjs
COPY halo/kit ./kit

ENV PORT=3001
EXPOSE 3001
USER node
CMD ["node", "server.mjs"]
