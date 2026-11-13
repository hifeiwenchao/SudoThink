# SudoThink Blog

一个前后端分离的博客系统，提供公开站点和独立域名的管理后台。

- 文章、分类、标签、“关于我”、访客评论审核与文章打赏。
- 富文本创作、OSS 图片/视频直传、CDN 刷新与预热、API 请求记录查询。
- 浅色/深色/系统外观，以及时间戳、二维码、JSON、cron 等浏览器本地工具。

文章阅读数由 Redis 实时累加，经 Celery 延迟写回 MySQL；请求记录独立保存并脱敏。详细机制见 [开发文档](./docs/development.md)。

## 技术栈

| 部分 | 技术 |
| --- | --- |
| 后端 | Python 3.15+、Sanic、Tortoise-ORM / Aerich、Pydantic、PyJWT |
| 前端 | Node.js 22+、Vue 3、Vite、TypeScript、Vue Router、Pinia、Element Plus、Axios |
| 数据与任务 | MySQL 8、Redis 7、Celery、RabbitMQ |
| 部署 | Docker Compose、NGINX |

主要目录：`backend/` 后端与初始化脚本，`frontend/` 前端，`nginx/` 外部代理配置，`docs/` 详细文档。统一环境变量模板为 [.env.example](./.env.example)。

## Docker 部署

### 1. 准备外部服务与网络

[应用 Compose](./docker-compose.yml) 仅管理 `backend`、`frontend`、`worker`、`beat`；MySQL、Redis、RabbitMQ、NGINX 由外部服务提供。以下容器名、域名、网络名和路径均为示例，使用时替换为实际值。

| 网络 | 连接服务 |
| --- | --- |
| `sudothink-data` | MySQL、Redis、RabbitMQ、backend、worker、beat |
| `sudothink-proxy` | 外部 NGINX、backend、frontend |

先启动外部服务，再创建网络并连接已有容器；已存在的网络和连接可复用：

```bash
docker network create sudothink-data
docker network create sudothink-proxy
docker network connect --alias mysql sudothink-data mysql-container
docker network connect --alias redis sudothink-data redis-container
docker network connect --alias rabbitmq sudothink-data rabbitmq-container
docker network connect sudothink-proxy nginx-container
```

### 2. 配置环境变量和站点

在项目根目录创建 `.env`；已有文件时按模板合并缺项并保留实际凭据：

```bash
cd /path/to/SudoThink
test -f .env || cp .env.example .env
```

模板默认用于生产部署，至少确认以下配置，并替换所有密钥、密码、邮箱及域名：

```dotenv
DEPENDS_MAIN_NETWORK=sudothink-data
DEPENDS_PROXY_NETWORK=sudothink-proxy
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=replace-with-a-random-application-secret
JWT_SECRET=replace-with-a-random-jwt-secret
FRONTEND_HTTP_PORT=8100
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=sudothink
MYSQL_USER=sudothink
MYSQL_PASSWORD=replace-with-mysql-password
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-redis-password
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=sudothink
RABBITMQ_PASSWORD=replace-with-rabbitmq-password
RABBITMQ_VHOST=/
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-strong-admin-password
CORS_ORIGINS=https://www.example.com,https://admin.example.com
VITE_API_BASE_URL=/api
```

MySQL 账号及 RabbitMQ 用户/vhost 须事先创建并授权；建库可单独配置 `MYSQL_ADMIN_USER`、`MYSQL_ADMIN_PASSWORD`。Redis 未启用密码时留空。初始化脚本不会创建 MySQL 账号，也不会重置已有管理员密码。

公开站点与管理站点共用前端，通过主机名区分。构建前调整：

- [frontend/src/site.ts](./frontend/src/site.ts)：`ADMIN_SITE_HOST` 填管理域名，`PUBLIC_SITE_URL` 填公开站点完整首页地址。
- [nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf)：替换公开、管理及裸域的 `server_name`、裸域跳转目标和证书路径。
- `.env`：`CORS_ORIGINS` 填两个站点的准确 Origin；需要访客真实 IP 时配置 `TRUSTED_PROXY_CIDRS`，见 [代理说明](./docs/deployment-reference.md#qqwry-与可信代理)。

### 3. 构建、初始化和启动

```bash
docker compose config --quiet
docker compose build backend frontend

# 首次部署：创建数据库、表和管理员
docker compose run --rm backend python scripts/init_db.py

# 启用静态资源 CDN 时，先完成下文的资源发布，再启动前端
docker compose up -d backend frontend worker beat
docker compose ps
docker compose logs --tail=100 backend worker beat
```

已有安装按下文[更新流程](#更新应用)运行升级脚本，升级保留已有内容和阅读数，可重复执行；账号需有 `CREATE`、`ALTER` 权限。构建镜像源及更多配置见 [部署配置参考](./docs/deployment-reference.md)。

### 4. 验证入口与 HTTPS

公开博客可直接通过 `http://服务器IP:8100/` 访问，端口由 `FRONTEND_HTTP_PORT` 控制；前端将同源 `/api/` 转发到后端。IP 入口展示公开站点，管理后台使用前面配置的独立管理域名。

```bash
curl --fail http://服务器IP:8100/api/health
```

域名访问需配置 DNS，并在外部 NGINX 发布 `80`、`443`。证书应覆盖裸域、公开和管理域名；将证书目录只读挂载到 `/etc/ssl/depends`，并与站点配置中的路径一致。外部 NGINX 经共享代理网络访问 `sudothink-frontend:8100` 和 `sudothink-backend:8000`。完整证书挂载示例见 [HTTPS 配置](./docs/deployment-reference.md#https-与外部-nginx)。

```bash
cp nginx/conf.d/sudothink.conf /path/to/nginx/conf.d/sudothink.conf
docker exec nginx-container nginx -t && docker exec nginx-container nginx -s reload
curl --fail https://www.example.com/api/health
curl --fail https://admin.example.com/api/health
```

健康检查应返回 `code: 0`、`data.status: "ok"`、`data.redis: true`。默认 HTTP 自动跳转 HTTPS，裸域跳转公开站点，并保留路径与查询参数。

### 静态资源 CDN 发布

默认 `CDN_BASE_URL` 留空，资源从站点加载。启用 CDN 时，在 `.env` 配置 `CDN_BASE_URL`、`OSS_STATIC_PREFIX` 及后端 OSS 凭据，按以下顺序发布：

1. 构建前端，导出本次构建的静态资源。
2. 使用 `publish_static_assets.py` 先 `--dry-run`，再上传到 OSS。
3. 在后台或阿里云控制台手动刷新 CDN 静态目录，等待完成并确认新资源可访问。
4. 部署与上传资源相同的前端构建，再重载外部 NGINX。

资源使用固定文件名，上传会覆盖同名文件；HTML 由站点提供。Docker 导出和上传命令见 [CDN 发布步骤](./docs/deployment-reference.md#前端静态资源通过-cdn-发布)。

## 更新应用

更新代码或配置后重新构建；涉及数据库结构时在启动前执行升级脚本。启用 CDN 的安装先完成上述资源发布，再切换容器：

```bash
docker compose config --quiet
docker compose build backend frontend
docker compose run --rm --no-deps backend python scripts/upgrade_site_content.py
docker compose up -d --force-recreate backend frontend worker beat
docker exec nginx-container nginx -t && docker exec nginx-container nginx -s reload
```

backend、worker、beat 应运行相同版本。`.env` 修改后需重建容器，前端构建变量或 `site.ts` 修改后需重新构建前端；容器重建和证书续签后检查并重载外部 NGINX。

## 本地运行

准备 Python 3.15+、Node.js 22+、npm（或 pnpm）及可访问的 MySQL、Redis、RabbitMQ。复制根目录 `.env.example` 为 `.env`，填写凭据，并调整为宿主机可访问的地址：

```dotenv
APP_ENV=development
APP_DEBUG=true
MYSQL_HOST=127.0.0.1
REDIS_HOST=127.0.0.1
RABBITMQ_HOST=127.0.0.1
CORS_ORIGINS=http://localhost:8100,http://sudothink.test:8100,http://admin.sudothink.test:8100
VITE_API_BASE_URL=/api
```

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/init_db.py          # 已有数据库改用 scripts/upgrade_site_content.py
python main.py
```

其他终端分别运行前端、worker、beat；worker/beat 使用已激活的后端虚拟环境：

```bash
# 前端，在项目根目录执行
cd frontend
npm ci
npm run dev

# worker，在 backend 目录执行
celery -A app.celery_app:celery_app worker --loglevel=INFO

# beat，在另一个 backend 终端执行
mkdir -p data
celery -A app.celery_app:celery_app beat --loglevel=INFO --schedule=data/celerybeat-schedule
```

前端默认 `http://localhost:8100`，Vite 代理 `/api` 到 `http://localhost:8000`。beat 当前无内置周期计划；阅读数延迟写回需要 Redis、RabbitMQ 与 worker。

本地调试管理后台时，将 `site.ts` 的 `ADMIN_SITE_HOST` 改为 `admin.sudothink.test`，`PUBLIC_SITE_URL` 改为 `http://sudothink.test:8100/`；在 [vite.config.ts](./frontend/vite.config.ts) 的 `server.allowedHosts` 加入两个本地域名并重启 Vite，在 `/etc/hosts` 加入：

```text
127.0.0.1 sudothink.test
127.0.0.1 admin.sudothink.test
```

分别访问 `http://sudothink.test:8100/` 和 `http://admin.sudothink.test:8100/`；生产构建前恢复实际站点配置。

## 详细文档

- [部署配置参考](./docs/deployment-reference.md)：HTTPS、环境变量、OSS/CDN、ICP、QQWry 与可信代理。
- [功能使用说明](./docs/features.md)：创作、工具箱、外观、分类标签、打赏与评论审核。
- [开发机制与接口](./docs/development.md)：Celery、通用延迟任务、阅读计数、请求记录和 API 路径。
