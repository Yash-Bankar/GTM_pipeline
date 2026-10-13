# Synpo GTM dashboard (Next.js) - production image.
#
# Build context is the `frontend/` directory:
#   docker build -t synpo-gtm-frontend ./frontend

FROM node:22-alpine AS builder
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build-time env: the API is contacted at runtime by the server, not the browser,
# so no NEXT_PUBLIC_* values are required.
RUN npm run build

FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts

# Non-root runtime user.
USER node

EXPOSE 3000
CMD ["npm", "run", "start"]
