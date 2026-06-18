# syntax=docker/dockerfile:1

# ── Swiss Job Hunter — frontend (static SPA served by nginx) ──────────────────

# Stage 1: build the Vite bundle.
FROM node:20-alpine AS build

WORKDIR /app

# VITE_API_BASE_URL is inlined into the bundle at build time (Vite reads
# import.meta.env.VITE_*). Defaults to localhost so local compose works
# unchanged; override via build arg for remote deploys.
ARG VITE_API_BASE_URL=http://localhost:8765
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

# Install deps from the lockfile for reproducible builds.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# Stage 2: serve the static bundle.
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
