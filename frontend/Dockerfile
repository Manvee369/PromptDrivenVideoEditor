# ── Stage 1: deps + build ───────────────────────────────────────────────────
FROM node:20-slim AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Build Next.js production bundle.
# NEXT_PUBLIC_API_URL is baked in at build time; pass it via --build-arg.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

# ── Stage 2: minimal runtime ────────────────────────────────────────────────
FROM node:20-slim AS runtime

WORKDIR /app

# Only copy what Next.js needs to run in standalone mode
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

# Non-root user
RUN useradd -r -u 1001 nextjs && chown -R nextjs /app
USER nextjs

EXPOSE 3000

ENV NODE_ENV=production
ENV PORT=3000

CMD ["node", "server.js"]
