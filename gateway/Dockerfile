# Multi-stage: build the React operate console, then serve it (plus the
# existing reverse-proxy rules) from nginx. Build context is the repo
# root (see docker-compose.yml) so this stage can reach services/web/.

FROM node:20-alpine AS build
WORKDIR /app
COPY services/web/package.json services/web/package-lock.json* ./
RUN npm install
COPY services/web/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY gateway/nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist /usr/share/nginx/html
