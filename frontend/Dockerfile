# 多阶段构建：Node 构建静态资源 -> Nginx 提供静态服务
FROM node:20-alpine AS builder

WORKDIR /app

# 启用 corepack 以使用 pnpm/yarn 的版本管理（这里用 npm 即可）
COPY package.json ./
RUN npm install --no-audit --no-fund

COPY . .

ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build


FROM nginx:1.27-alpine AS runtime

COPY --from=builder /app/dist /usr/share/nginx/html
COPY ./nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
