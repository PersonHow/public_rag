# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build -- --configuration=production

# ── Stage 2: Serve ────────────────────────────────────────────────────────────
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf.template
COPY --from=builder /app/dist/web/browser /usr/share/nginx/html

EXPOSE 8080

CMD ["/bin/sh", "-c", \
  "envsubst '$PORT $BACKEND_HOST' < /etc/nginx/conf.d/default.conf.template \
   > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
