# 多阶段构建：Node 构建静态资源 -> Nginx 提供静态服务
FROM node:22-alpine AS builder

WORKDIR /app

# 按锁文件安装依赖，保持本地与 Docker 构建一致。
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

ARG VITE_API_BASE_URL=/api
ARG VITE_ASSET_BASE_URL=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_ASSET_BASE_URL=${VITE_ASSET_BASE_URL}

RUN npm run build


FROM nginx:1.27-alpine AS runtime

# 只保留本项目的构建产物，避免导出 CDN 资源时混入默认 HTML 页面。
RUN rm -f /usr/share/nginx/html/index.html /usr/share/nginx/html/50x.html
COPY --from=builder /app/dist /usr/share/nginx/html
COPY ./nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8100

CMD ["nginx", "-g", "daemon off;"]
