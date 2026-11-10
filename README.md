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
   ├── https://www.example.com/   ──> sudothink-frontend:8100
   ├── https://admin.example.com/ ──> sudothink-frontend:8100
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
| [nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) | 将 HTTP、HTTPS 两个 `server` 中的 `server_name` 都设置为公开站点和管理站点域名，例如 `www.example.com admin.example.com` |
| [frontend/src/site.ts](./frontend/src/site.ts) | 将 `ADMIN_SITE_HOST` 设置为管理站域名，例如 `admin.example.com`，只填写主机名 |
| `.env` | 设置对应的 `CORS_ORIGINS` 和管理员邮箱 `ADMIN_EMAIL` |

当前管理站主机名在 `frontend/src/site.ts` 中配置，修改后需要重新构建前端。

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

docker compose up -d backend frontend
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

[nginx/conf.d/sudothink.conf](./nginx/conf.d/sudothink.conf) 默认通过 HTTPS 提供两个站点，支持 TLS 1.2、TLS 1.3 和 HTTP/2。HTTP 请求会返回 `308`，保留主机名、路径和查询参数并跳转到 HTTPS。HTTPS 站点使用稳定容器名 `sudothink-backend:8000`、`sudothink-frontend:8100` 作为 upstream；两个站点的 `/api/` 转发给后端，其余页面请求转发给前端。

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

## 外观模式

公开博客与管理后台均支持浅色、深色和跟随系统三种模式，默认跟随系统。通过顶部导航中的外观选择器切换；跟随系统时，系统外观变化会即时生效。

手动选择保存在当前站点的浏览器存储中，刷新或重新访问后仍会保留，同一站点的多个标签页会同步选择。文章正文、富文本编辑器、预览、表单、表格和弹窗统一适配主题。

## 工具箱

公开站点顶部导航的“工具箱”位于“关于我”之前，入口为 `/tools`。工具按需加载，目录可以切换模块，也可以通过 `/tools?tool=json` 这样的链接直接打开指定工具。

| 工具 | 链接参数 `tool` | 功能 |
| --- | --- | --- |
| 时间戳转换 | `timestamp` | 日期与秒/毫秒时间戳双向转换，支持本地时区、UTC 和 ISO 8601 偏移 |
| 二维码生成器 | `qrcode` | 文本生成二维码、下载 PNG、上传图片识别二维码内容 |
| 加密解密 | `crypto` | AES、DES、3DES 口令加解密，RSA PEM 密钥加解密，MD5/SHA 摘要和 UTF-8 Base64 编解码 |
| 生成随机数 | `random` | 自定义范围、数量、小数精度、重复规则与排序 |
| 计算器 | `calculator` | 四则运算、括号、负数、小数和取模，支持按键与键盘输入 |
| JSON 解析 | `json` | 校验、格式化、压缩、文本与 JSON 字符串互转，保留大整数与小数精度 |
| cron 表达式 | `cron` | 5/6 字段表达式的中文解释，按指定时区预览未来 10 次执行 |
| 进制转换 | `radix` | 二、八、十、十六进制整数互转，使用 BigInt 保留精度 |

工具的输入、图片和密钥均在浏览器本地处理，不发送给后端，也不保存在浏览器存储中。复制功能支持 HTTPS 和通过 IP/HTTP 访问；计算器的 Enter 用于计算、Escape 用于清空，`%` 表示余数。加解密工具会标明所用格式，摘要功能生成单向摘要。

## 管理后台文章创作

在管理站点登录后，进入“文章管理 → 新建文章”，或从顶部“写文章”进入编辑页。

- 正文使用富文本编辑器，支持多级标题、加粗、斜体、下划线、删除线、列表、引用、代码块、对齐、链接、图片和撤销/重做。
- 右侧选择一个分类、多个标签，设置摘要和封面图，点击“预览”检查排版；正文图片通过工具栏填写 HTTP/HTTPS 图片 URL 插入，暂不提供本地文件上传。
- “保存草稿”保存到后台，“发布文章”使文章在公开站点可见。已有文章可在文章管理列表中点击“编辑”，继续修改草稿或更新已发布内容。
- 页面显示字数、预计阅读时长和保存状态；有未保存修改时，离开编辑页会提醒。

文章富文本 HTML 继续保存在现有 `content` 字段中。预览和文章详情统一清洗 HTML 并渲染；已有纯文本正文保留换行展示。草稿仅可通过管理员接口读取，编辑读取不会增加公开阅读量。

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

### 已有数据库升级

首次部署运行 `init_db.py` 会创建完整结构。已有安装需要在启动新版后端前运行一次升级脚本，为分类添加权重字段并创建“关于我”数据表。脚本可以重复执行，会保留已有文章、分类和管理员数据；数据库账号需要 `CREATE` 和 `ALTER` 权限。

Docker 部署在项目根目录执行：

```bash
docker compose build backend
docker compose build frontend
docker compose run --rm --no-deps backend python scripts/upgrade_site_content.py
docker compose up -d backend frontend
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
| 标签列表 | GET | `/api/tags` |
| 新增标签 | POST | `/api/tags`（管理员） |
| 更新标签 | PUT | `/api/tags/<id>`（管理员） |
| 删除标签 | DELETE | `/api/tags/<id>`（管理员） |
| 评论列表 | GET | `/api/articles/<id>/comments` |
