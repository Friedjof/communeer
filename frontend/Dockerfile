FROM node:22-alpine AS build
WORKDIR /app
ENV CI=true
COPY package.json pnpm-lock.yaml .npmrc pnpm-workspace.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM caddy:alpine
COPY --from=build /app/dist /srv
COPY Caddyfile /etc/caddy/Caddyfile
