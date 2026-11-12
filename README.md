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
- **Celery** - 异步任务与周期调度（worker / beat）
- **RabbitMQ** - Celery 消息 broker，由外部容器提供
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
│   │   ├── tasks/        # Celery 任务模块
│   │   ├── celery_app.py # Celery 配置与周期任务表
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

1. **Docker 部署**：MySQL、Redis、RabbitMQ、NGINX 由外部容器提供，当前项目的 Compose 构建和运行 backend、frontend、worker、beat。
2. **本地运行**：后端直接由 Python 启动，前端由 Vite 启动，Celery 在独立终端运行；MySQL、Redis 和 RabbitMQ 可以使用本机服务，也可以使用对外发布端口的容器服务。

### Docker 部署（外部基础设施容器）

MySQL、Redis、RabbitMQ、NGINX 由外部容器提供，可以由各自独立的 Compose 管理。应用通过两个共享 Docker 网络连接这些服务。下面使用 `sudothink-data`、`sudothink-proxy` 作为示例网络名：

| 服务 | Docker 网络 | 用途 |
| --- | --- | --- |
| MySQL、Redis | `sudothink-data` | 数据库和缓存 |
| RabbitMQ | `sudothink-data` | 异步任务消息 broker |
| worker、beat | `sudothink-data` | 消费任务、投递周期任务 |
| backend | `sudothink-data`、`sudothink-proxy` | 访问数据库，并接收代理请求 |
| frontend | `sudothink-proxy` | 提供前端静态资源 |
| 外部 NGINX | `sudothink-proxy` | 代理两个站点及 API |

```text
外部 NGINX（sudothink-proxy，HTTP 自动跳转 HTTPS）
   ├── https://www.example.com/   ──> sudothink-frontend:8100
   ├── https://admin.example.com/ ──> sudothink-frontend:8100
   └── 两个站点的 /api/              ──> sudothink-backend:8000
                                      │ sudothink-data
                                      ├──> mysql:3306
                                      └──> redis:6379
```

下文的 `www.example.com`、`admin.example.com` 为示例域名；`mysql-container`、`redis-container`、`rabbitmq-container`、`nginx-container` 和 `/path/to/...` 为容器名、路径占位值，使用时替换为实际配置。

先启动外部基础服务，再创建共享网络并接入对应容器：

```bash
docker network create sudothink-data
docker network create sudothink-proxy

docker network connect --alias mysql sudothink-data mysql-container
docker network connect --alias redis sudothink-data redis-container
docker network connect --alias rabbitmq sudothink-data rabbitmq-container
docker network connect sudothink-proxy nginx-container

docker network inspect sudothink-data sudothink-proxy --format '{{.Name}}'
```

[应用 Compose](./docker-compose.yml) 管理 backend、frontend、worker 和 beat。在应用 `.env` 中将 `DEPENDS_MAIN_NETWORK`、`DEPENDS_PROXY_NETWORK` 设置为实际共享网络名；使用上面的示例时，分别填写 `sudothink-data`、`sudothink-proxy`。已有网络和容器连接可复用，跳过相应创建、接入命令，并确认 MySQL、Redis、RabbitMQ 分别具有 `mysql`、`redis`、`rabbitmq` 网络别名。

前端容器内的 NGINX 监听 `8100`，Compose 默认将宿主机的 `8100` 映射到该端口，支持通过 IP 直接访问公开博客。外部 NGINX 通过 `sudothink-proxy` 网络访问前端容器，并提供宿主机的 `80`、`443` 域名入口。

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
FRONTEND_HTTP_PORT=8100

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
| [nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) | 将公开、管理站点的 HTTP 和 HTTPS `server` 中的 `server_name` 设置为对应域名，例如 `www.example.com admin.example.com` |
| [nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) 中的裸域跳转 | 将独立跳转 `server` 的 `server_name` 设置为裸域，例如 `example.com`，并将 `return 308` 的目标设置为 `https://www.example.com$request_uri` |
| [frontend/src/site.ts](./frontend/src/site.ts) | 将 `ADMIN_SITE_HOST` 设置为管理站域名，例如 `admin.example.com`，只填写主机名；将 `PUBLIC_SITE_URL` 设置为公开博客首页的完整地址，例如 `https://www.example.com/`，用于后台“返回前台”和顶部“首页”链接 |
| `.env` | 设置对应的 `CORS_ORIGINS` 和管理员邮箱 `ADMIN_EMAIL` |

当前管理站主机名在 `frontend/src/site.ts` 中配置，修改后需要重新构建前端。

为裸域、公开站点和管理站点配置指向部署服务器的 DNS 记录，例如 `example.com`、`www.example.com` 和 `admin.example.com`。裸域仅用于跳转到公开站点。

#### 构建、初始化并启动应用

后端 Dockerfile 默认使用 `https://mirrors.aliyun.com` 作为 Debian APT 镜像源。如需使用官方源，在项目 `.env` 中设置 `DEBIAN_MIRROR=https://deb.debian.org`；填写根 URL，不要添加 `/debian` 后缀。Python 包源默认使用 `https://mirrors.aliyun.com/pypi/simple`，可在 `.env` 中设置 `PYPI_INDEX_URL=https://pypi.org/simple` 改用官方源。Compose 会将这两个变量作为 backend 的构建参数传入，修改后需重新构建后端镜像，不会影响已运行的容器。

Docker 镜像源、APT 软件源和 Python 包源相互独立；配置 Docker 镜像加速不会加速构建中的 APT 或 pip 下载。

在项目根目录依次构建后端、前端，再初始化并启动应用：

```bash
cd /path/to/SudoThink
docker compose config --quiet
docker compose build backend
docker compose build frontend

# 首次部署：创建数据库、数据表和管理员账号
docker compose run --rm backend python scripts/init_db.py

docker compose up -d backend frontend worker beat
docker compose ps
docker compose logs --tail=100 backend
```

如果后端构建较慢，使用 `docker compose --progress plain build backend` 查看具体耗时步骤。持续低速下载仍可能耗时较长，需要根据日志检查软件源和网络。

#### 通过 IP 和端口访问

应用启动后，公开博客可通过 `http://服务器IP:8100/` 访问，无需配置域名、证书或外部 NGINX。前端容器同时将同源的 `/api/` 请求转发到后端，`VITE_API_BASE_URL` 保持 `/api`。

宿主机端口由 `.env` 中的 `FRONTEND_HTTP_PORT` 控制，默认 `8100`。如端口已占用，可改为其他空闲端口，再执行 `docker compose up -d frontend` 应用配置。确保服务器防火墙和云安全组允许访问所选 TCP 端口。

管理后台继续通过独立管理域名识别，IP 入口展示公开博客。域名访问仍使用下文的 HTTPS 配置，`80` 端口自动跳转到 HTTPS。

可以直接检查同源 API：

```bash
curl --fail http://服务器IP:8100/api/health
```

#### 接入外部 NGINX

[nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) 默认通过 HTTPS 提供公开站点和管理站点，支持 TLS 1.2、TLS 1.3 和 HTTP/2。这两个站点的 HTTP 请求会返回 `308`，保留主机名、路径和查询参数并跳转到 HTTPS。HTTPS 站点使用稳定容器名 `sudothink-backend:8000`、`sudothink-frontend:8100` 作为 upstream；两个站点的 `/api/` 转发给后端，其余页面请求转发给前端。

裸域使用独立的跳转配置，HTTP 和 HTTPS 请求均返回 `308`，跳转到公开站点的 HTTPS 地址；例如 `https://example.com/articles/1?from=apex` 跳转到 `https://www.example.com/articles/1?from=apex`，保留路径和查询参数。若外部 NGINX 的其他配置已在相同监听地址和端口下声明该裸域，应合并规则或移除重复的 `server_name` 声明，避免跳转规则与已有站点冲突。

先准备一张同时覆盖裸域、公开站点和管理站点域名的有效证书，例如包含 `example.com`、`www.example.com` 和 `admin.example.com` 的 SAN 证书，或同时包含 `example.com` 和 `*.example.com` 的证书。`*.example.com` 本身不覆盖裸域 `example.com`，HTTPS 裸域跳转也需要有效证书才能完成 TLS 握手。站点和裸域跳转共用以下容器内路径：

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

检查裸域在 HTTP 和 HTTPS 下均跳转到公开站点，并保留路径和查询参数：

```bash
curl -I 'http://example.com/articles/1?from=apex'
curl -I 'https://example.com/articles/1?from=apex'
```

两者均应返回 `308`，且 `Location` 为 `https://www.example.com/articles/1?from=apex`。

#### 更新应用和环境变量

代码更新后先重复构建步骤；修改 `.env` 后重建应用容器以读取新配置：

```bash
cd /path/to/SudoThink
docker compose up -d --force-recreate backend frontend worker beat
```

应用容器重建后，NGINX 需要重新解析 upstream 的容器 IP：

```bash
docker exec nginx-container nginx -t && docker exec nginx-container nginx -s reload
```

### 本地运行（不使用 Docker）

本地运行需要 Python 3.15+、Node.js 22+、pnpm（或 npm）、MySQL 8、Redis 7；运行异步任务还需 RabbitMQ。MySQL、Redis 和 RabbitMQ 可以是本机服务，也可以是发布了端口的外部容器。

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
CORS_ORIGINS=http://localhost:8100,http://sudothink.test:8100,http://admin.sudothink.test:8100
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

前端默认访问地址为 <http://localhost:8100>。Vite 会将 `/api` 请求代理到 `http://localhost:8000`，因此本地开发时通常保持 `VITE_API_BASE_URL=/api` 即可。

本地调试两个站点时，可以使用 `sudothink.test` 和 `admin.sudothink.test`。先将 [frontend/src/site.ts](./frontend/src/site.ts) 的 `ADMIN_SITE_HOST` 改为 `admin.sudothink.test`，并将这两个域名加入 [frontend/vite.config.ts](./frontend/vite.config.ts) 的 `server.allowedHosts`，然后重启 Vite。

在本机 `/etc/hosts` 中加入：

```text
127.0.0.1 sudothink.test
127.0.0.1 admin.sudothink.test
```

管理后台访问 <http://admin.sudothink.test:8100/>，公开站点访问 <http://sudothink.test:8100/>。这些记录仅用于本机开发；生产构建前，将 `ADMIN_SITE_HOST` 调整为实际管理域名。

## Celery 异步任务与周期调度

项目提供两个独立服务：`worker` 消费并执行任务，`beat` 按调度表向 RabbitMQ 投递周期任务。RabbitMQ 由外部容器提供；两个服务与 backend 复用同一个 `sudothink-backend` 镜像、任务代码和根目录 `.env`，只接入数据网络，不开放 HTTP 端口。

在 `.env` 配置已有 RabbitMQ 的连接信息。Docker 中使用容器网络别名 `rabbitmq`；后端和 Celery 在宿主机直接运行时，改为宿主机可访问的地址及已发布的 AMQP 端口：

```dotenv
RABBITMQ_HOST=rabbitmq
RABBITMQ_PORT=5672
RABBITMQ_USER=sudothink
RABBITMQ_PASSWORD=replace-with-a-strong-rabbitmq-password
RABBITMQ_VHOST=/
CELERY_RESULT_BACKEND=
CELERY_TIMEZONE=Asia/Shanghai
CELERY_WORKER_CONCURRENCY=2
```

使用已创建的非 `guest` 用户，并确认该用户对目标 vhost 拥有 configure、write、read 权限。`RABBITMQ_VHOST=/` 使用默认 vhost，也可以填写已创建并授权的专用 vhost。用户名、密码和 vhost 填原始值，后端会自动编码特殊字符。项目使用 `sudothink` 任务队列和独立的控制交换机，避免混用默认 `celery` 队列。

Docker 部署在构建 backend 镜像后启动服务：

```bash
docker compose build backend
docker compose up -d backend worker beat
docker compose ps
docker compose logs --tail=100 worker beat

# 向 worker 手动投递诊断任务，在 worker 日志中确认执行成功并返回 pong。
docker compose exec backend celery -A app.celery_app:celery_app call app.tasks.diagnostics.ping
docker compose logs --tail=20 worker
```

更新任务代码或依赖后，重新构建 backend 并重建 backend、worker、beat，确保生产者和消费者运行同一版本。修改 RabbitMQ 凭据或 Celery 环境变量后，也需重建这三个容器。broker 暂不可用时 worker 会重试连接；只有连接成功且日志出现 `ready`，才表示可以消费任务。

直接本地运行时，设置 `RABBITMQ_HOST=127.0.0.1` 及实际端口，并激活后端虚拟环境、安装 `requirements.txt`。在两个独立终端从 `backend` 目录启动：

```bash
# 终端一
celery -A app.celery_app:celery_app worker --loglevel=INFO

# 终端二，状态文件放在被 Git 忽略的 data 目录中
mkdir -p data
celery -A app.celery_app:celery_app beat --loglevel=INFO --schedule=data/celerybeat-schedule
```

macOS / Linux 默认使用 prefork 进程池；Windows 本地调试可在 worker 命令添加 `--pool=solo`。同一套调度表只运行一个 beat，避免重复投递。Docker 的 beat 状态文件保存到独立命名卷 `celerybeat-state`，容器重建后保留调度状态。

### 添加任务和周期计划

在 `backend/app/tasks` 下新增任务模块，并在该目录的 `__init__.py` 中导入。任务使用 Celery 的同步入口，例如已有的 `app.tasks.diagnostics.ping`；通过 `ping.delay()` 或 `celery_app.send_task("app.tasks.diagnostics.ping")` 投递。Sanic 请求处理中投递任务会进行同步 broker I/O，应使用 `await asyncio.to_thread(ping.delay)`，避免阻塞事件循环。

周期计划集中在 [backend/app/celery_app.py](./backend/app/celery_app.py) 的 `BEAT_SCHEDULE` 中，默认是空字典，beat 启动后等待配置计划。新增计划时填写已注册的任务名和 `schedule`，例如 `crontab(hour=2, minute=0)` 表示按 `CELERY_TIMEZONE` 每天凌晨两点投递；修改后重建 worker 和 beat。

任务不复用 Sanic 的数据库和 Redis 生命周期。未来任务需要异步 ORM 或缓存时，应在任务进程中自行建立并关闭连接；不要直接把 `async def` 注册为 Celery 任务，也不要跨事件循环复用 ORM 连接。任务应按可能重复执行设计为幂等。

默认不保存任务结果，适合仅需后台执行的任务；`.delay()` 返回任务 ID，但不能直接读取执行结果。如需查询结果，可设置 Celery 支持的 `CELERY_RESULT_BACKEND`，并重建服务。仅接受 JSON 消息，不接受 pickle 等序列化格式。

## 外观模式

公开博客与管理后台均支持浅色、深色和跟随系统三种模式，默认跟随系统。通过顶部导航中的外观选择器切换；跟随系统时，系统外观变化会即时生效。

手动选择保存在当前站点的浏览器存储中，刷新或重新访问后仍会保留，同一站点的多个标签页会同步选择。文章正文、富文本编辑器、预览、表单、表格和弹窗统一适配主题。

## ICP 备案信息

在项目根目录 `.env` 中设置 `VITE_ICP_NUMBER` 为实际 ICP 备案号，公开站点和管理站点的页脚会显示该号码，并链接到工信部备案查询网站 <https://beian.miit.gov.cn/>。默认留空时隐藏备案信息，个人备案号无需写入代码或提交到仓库。

该配置在前端构建时生效。Docker 部署修改后执行 `docker compose build frontend`，再执行 `docker compose up -d --no-deps frontend`；本地开发修改后重启 Vite，直接部署静态文件时重新执行 `npm run build`。如果启用了静态资源 CDN，请按下文的 CDN 发布流程上传资源并手动刷新 CDN 后再切换前端。

## 工具箱

公开站点顶部导航的“工具箱”位于“关于我”之前，入口为 `/tools`。工具按需加载，目录可以切换模块，也可以通过 `/tools?tool=json` 这样的链接直接打开指定工具。

| 工具 | 链接参数 `tool` | 功能 |
| --- | --- | --- |
| 时间戳转换 | `timestamp` | 日期与秒/毫秒时间戳双向转换，支持本地时区、UTC 和 ISO 8601 偏移 |
| 二维码生成器 | `qrcode` | 文本生成二维码、下载 PNG、上传图片识别二维码内容 |
| 加密解密 | `crypto` | AES、DES、3DES 口令加解密，RSA PEM 密钥加解密，MD5/SHA 摘要和 UTF-8 Base64 编解码 |
| 随机字符串 | `random` | 自定义长度、数量、大小写字母/数字/符号、字符集、排除字符和前后缀 |
| 计算器 | `calculator` | 四则运算、括号、负数、小数和取模，支持按键与键盘输入 |
| JSON 解析 | `json` | 校验、格式化、压缩、文本与 JSON 字符串互转，保留大整数与小数精度 |
| cron 表达式 | `cron` | 5/6 字段表达式的中文解释，按指定时区预览未来 10 次执行 |
| 进制转换 | `radix` | 二、八、十、十六进制整数互转，使用 BigInt 保留精度 |

工具的输入、图片和密钥均在浏览器本地处理，不发送给后端，也不保存在浏览器存储中。复制功能支持 HTTPS 和通过 IP/HTTP 访问；计算器的 Enter 用于计算、Escape 用于清空，`%` 表示余数。加解密工具会标明所用格式，摘要功能生成单向摘要。

随机字符串工具支持 1–256 位随机部分、每批 1–100 条结果。勾选的字符类型与自定义字符合并后去重，可排除指定字符及易混淆字符 `0Oo1Il`；每个位置从可用字符集中随机选取，不保证每种类型都会出现。关闭字符重复时，同一条结果的随机部分不会重复使用字符，长度不能超过可用字符数；不同结果之间仍可能相同。前后缀另行添加，不计入随机长度和字符重复规则。长度按 Unicode 码点计数，支持中文和单个表情；自定义字符不接受空白、控制字符或不可见格式字符。

## 管理后台文章创作

在管理站点登录后，进入“文章管理 → 新建文章”，或从顶部“写文章”进入编辑页。

- 正文使用富文本编辑器，支持多级标题、加粗、斜体、下划线、删除线、列表、引用、代码块、对齐、链接、图片和撤销/重做。
- 右侧选择一个分类、多个标签，设置摘要和封面图，点击“预览”检查排版；正文支持图片 URL，也可上传本地图片和视频，封面支持本地图片上传。上传功能需要先配置下文的阿里云 OSS 和 CDN。
- “保存草稿”保存到后台，“发布文章”使文章在公开站点可见。已有文章可在文章管理列表中点击“编辑”，继续修改草稿或更新已发布内容。
- 页面显示字数、预计阅读时长和保存状态；有未保存修改时，离开编辑页会提醒。

文章富文本 HTML 继续保存在现有 `content` 字段中。预览和文章详情统一清洗 HTML 并渲染；已有纯文本正文保留换行展示。草稿仅可通过管理员接口读取，编辑读取不会增加公开阅读量。

### 阿里云 OSS 图片、视频上传

管理员在正文工具栏选择本地图片或视频，或在封面处上传图片。浏览器先向后台申请 5 分钟有效的上传凭证，再直接上传到阿里云 OSS；进度和取消在上传界面显示，成功后插入 CDN 地址。上传期间请等待完成或取消后再保存文章；离开编辑页会提醒。共享编辑器的“关于我”也支持媒体上传。

支持 JPG/JPEG、PNG、GIF、WebP、AVIF 图片，以及 MP4、WebM 视频；默认单张图片最大 10 MB、单个视频最大 200 MB。视频以原文件存储，使用浏览器原生播放器，不执行转码；编码需可被目标浏览器播放。正文可以只有图片或视频。原有外链继续保留，若需迁移到 OSS，请重新上传并替换链接。

在根目录 `.env` 填写配置；Docker 和直接运行后端均读取这些变量：

```dotenv
ACCESS_KEY_ID=your-ram-access-key-id
ACCESS_KEY_SECRET=your-ram-access-key-secret
OSS_SECURITY_TOKEN=
OSS_REGION=cn-hangzhou
OSS_BUCKET=your-bucket
OSS_ENDPOINT=https://oss-cn-hangzhou.aliyuncs.com
CDN_BASE_URL=https://cdn.example.com
OSS_MEDIA_PREFIX=media
OSS_STATIC_PREFIX=static
OSS_IMAGE_MAX_BYTES=10485760
OSS_VIDEO_MAX_BYTES=209715200
OSS_MEDIA_CACHE_SECONDS=31536000
```

`OSS_REGION` 和公网 `OSS_ENDPOINT` 必须与 Bucket 所在地域一致；上传地址由后端生成，不使用 CDN 域名上传。CDN 地址是阿里云 CDN 中配置的自定义 HTTPS 资源域名，也可带路径前缀；该前缀必须对应 CDN 的回源路径规则。没有配置 OSS/CDN 时，本地上传入口不可用，图片 URL 插入仍可使用。

密钥只供后端签名和静态资源发布脚本使用，不能设置为 `VITE_` 变量。前端只接收短期表单签名，不接收 AccessKey Secret。使用专用 RAM 用户，权限限定到目标 Bucket 的媒体和静态资源目录，例如：

```json
{
  "Version": "1",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["oss:PutObject"],
    "Resource": [
      "acs:oss:*:*:your-bucket/media/*",
      "acs:oss:*:*:your-bucket/static/*"
    ]
  }]
}
```

修改目录前缀时同步调整 RAM Resource。也支持 STS 临时凭据，需同时填写 `OSS_SECURITY_TOKEN` 并在过期前更新；项目不会自动续期。签名接口只允许已登录的管理员申请，限制文件后缀、声明 MIME、大小和服务端生成的单个随机对象键。它不执行文件内容审核、恶意文件扫描或视频转码。

在 OSS Bucket 的跨域规则中允许实际管理站 Origin（例如 `https://admin.example.com`）执行 `POST`，允许请求头 `*`，可暴露 `ETag` 和 `x-oss-request-id`，预检缓存时间可设为 600 秒。本地调试时另行添加准确的管理站 HTTP Origin 和端口。应用的 `CORS_ORIGINS` 与 OSS 跨域规则分别管理，两处都需正确配置。

在阿里云 CDN 创建 `cdn.example.com` 加速域名，以该 OSS Bucket 为源站，完成 CNAME 解析并配置 HTTPS 证书。推荐保持 Bucket 私有，按阿里云文档开启 CDN 私有 Bucket 回源授权；上传使用签名授权，公开访问使用 CDN。若自行选择公共读 Bucket，确认对象 ACL 和 Bucket 策略允许读取。这里的 CDN URL 用于公开博客，未实现访客 URL 鉴权，不要上传私密资料。

CDN 对公开 JS、字体等跨域资源需要返回 `Access-Control-Allow-Origin: *`，并正确处理 `GET`、`HEAD`、`OPTIONS`；这是公开资源的读取规则，OSS 上传规则仍限定管理站 Origin。开启视频 Range 回源，保留正确的 `Content-Type`，以支持 MP4/WebM 播放和拖动进度。`media/*` 可设置合理缓存时间，上传对象使用随机文件名；删除文章或取消上传不会自动删除 OSS 对象。

`OSS_MEDIA_CACHE_SECONDS` 控制新上传图片、视频的缓存时长，单位为秒，须为非负整数，默认 `31536000`（365 天）。正数会在上传时写入 OSS 对象元数据 `Cache-Control: public,max-age=<秒数>,immutable`，设为 `0` 则写入 `Cache-Control: no-store`。正文、封面、“关于我”和打赏收款码的媒体上传共用该配置；前端 JS/CSS 等静态资源使用下文的独立缓存策略。CDN 需遵循源站缓存头；如果路径规则强制指定缓存时长，应同步调整该规则。

修改该参数只影响后续上传，已有对象保留原元数据。已有资源需修改 OSS 的 `Cache-Control` 元数据并刷新 CDN，或重新上传生成新 URL；浏览器已保存长缓存的资源优先通过新 URL 更新。

Docker 修改 `.env` 后重建后端容器，直接运行则重启后端。直传文件不经过应用 NGINX/Sanic，因此不需要为视频提高应用请求体上限。

### 前端静态资源通过 CDN 发布

图片和视频上传后自动使用 `CDN_BASE_URL`。前端 JS、CSS、字体和构建中的图片在生产构建时也使用以下两项配置，自动生成固定静态目录：

```dotenv
CDN_BASE_URL=https://cdn.example.com
OSS_STATIC_PREFIX=static
```

生产构建在 `CDN_BASE_URL` 非空时，自动以 `CDN_BASE_URL/OSS_STATIC_PREFIX/` 为资源地址，例如 `https://cdn.example.com/static/`；留空 `CDN_BASE_URL` 则使用站点本身。开发模式始终从本地 Vite 加载。每次发布复用固定目录，构建资源使用稳定文件名，不附加内容哈希，上传时覆盖同名文件。页面 HTML 仍由站点提供，API 保持 `/api` 同源。

Vite 和发布脚本使用根目录的同一份 `.env`。Docker Compose 将公开的 `CDN_BASE_URL` 和 `OSS_STATIC_PREFIX` 作为 frontend 构建参数传入；访问密钥仍仅由后端和发布脚本使用，不会作为前端构建参数或客户端环境变量传入。修改这两项中的任一项后，需重新构建前端。

项目提供 [backend/scripts/publish_static_assets.py](./backend/scripts/publish_static_assets.py)。脚本直接从 `CDN_BASE_URL` 和 `OSS_STATIC_PREFIX` 推导上传目录并校验构建地址，无需另设资源 URL。验证全部文件后，将静态文件上传到固定目录，设置正确的 MIME 和 `Cache-Control: public,max-age=0,s-maxage=31536000,must-revalidate`。浏览器使用前会校验缓存，CDN 可缓存一年；CDN 需遵循源站缓存头，或为 `/static/` 配置一年缓存并让浏览器缓存遵循源站（修改了 `OSS_STATIC_PREFIX` 时使用对应路径）。脚本不上传 `index.html`，不清理云端历史资源，也不自动刷新 CDN。

直接运行时，激活后端虚拟环境后，在项目根目录执行：

```bash
cd frontend
npm ci
npm run build
cd ..
python backend/scripts/publish_static_assets.py frontend/dist --dry-run
python backend/scripts/publish_static_assets.py frontend/dist
```

上传完成后，在阿里云 CDN 控制台手动执行目录刷新，例如刷新 `https://cdn.example.com/static/`，等待刷新完成并确认新构建 `index.html` 引用的 CDN 脚本和样式已更新且可通过 HTTPS 读取，再把同一份 `frontend/dist` 部署到站点。固定 URL 会覆盖线上同名资源，上传及刷新期间已打开的页面可能受影响，建议选择低流量时段发布。

Docker 部署无需在宿主机安装 Python：从构建好的前端镜像导出资源，通过后端临时容器上传。以下命令在项目根目录依次执行，保持使用同一份 `.env`：

```bash
docker compose build backend frontend

# 临时容器只用于导出构建产物，不启动服务。
cdn_dist_dir=$(mktemp -d)
cdn_export_container=$(docker create sudothink-frontend)
docker cp "$cdn_export_container:/usr/share/nginx/html/." "$cdn_dist_dir/"
docker rm "$cdn_export_container"

docker compose run --rm --no-deps --interactive=false \
  --volume "$cdn_dist_dir:/static-dist:ro" \
  backend python scripts/publish_static_assets.py /static-dist --dry-run
docker compose run --rm --no-deps --interactive=false \
  --volume "$cdn_dist_dir:/static-dist:ro" \
  backend python scripts/publish_static_assets.py /static-dist
```

`--interactive=false` 避免临时容器读取标准输入，支持通过 `ssh ... bash -s` 执行整段脚本。发布脚本失败时先修正配置或网络；上传成功后手动刷新 CDN 静态目录，等待刷新完成并检查新资源 URL，再执行 `docker compose up -d --no-build backend frontend worker beat`，并按前文检查和重载外部 NGINX。CDN 上的 JS/CSS 必须已更新且可访问后才切换前端，否则页面可能加载到旧资源或因缺少资源而无法打开。

已有的 `release-*` 目录不会自动删除。迁移并确认站点使用固定目录后，可自行清理不再引用的旧目录。

配置参考：[OSS V4 表单签名](https://help.aliyun.com/zh/oss/developer-reference/signature-version-4-recommend)、[OSS CORS](https://help.aliyun.com/zh/oss/user-guide/configure-cross-origin-resource-sharing)、[CDN 加速 OSS 与私有回源](https://help.aliyun.com/zh/oss/user-guide/use-cdn-to-accelerate-access-to-oss)。

前端验证：

```bash
cd frontend
npm ci
npm test
npm run build
```

## 关于我与分类导航

博客顶部的“关于我”进入独立页面。在管理后台打开“关于我”，编辑页面标题和富文本正文，可先预览再保存。保存后刷新公开页面即可看到更新，无需重新构建前端；尚未填写正文时显示待完善提示。

管理后台的“分类管理”支持新增、编辑和删除分类，以及设置名称、Slug、描述和权重。权重为 `0` 至 `999999` 的整数，默认 `0`，数值越大越靠前；相同权重按创建顺序排列。分类按此顺序出现在博客顶部导航和首页分类栏，点击后筛选对应文章，地址中的分类参数支持刷新和分享。

在文章编辑页选择分类后保存或发布。删除分类会将其文章改为未分类，文章内容保留。

### 标签管理

在管理后台打开“标签管理”，可新增、编辑和删除标签。标签名称去除首尾空白后为 1 至 6 个字符，前端输入和后端接口均进行校验；Slug 留空时根据名称自动生成。删除标签会移除它与文章的关联，文章内容保留。

文章编辑页的“文章标签”支持搜索和多选，保存草稿或发布时一并保存；重新编辑会回显已有选择，可单独移除标签或全部清空。每篇文章最多属于一个分类，可以拥有多个标签，二者均为选填。标签功能复用已有标签表和关联表，无需额外数据库升级；尚未升级分类权重与“关于我”的旧安装仍需执行下文升级步骤。

## 文章打赏

管理后台的“打赏设置”支持启用或关闭打赏，分别上传、预览和清除微信、支付宝收款码，也可填写完整的 HTTP/HTTPS 图片地址。上传复用阿里云 OSS 和 CDN 配置；收款码以完整图片展示，建议使用清晰、带留白的原图。

至少设置一种收款方式后可启用打赏，点击“保存设置”生效。读者可从公开站点右侧的固定打赏入口查看收款码；同时设置两种时可切换。默认关闭，关闭后保留已保存的图片地址；未配置或设置加载失败时不显示入口。该功能只展示收款码，由读者使用微信或支付宝扫码付款。

新安装运行 `init_db.py` 会自动创建打赏设置表；已有安装先执行下文升级脚本。收款码通过后台保存到数据库，无需写入 `.env` 或重新构建前端。

## 访客评论与审核

已发布文章的底部提供评论区，无需注册或登录。昵称必填，为 1–32 个中文、英文字母、数字或下划线；邮箱选填；评论正文为 1–1000 个字符。首次提交成功后，当前浏览器的 localStorage 只保存昵称和邮箱，并收起身份填写框；再次访问时直接使用已保存的信息，显示当前评论昵称。点击“修改信息”可重新编辑，取消修改会恢复原身份并保留评论正文；修改后的身份在评论提交成功后保存。正文不保存在浏览器中。浏览器禁止存储时仍可正常提交。

管理后台的“评论管理”位于“文章管理”下方，统一查看和审核评论，支持按文章以及“全部、待审核、已通过、已驳回”状态组合筛选。文章选择器可按标题搜索，切换筛选条件会返回第一页。管理员可在列表查看昵称、邮箱、提交 IP、归属地和 User-Agent，直接通过或驳回评论；驳回会保留记录，已驳回评论可重新通过，已通过评论也可驳回并停止公开展示。

新评论默认为待审核，通过后才在文章下方公开展示。公开评论直接显示城市名称，境外显示国家。点击评论旁的“回复”可回复其他游客，沿用已保存的身份信息；表单显示回复对象，取消回复保留正文。回复同样需要审核，通过后显示回复对象昵称；原评论被驳回后，不再显示其昵称上下文。

公开接口只返回审核通过的评论及其昵称、归属地、正文、时间和回复关系，不公开邮箱、原始 IP 或 User-Agent。后端从请求头记录 User-Agent，最长保留 1024 个字符，旧评论的该字段为空。评论按每页 10 条展示；草稿文章不接受公开评论。评论提交成功后显示待审核提示，2 秒后自动消失。

提交按来源 IP 限制为每 30 秒一条、每 10 分钟最多五条，超限返回 `429`；限流状态保存在 Redis。Redis 暂不可用时评论仍可提交。

### qqwry 离线 IP 归属地

后端使用传统 QQWry IPv4 格式的 `qqwry.dat` 本地查询归属地，无需在线定位接口或 API Key。国内展示城市简称，例如“江苏省南京市”显示为“南京”、“浙江省杭州市”显示为“杭州”，直辖市如“北京市”显示为“北京”；自治州、地区保留名称，境外显示国家，不展示区县、运营商或详细地址。数据库保留完整归属地，已有评论也按相同规则展示，无需改写数据。仅能定位到省时显示省份；IPv6、内网地址、缺失或无法读取的数据库显示“未知”，不阻止评论提交。

仓库提供 [backend/data/qqwry.dat](./backend/data/qqwry.dat)，拉取代码后即可使用。更新时可从[纯真官网](https://www.cz88.net/)或已获授权的数据渠道获取兼容文件，并遵守数据提供方的使用条款。项目不自动下载；`.czdb` 与传统 `.dat` 格式不同，不能直接改名使用。

Docker 部署时，将文件放到 `backend/data/qqwry.dat`，Compose 会将 `backend/data` 只读挂载到后端的 `/app/data`。在 `.env` 中配置：

```dotenv
QQWRY_DB_PATH=data/qqwry.dat
# 填写实际的代理容器 IP 或专用代理网络 CIDR，多个以逗号分隔。
TRUSTED_PROXY_CIDRS=172.30.0.0/24
```

上面的网段仅为示例。可以用 `docker network inspect 网络名 --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'` 查看实际代理网络网段；只填写受信任代理所在的网络或固定 IP，不要填写 `0.0.0.0/0` 或 `::/0`。通过本项目的独立外部 NGINX 和前端容器入口访问时，后端必须信任实际转发请求的 NGINX 容器地址，才能记录访客 IP。

直接本地运行也可把文件放到 `backend/data/qqwry.dat`，使用相同的 `QQWRY_DB_PATH=data/qqwry.dat`；相对路径始终以 `backend` 为基准，也可配置绝对路径。没有反向代理时，`TRUSTED_PROXY_CIDRS` 留空，后端直接记录连接来源 IP；如果使用本机 NGINX 或 Vite 代理，需要按实际代理来源配置受信任地址，并确保代理覆盖 `X-Forwarded-For`。

项目的两份 NGINX 配置会用连接来源覆盖 `X-Forwarded-For`。后端仅接受来自受信任代理的转发信息，忽略其他来源提供的 IP 请求头。如果另有 CDN 或负载均衡，需要先在入口 NGINX 中依据提供方的官方网段配置真实 IP，再传递给后端。

修改 `.env` 后重建后端容器；更新离线库后，后续评论会使用更新的数据，已保存的评论归属地保持原记录。首次部署由初始化脚本建表；已有安装先执行下文数据库升级，再启动新版后端。

## 已有数据库升级

首次部署运行 `init_db.py` 会创建完整结构。已有安装需要在启动新版后端前运行一次升级脚本，为分类补齐权重字段，创建“关于我”和打赏设置数据表，并为评论补齐访客昵称、邮箱、IP、归属地、User-Agent、可空的用户关联和驳回状态字段。已有评论会保留原审核结果；旧版中已被驳回删除的记录无法恢复。脚本可以重复执行，会保留已有文章、分类、评论、管理员及站点设置；数据库账号需要 `CREATE` 和 `ALTER` 权限。

Docker 部署在项目根目录执行：

```bash
docker compose build backend
docker compose build frontend
docker compose run --rm --no-deps backend python scripts/upgrade_site_content.py
docker compose up -d backend frontend worker beat
```

容器重建后，按[更新应用和环境变量](#更新应用和环境变量)中的步骤检查并重载外部 NGINX。

直接运行时，激活后端虚拟环境后，在项目根目录执行，再重新启动后端：

```bash
python backend/scripts/upgrade_site_content.py
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
| 新增分类 | POST | `/api/categories`（管理员） |
| 更新分类 | PUT | `/api/categories/<id>`（管理员） |
| 删除分类 | DELETE | `/api/categories/<id>`（管理员） |
| 关于我 | GET | `/api/about` |
| 编辑关于我 | GET / PUT | `/api/admin/about`（管理员） |
| 公开打赏设置 | GET | `/api/donations` |
| 读取 / 保存打赏设置 | GET / PUT | `/api/admin/donations`（管理员） |
| 上传配置 | GET | `/api/admin/uploads/config`（管理员） |
| OSS 直传凭证 | POST | `/api/admin/uploads/policy`（管理员） |
| 标签列表 | GET | `/api/tags` |
| 新增标签 | POST | `/api/tags`（管理员） |
| 更新标签 | PUT | `/api/tags/<id>`（管理员） |
| 删除标签 | DELETE | `/api/tags/<id>`（管理员） |
| 评论列表 | GET | `/api/articles/<id>/comments` |
| 提交访客评论 | POST | `/api/articles/<id>/comments` |
| 评论管理列表 | GET | `/api/admin/comments`（管理员，支持 `article_id`、`status`、`page`、`size`） |
| 通过 / 驳回评论 | POST | `/api/comments/<id>/approve` / `/api/comments/<id>/reject`（管理员或文章作者） |
