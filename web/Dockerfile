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
COPY security-headers.conf /etc/nginx/security-headers.conf
COPY --from=builder /app/dist/web/browser /usr/share/nginx/html

EXPOSE 8080

CMD ["/bin/sh", "-c", \
  "envsubst '$PORT $BACKEND_HOST $PROXY_SHARED_SECRET' < /etc/nginx/conf.d/default.conf.template \
   > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
