FROM node:22-bookworm-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --no-fund
COPY tsconfig.json vite.config.ts vitest.config.ts tailwind.config.js postcss.config.js ./
COPY api ./api
COPY web ./web
RUN npm run build
USER node
EXPOSE 3000
CMD ["node", "--import", "tsx", "api/server.ts"]
