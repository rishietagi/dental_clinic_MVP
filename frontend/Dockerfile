# Frontend image — Next.js standalone build, multi-stage.
# Node 24 (matches the local toolchain; see docs/TECH_STACK.md for why not 20).

# --- deps: install node_modules once, cached on package-lock.json ---
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# --- builder: compile the app ---
FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# NEXT_PUBLIC_* is inlined at BUILD time and runs in the user's browser, so it
# MUST be set before `npm run build`. Miss this and the browser calls the wrong
# host — a failure that looks like CORS but is a baked-in URL.
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Supabase Auth config — also NEXT_PUBLIC_*, so also inlined at build time.
ARG NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL}
ARG NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
ENV NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=${NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY}

RUN npm run build

# --- runner: minimal image with just the standalone server ---
FROM node:24-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Run as a non-root user.
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

# `output: standalone` emits a self-contained server, but NOT .next/static or
# public — those must be copied in separately or the page loads with no CSS/JS.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
