# SudoThink Blog

一个基于前后端分离架构的博客系统。

## 技术栈

### 后端
- **Python** 3.11+
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
│   └── conf.d/default.conf
├── docker-compose.yml
├── .env.example
└── README.md
```

## 部署与运行

项目支持两种运行方式：

1. **Docker 部署**：MySQL、Redis、NGINX 由外部容器提供，当前项目的 Compose 只负责构建和运行 backend、frontend。
2. **本地运行**：后端直接由 Python 启动，前端由 Vite 启动；MySQL 和 Redis 可以使用本机服务，也可以使用对外发布端口的容器服务。

### Docker 部署（外部基础设施容器）

Docker 部署的网络关系如下：

```text
浏览器
   │
   ▼
外部 NGINX 容器 :80/:443
   ├── /       ──> sudothink-frontend:80
   └── /api/   ──> sudothink-backend:8000
                              ├──> 外部 MySQL 容器 :3306
                              └──> 外部 Redis 容器 :6379
```

backend、frontend、NGINX、MySQL、Redis 必须加入同一个 Docker 网络。先创建共享网络，并将已经运行的外部容器接入：

```bash
docker network create sudothink-net

docker network connect sudothink-net <mysql-container>
docker network connect sudothink-net <redis-container>
docker network connect sudothink-net <nginx-container>
```

如果外部容器已经接入该网络，重复执行 `docker network connect` 会提示已连接，可以跳过。外部容器也可以在各自的 Compose 文件中声明同一个网络：

```yaml
networks:
  sudothink-net:
    external: true
    name: sudothink-net
```

复制并修改环境变量：

```bash
cp .env.example .env
```

Docker 部署时，`.env` 中的数据库和 Redis 地址必须使用它们在共享网络中的容器名或网络别名，不能使用 `localhost`：

```dotenv
APP_ENV=production
APP_DEBUG=false
APP_SECRET_KEY=change-to-a-random-secret
JWT_SECRET=change-to-a-random-jwt-secret

MYSQL_HOST=mysql-prod
MYSQL_PORT=3306
MYSQL_USER=blog
MYSQL_PASSWORD=your-password
MYSQL_DATABASE=sudothink

REDIS_HOST=redis-prod
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

CORS_ORIGINS=https://your-domain.example
VITE_API_BASE_URL=/api
```

其中 `mysql-prod` 和 `redis-prod` 替换成实际容器名。如果使用网络别名，也可以设置为 `mysql` 和 `redis`。

当前 [docker-compose.yml](./docker-compose.yml) 只启动 backend 和 frontend：

```bash
docker compose up -d --build
docker compose ps
```

由于 MySQL 和 Redis 不再由当前 Compose 管理，请先确认它们已经启动且可以通过共享网络访问。外部 NGINX 应该使用容器名访问应用服务。可以参考 [nginx/conf.d/default.conf](./nginx/conf.d/default.conf)，并按实际容器名调整 upstream；例如：

```nginx
upstream sudothink_backend {
    server sudothink-backend:8000;
}

upstream sudothink_frontend {
    server sudothink-frontend:80;
}
```

然后将 `/api/` 代理到 `sudothink_backend`，将其他路径代理到 `sudothink_frontend`。NGINX 应在 backend 和 frontend 启动后加载或重新加载配置：

```bash
docker exec <nginx-container> nginx -s reload
```

部署后检查：

```bash
curl http://your-domain.example/api/health
```

通常只需要对外发布 NGINX 的 `80/443` 端口，MySQL、Redis 和 backend 的 `3306/6379/8000` 可以只在 Docker 网络内部访问。

### 本地运行（不使用 Docker）

本地运行需要 Python 3.11+、Node.js、pnpm（或 npm）、MySQL 8 和 Redis 7。MySQL 和 Redis 可以是本机服务，也可以是发布了端口的外部容器。

先在项目根目录创建环境变量文件：

```bash
cp .env.example .env
```

如果后端直接运行在宿主机上，`.env` 中应使用宿主机可访问的地址，例如：

```dotenv
APP_ENV=development
APP_DEBUG=true
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
CORS_ORIGINS=http://localhost:5173
VITE_API_BASE_URL=/api
```

如果 MySQL 或 Redis 在其他服务器上运行，则把 `MYSQL_HOST` 或 `REDIS_HOST` 改为对应服务器地址，并确保端口可访问。Docker 内部容器名（例如 `mysql-prod`）不能直接用于宿主机上的本地 Python 进程。

初始化并启动后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows PowerShell 使用 .venv\\Scripts\\Activate.ps1
pip install -r requirements.txt

# 首次运行时初始化 Aerich
aerich init -t app.core.config.TORTOISE_ORM
aerich init-db

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

## 默认 API 路径

| 模块 | 方法 | 路径 |
| --- | --- | --- |
| 健康检查 | GET | `/api/health` |
| 注册 | POST | `/api/auth/register` |
| 登录 | POST | `/api/auth/login` |
| 文章列表 | GET | `/api/articles` |
| 文章详情 | GET | `/api/articles/<id>` |
| 创建文章 | POST | `/api/articles` |
| 分类列表 | GET | `/api/categories` |
| 标签列表 | GET | `/api/tags` |
| 评论列表 | GET | `/api/articles/<id>/comments` |
