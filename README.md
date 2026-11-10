# SudoThink Blog

一个基于前后端分离架构的博客系统。

## 技术栈

### 后端
- **Python** 3.15+
- **Sanic** - 高性能异步 Web 框架
- **Tortoise-ORM** - 异步 ORM
- **Aerich** - Tortoise-ORM 的数据库迁移工具
- **MySQL** 8.0 - 主数据库
- **Redis** 7 - 缓存 / 会话 / 限流
- **PyJWT** - JWT 鉴权
- **Pydantic** - 数据校验

### 前端
- **Vue 3** + **Vite** + **TypeScript**
- **Vue Router** + **Pinia**
- **Element Plus** - UI 组件库
- **Axios** - HTTP 客户端

### 基础设施
- **NGINX** - 反向代理 / 静态资源服务
- **Docker** + **Docker Compose** - 容器化编排

## 目录结构

```
SudoThink/
├── backend/              # Sanic 后端
│   ├── app/
│   │   ├── api/          # 路由蓝图
│   │   ├── core/         # 核心工具 (config/redis/security/response)
│   │   ├── middlewares/  # 中间件
│   │   ├── models/       # Tortoise ORM 模型
│   │   └── schemas/      # Pydantic 数据模型
│   ├── scripts/          # 数据库和管理员初始化脚本
│   ├── migrations/       # Aerich 迁移文件
│   ├── main.py           # 入口
│   ├── pyproject.toml
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/             # Vue 3 前端
│   ├── src/
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── nginx/                # NGINX 反向代理配置
│   ├── nginx.conf
│   └── conf.d/sudothink.conf
├── docker-compose.yml          # 应用服务，接入外部数据网络和代理网络
├── .env.example                # 统一环境配置模板，默认用于生产部署
└── README.md
```

## 部署与运行

项目支持两种运行方式：

1. **Docker 部署**：MySQL、Redis、NGINX 由外部容器提供，当前项目的 Compose 只负责构建和运行 backend、frontend。
2. **本地运行**：后端直接由 Python 启动，前端由 Vite 启动；MySQL 和 Redis 可以使用本机服务，也可以使用对外发布端口的容器服务。

### Docker 部署（外部基础设施容器）

MySQL、Redis、NGINX 由外部容器提供，可以由各自独立的 Compose 管理。应用通过两个共享 Docker 网络连接这些服务。下面使用 `sudothink-data`、`sudothink-proxy` 作为示例网络名：

| 服务 | Docker 网络 | 用途 |
| --- | --- | --- |
| MySQL、Redis | `sudothink-data` | 数据库和缓存 |
| backend | `sudothink-data`、`sudothink-proxy` | 访问数据库，并接收代理请求 |
| frontend | `sudothink-proxy` | 提供前端静态资源 |
| 外部 NGINX | `sudothink-proxy` | 代理两个站点及 API |

```text
外部 NGINX（sudothink-proxy，HTTP 自动跳转 HTTPS）
   ├── https://www.example.com/   ──> sudothink-frontend:80
   ├── https://admin.example.com/ ──> sudothink-frontend:80
   └── 两个站点的 /api/              ──> sudothink-backend:8000
                                      │ sudothink-data
                                      ├──> mysql:3306
                                      └──> redis:6379
```

下文的 `www.example.com`、`admin.example.com` 为示例域名；`mysql-container`、`redis-container`、`nginx-container` 和 `/path/to/...` 为容器名、路径占位值，使用时替换为实际配置。

先启动外部基础服务，再创建共享网络并接入对应容器：

```bash
docker network create sudothink-data
docker network create sudothink-proxy

docker network connect --alias mysql sudothink-data mysql-container
docker network connect --alias redis sudothink-data redis-container
docker network connect sudothink-proxy nginx-container

docker network inspect sudothink-data sudothink-proxy --format '{{.Name}}'
```

[应用 Compose](./docker-compose.yml) 只管理 backend、frontend。在应用 `.env` 中将 `DEPENDS_MAIN_NETWORK`、`DEPENDS_PROXY_NETWORK` 设置为实际共享网络名；使用上面的示例时，分别填写 `sudothink-data`、`sudothink-proxy`。已有网络和容器连接可复用，跳过相应创建、接入命令，并确认 MySQL、Redis 分别具有 `mysql`、`redis` 网络别名。

#### 准备生产环境变量

在项目根目录使用 [.env.example](./.env.example) 创建 `.env`，模板默认采用生产模式。如果已有 `.env`，按模板合并缺少的配置，保留实际数据库、Redis 凭据：

```bash
cd /path/to/SudoThink
test -f .env || cp .env.example .env
```

需要确认的配置包括：

```dotenv
DEPENDS_MAIN_NETWORK=sudothink-data
DEPENDS_PROXY_NETWORK=sudothink-proxy
APP_ENV=production
APP_DEBUG=false

MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=sudothink
REDIS_HOST=redis
REDIS_PORT=6379

ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@example.com
ADMIN_PASSWORD=replace-with-a-strong-admin-password

CORS_ORIGINS=https://www.example.com,https://admin.example.com
VITE_API_BASE_URL=/api
```

将模板中的应用密钥、JWT 密钥、密码、邮箱和域名替换为实际值。`MYSQL_USER`、`MYSQL_PASSWORD` 对应已有数据库账号；`REDIS_PASSWORD` 与外部 Redis 服务一致，未启用密码认证时留空。容器内通过网络别名 `mysql`、`redis` 连接基础服务，`VITE_API_BASE_URL` 保持 `/api`。生产环境的 `CORS_ORIGINS` 填写两个站点的 HTTPS Origin，协议、域名和端口须与实际访问地址一致；本地开发的 HTTP 配置见下文。

`MYSQL_USER` 对应账号必须已存在，并具有目标数据库的建表和数据读写权限。建库使用的账号还需要创建数据库的权限，可通过 `MYSQL_ADMIN_USER`、`MYSQL_ADMIN_PASSWORD` 单独配置。初始化脚本会创建数据库、表和博客管理员，不会创建或授权 MySQL 账号。

管理员已存在时，重复初始化会保留原密码；修改 `.env` 中的 `ADMIN_PASSWORD` 不会重置已有账号密码。

#### 配置站点域名

公开站点与管理站点共用同一份前端，通过访问域名区分。部署前按实际域名调整：

| 配置位置 | 调整内容 |
| --- | --- |
| [nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) | 将 HTTP、HTTPS 两个 `server` 中的 `server_name` 都设置为公开站点和管理站点域名，例如 `www.example.com admin.example.com` |
| [frontend/src/site.ts](./frontend/src/site.ts) | 将 `ADMIN_SITE_HOST` 设置为管理站域名，例如 `admin.example.com`，只填写主机名 |
| `.env` | 设置对应的 `CORS_ORIGINS` 和管理员邮箱 `ADMIN_EMAIL` |

当前管理站主机名在 `frontend/src/site.ts` 中配置，修改后需要重新构建前端。

#### 构建、初始化并启动应用

在项目根目录依次构建后端、前端，再初始化并启动应用：

```bash
cd /path/to/SudoThink
docker compose config --quiet
docker compose build backend
docker compose build frontend

# 首次部署：创建数据库、数据表和管理员账号
docker compose run --rm backend python scripts/init_db.py

docker compose up -d backend frontend
docker compose ps
docker compose logs --tail=100 backend
```

#### 接入外部 NGINX

[nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) 默认通过 HTTPS 提供两个站点，支持 TLS 1.2、TLS 1.3 和 HTTP/2。HTTP 请求会返回 `308`，保留主机名、路径和查询参数并跳转到 HTTPS。HTTPS 站点使用稳定容器名 `sudothink-backend:8000`、`sudothink-frontend:80` 作为 upstream；两个站点的 `/api/` 转发给后端，其余页面请求转发给前端。

先准备一张同时覆盖公开站点和管理站点域名的有效证书，可使用包含两个域名的 SAN 证书或覆盖两个域名的通配符证书。站点配置使用以下容器内路径：

| 文件 | 容器内路径 |
| --- | --- |
| 完整证书链 | `/etc/ssl/depends/example.com/fullchain.pem` |
| 证书私钥 | `/etc/ssl/depends/example.com/privkey.pem` |

`example.com` 是证书目录示例，部署时按实际域名目录替换，并同步修改 [nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) 中的 `ssl_certificate`、`ssl_certificate_key` 路径。

在外部 NGINX 的 Compose 服务中发布 `80` 和 `443` 端口，并将宿主机证书根目录只读挂载到 `/etc/ssl/depends`。例如，将以下配置合并到已有的外部 NGINX 服务中，保留该服务原有的其他配置；已有 `/etc/ssl/depends` 根目录挂载可直接复用：

```yaml
ports:
  - "80:80"
  - "443:443"
volumes:
  - /path/to/nginx/conf.d:/etc/nginx/conf.d:ro
  - /path/to/certs:/etc/ssl/depends:ro
```

宿主机 `/path/to/certs/example.com` 目录中必须已存在 `fullchain.pem` 和 `privkey.pem`，且外部 NGINX 能读取这两个文件。端口和挂载由外部 NGINX 的 Compose 管理；修改后在其 Compose 项目中重建 NGINX 容器，使配置生效。

应用启动、域名和证书配置完成后，将独立站点文件放入外部 NGINX 的 `conf.d` 挂载目录，再检查并重载配置。目标目录需要映射到容器内已被 NGINX 加载的配置目录：

```bash
cd /path/to/SudoThink
cp nginx/conf.d/sudothink.conf /path/to/nginx/conf.d/sudothink.conf
docker exec nginx-container nginx -t && docker exec nginx-container nginx -s reload
```

按示例域名配置后，入口为 <https://www.example.com/> 和 <https://admin.example.com/>。确认生产环境 `CORS_ORIGINS` 配置了两个 HTTPS Origin。证书续签并更新挂载目录中的文件后，也需要先运行 `nginx -t`，成功后再执行 `nginx -s reload`，使 NGINX 加载新证书。

外部入口配置完成、域名解析到服务器后，检查两个站点的 API：

```bash
curl --fail https://www.example.com/api/health
curl --fail https://admin.example.com/api/health
```

健康检查应返回 `code: 0`，且 `data.status` 为 `ok`、`data.redis` 为 `true`。公网访问前，确认实际域名已解析到部署服务器。

检查 HTTP 自动跳转：

```bash
curl -I http://www.example.com/api/health
curl -I http://admin.example.com/api/health
```

应返回 `308`，且 `Location` 分别为 `https://www.example.com/api/health`、`https://admin.example.com/api/health`。

#### 更新应用和环境变量

代码更新后先重复构建步骤；修改 `.env` 后重建应用容器以读取新配置：

```bash
cd /path/to/SudoThink
docker compose up -d --force-recreate backend frontend
```

应用容器重建后，NGINX 需要重新解析 upstream 的容器 IP：

```bash
docker exec nginx-container nginx -t && docker exec nginx-container nginx -s reload
```

### 本地运行（不使用 Docker）

本地运行需要 Python 3.15+、Node.js 22+、pnpm（或 npm）、MySQL 8 和 Redis 7。MySQL 和 Redis 可以是本机服务，也可以是发布了端口的外部容器。

先在项目根目录创建环境变量文件：

```bash
cp .env.example .env
```

`.env.example` 默认用于生产部署。本地开发时，将 `.env` 调整为开发模式；如果后端直接运行在宿主机上，数据库和 Redis 应使用宿主机可访问的地址，例如：

```dotenv
APP_ENV=development
APP_DEBUG=true
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
CORS_ORIGINS=http://localhost:5173,http://sudothink.test:5173,http://admin.sudothink.test:5173
VITE_API_BASE_URL=/api
ADMIN_EMAIL=admin@example.com
```

同时填写应用密钥、JWT 密钥、数据库及 Redis 凭据和初始管理员密码，具体含义见上面的环境变量说明。

如果 MySQL 或 Redis 在其他服务器上运行，则把 `MYSQL_HOST` 或 `REDIS_HOST` 改为对应服务器地址，并确保端口可访问。Docker 内部容器名（例如 `mysql-prod`）不能直接用于宿主机上的本地 Python 进程。

初始化并启动后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell 使用 .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt

# 创建数据库、数据表和管理员账号
python scripts/init_db.py

python main.py
```

后端默认监听 `http://localhost:8000`。健康检查地址为 <http://localhost:8000/api/health>。

另开一个终端启动前端：

```bash
cd frontend
pnpm install                 # 或 npm install
pnpm dev                    # 或 npm run dev
```

前端默认访问地址为 <http://localhost:5173>。Vite 会将 `/api` 请求代理到 `http://localhost:8000`，因此本地开发时通常保持 `VITE_API_BASE_URL=/api` 即可。

本地调试两个站点时，可以使用 `sudothink.test` 和 `admin.sudothink.test`。先将 [frontend/src/site.ts](./frontend/src/site.ts) 的 `ADMIN_SITE_HOST` 改为 `admin.sudothink.test`，并将这两个域名加入 [frontend/vite.config.ts](./frontend/vite.config.ts) 的 `server.allowedHosts`，然后重启 Vite。

在本机 `/etc/hosts` 中加入：

```text
127.0.0.1 sudothink.test
127.0.0.1 admin.sudothink.test
```

管理后台访问 <http://admin.sudothink.test:5173/>，公开站点访问 <http://sudothink.test:5173/>。这些记录仅用于本机开发；生产构建前，将 `ADMIN_SITE_HOST` 调整为实际管理域名。

## 管理后台文章创作

在管理站点登录后，进入“文章管理 → 新建文章”，或从顶部“写文章”进入编辑页。

- 正文使用富文本编辑器，支持多级标题、加粗、斜体、下划线、删除线、列表、引用、代码块、对齐、链接、图片和撤销/重做。
- 右侧设置文章摘要和封面图，点击“预览”检查排版；正文图片通过工具栏填写 HTTP/HTTPS 图片 URL 插入，暂不提供本地文件上传。
- “保存草稿”保存到后台，“发布文章”使文章在公开站点可见。已有文章可在文章管理列表中点击“编辑”，继续修改草稿或更新已发布内容。
- 页面显示字数、预计阅读时长和保存状态；有未保存修改时，离开编辑页会提醒。

富文本 HTML 继续保存在现有 `content` 字段中，无需数据库迁移。预览和文章详情统一清洗 HTML 并渲染；已有纯文本正文保留换行展示。草稿仅可通过管理员接口读取，编辑读取不会增加公开阅读量。

前端验证：

```bash
cd frontend
npm ci
npm test
npm run build
```

## 默认 API 路径

| 模块 | 方法 | 路径 |
| --- | --- | --- |
| 健康检查 | GET | `/api/health` |
| 登录 | POST | `/api/auth/login` |
| 文章列表 | GET | `/api/articles` |
| 文章详情 | GET | `/api/articles/<id>` |
| 创建文章 | POST | `/api/articles` |
| 分类列表 | GET | `/api/categories` |
| 标签列表 | GET | `/api/tags` |
| 评论列表 | GET | `/api/articles/<id>/comments` |
