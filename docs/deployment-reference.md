# 部署配置参考

基础部署与本地启动见 [README](../README.md)。本页补充环境变量、HTTPS、媒体上传、静态资源发布和访客 IP 配置。所有域名、容器名、网段、凭据与路径均为占位示例。

## 环境变量与数据库账号

根目录 [.env.example](../.env.example) 默认用于生产部署；已有 `.env` 时合并缺项并保留实际凭据。应用与 JWT 密钥、MySQL/Redis/RabbitMQ 凭据及管理员密码均需填写真实值。

- `MYSQL_USER` 对应已存在且有目标库建表、读写权限的账号；建库可另配 `MYSQL_ADMIN_USER`、`MYSQL_ADMIN_PASSWORD`。初始化不会创建或授权 MySQL 账号。
- 已有管理员重复初始化会保留原密码；修改 `ADMIN_PASSWORD` 不会重置已有密码。
- `REDIS_PASSWORD` 与外部 Redis 一致，无密码时留空。
- `CORS_ORIGINS` 填实际访问 Origin，包含协议、主机名与端口；应用 CORS 和 OSS CORS 独立配置。
- `FRONTEND_HTTP_PORT` 默认 `8100`；更换后重建 frontend，并开放对应防火墙、安全组端口。

## 构建镜像源

后端默认使用阿里云 Debian APT 与 Python 包镜像。可在根目录 `.env` 设置 `DEBIAN_MIRROR=https://deb.debian.org` 和 `PYPI_INDEX_URL=https://pypi.org/simple` 改用官方源；APT 变量填根 URL，不带 `/debian` 后缀。修改后重新构建 backend。

Docker 镜像加速、APT 软件源和 pip 包源相互独立。构建较慢时运行 `docker compose --progress plain build backend` 查看耗时步骤，并依据日志检查相应网络。

## HTTPS 与外部 NGINX

[nginx/conf.d/sudothink.conf](../nginx/conf.d/sudothink.conf) 默认通过 HTTPS 提供公开站点和管理站点，支持 TLS 1.2、TLS 1.3 和 HTTP/2。这两个站点的 HTTP 请求会返回 `308`，保留主机名、路径和查询参数并跳转到 HTTPS。HTTPS 站点使用稳定容器名 `sudothink-backend:8000`、`sudothink-frontend:8100` 作为 upstream；两个站点的 `/api/` 转发给后端，其余页面请求转发给前端。

裸域使用独立的跳转配置，HTTP 和 HTTPS 请求均返回 `308`，跳转到公开站点的 HTTPS 地址；例如 `https://example.com/articles/1?from=apex` 跳转到 `https://www.example.com/articles/1?from=apex`，保留路径和查询参数。若外部 NGINX 的其他配置已在相同监听地址和端口下声明该裸域，应合并规则或移除重复的 `server_name` 声明，避免跳转规则与已有站点冲突。

先准备一张同时覆盖裸域、公开站点和管理站点域名的有效证书，例如包含 `example.com`、`www.example.com` 和 `admin.example.com` 的 SAN 证书，或同时包含 `example.com` 和 `*.example.com` 的证书。`*.example.com` 本身不覆盖裸域 `example.com`，HTTPS 裸域跳转也需要有效证书才能完成 TLS 握手。站点和裸域跳转共用以下容器内路径：

| 文件 | 容器内路径 |
| --- | --- |
| 完整证书链 | `/etc/ssl/depends/example.com/fullchain.pem` |
| 证书私钥 | `/etc/ssl/depends/example.com/privkey.pem` |

`example.com` 是证书目录示例，部署时按实际域名目录替换，并同步修改 [nginx/conf.d/sudothink.conf](../nginx/conf.d/sudothink.conf) 中的 `ssl_certificate`、`ssl_certificate_key` 路径。

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

## RabbitMQ 与 Celery 配置

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

同一套周期计划只运行一个 beat；Compose 的 `celerybeat-state` 命名卷保留其状态。当前 `BEAT_SCHEDULE` 为空，阅读数写回由访问触发的延迟任务完成，不依赖 beat。Windows 本地 worker 可添加 `--pool=solo`。

更新任务代码、依赖或 RabbitMQ/Celery 配置后，重建 backend、worker、beat；worker 日志出现 `ready` 才表示已连接 broker 并可消费任务。诊断命令：

```bash
docker compose exec backend celery -A app.celery_app:celery_app call app.tasks.diagnostics.ping
docker compose logs --tail=20 worker
```

## ICP 备案信息

在项目根目录 `.env` 中设置 `VITE_ICP_NUMBER` 为实际 ICP 备案号，公开站点和管理站点的页脚会显示该号码，并链接到工信部备案查询网站 <https://beian.miit.gov.cn/>。默认留空时隐藏备案信息，个人备案号无需写入代码或提交到仓库。

该配置在前端构建时生效。Docker 部署修改后执行 `docker compose build frontend`，再执行 `docker compose up -d --no-deps frontend`；本地开发修改后重启 Vite，直接部署静态文件时重新执行 `npm run build`。如果启用了静态资源 CDN，请按下文的 CDN 发布流程上传资源并手动刷新 CDN 后再切换前端。

## 阿里云 OSS 图片、视频上传

管理员在正文工具栏选择本地图片或视频，或在封面处上传图片。浏览器先向后台申请 5 分钟有效的上传凭证，再直接上传到阿里云 OSS；进度和取消在上传界面显示，成功后插入 CDN 地址。上传期间请等待完成或取消后再保存文章；离开编辑页会提醒。共享编辑器的“关于我”也支持媒体上传。

支持 JPG/JPEG、PNG、GIF、WebP、AVIF 图片，以及 MP4、WebM 视频；默认单张图片最大 10 MB、单个视频最大 200 MB。“音乐设置”另支持 MP3、M4A、WAV、OGG 音频，默认每首最大 50 MiB。视频和音频以原文件存储，不执行转码；编码需可被目标浏览器播放。正文可以只有图片或视频。原有外链继续保留，若需迁移到 OSS，请重新上传并替换链接。

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
OSS_AUDIO_MAX_BYTES=52428800
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

CDN 对公开 JS、字体等跨域资源需要返回 `Access-Control-Allow-Origin: *`，并正确处理 `GET`、`HEAD`、`OPTIONS`；这是公开资源的读取规则，OSS 上传规则仍限定管理站 Origin。开启视频、音频 Range 回源，保留正确的 `Content-Type`，以支持播放和拖动进度。音频 MIME 使用 `audio/mpeg`、`audio/mp4`、`audio/wav`、`audio/ogg`。`media/*` 可设置合理缓存时间，上传对象使用随机文件名；删除文章、移除音乐曲目或取消上传不会自动删除 OSS 对象。

`OSS_MEDIA_CACHE_SECONDS` 控制新上传图片、视频、音频的缓存时长，单位为秒，须为非负整数，默认 `31536000`（365 天）。正数会在上传时写入 OSS 对象元数据 `Cache-Control: public,max-age=<秒数>,immutable`，设为 `0` 则写入 `Cache-Control: no-store`。正文、封面、“关于我”、打赏收款码和音乐的媒体上传共用该配置；前端 JS/CSS 等静态资源使用下文的独立缓存策略。CDN 需遵循源站缓存头；如果路径规则强制指定缓存时长，应同步调整该规则。

修改该参数只影响后续上传，已有对象保留原元数据。已有资源需修改 OSS 的 `Cache-Control` 元数据并刷新 CDN，或重新上传生成新 URL；浏览器已保存长缓存的资源优先通过新 URL 更新。

Docker 修改 `.env` 后重建后端容器，直接运行则重启后端。直传文件不经过应用 NGINX/Sanic，因此不需要为视频提高应用请求体上限。

## 前端静态资源通过 CDN 发布

图片和视频上传后自动使用 `CDN_BASE_URL`。前端 JS、CSS、字体和构建中的图片在生产构建时也使用以下两项配置，自动生成固定静态目录：

```dotenv
CDN_BASE_URL=https://cdn.example.com
OSS_STATIC_PREFIX=static
```

生产构建在 `CDN_BASE_URL` 非空时，自动以 `CDN_BASE_URL/OSS_STATIC_PREFIX/` 为资源地址，例如 `https://cdn.example.com/static/`；留空 `CDN_BASE_URL` 则使用站点本身。开发模式始终从本地 Vite 加载。每次发布复用固定目录，构建资源使用稳定文件名，不附加内容哈希，上传时覆盖同名文件。页面 HTML 仍由站点提供，API 保持 `/api` 同源。

Vite 和发布脚本使用根目录的同一份 `.env`。Docker Compose 将公开的 `CDN_BASE_URL` 和 `OSS_STATIC_PREFIX` 作为 frontend 构建参数传入；访问密钥仍仅由后端和发布脚本使用，不会作为前端构建参数或客户端环境变量传入。修改这两项中的任一项后，需重新构建前端。

项目提供 [backend/scripts/publish_static_assets.py](../backend/scripts/publish_static_assets.py)。脚本直接从 `CDN_BASE_URL` 和 `OSS_STATIC_PREFIX` 推导上传目录并校验构建地址，无需另设资源 URL。验证全部文件后，将静态文件上传到固定目录，设置正确的 MIME 和 `Cache-Control: public,max-age=0,s-maxage=31536000,must-revalidate`。浏览器使用前会校验缓存，CDN 可缓存一年；CDN 需遵循源站缓存头，或为 `/static/` 配置一年缓存并让浏览器缓存遵循源站（修改了 `OSS_STATIC_PREFIX` 时使用对应路径）。脚本不上传 `index.html`，不清理云端历史资源，也不自动刷新 CDN。

直接运行时，激活后端虚拟环境后，在项目根目录执行：

```bash
cd frontend
npm ci
npm run build
cd ..
python backend/scripts/publish_static_assets.py frontend/dist --dry-run
python backend/scripts/publish_static_assets.py frontend/dist
```

上传完成后，在后台“运维管理”或阿里云 CDN 控制台执行目录刷新，例如刷新 `https://cdn.example.com/static/`，等待刷新完成并确认新构建 `index.html` 引用的 CDN 脚本和样式已更新且可通过 HTTPS 读取，再把同一份 `frontend/dist` 部署到站点。固定 URL 会覆盖线上同名资源，上传及刷新期间已打开的页面可能受影响，建议选择低流量时段发布。

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

`--interactive=false` 避免临时容器读取标准输入，支持通过 `ssh ... bash -s` 执行整段脚本。发布脚本失败时先修正配置或网络；上传成功后手动刷新 CDN 静态目录，等待刷新完成并检查新资源 URL，再执行 `docker compose up -d --no-build backend frontend worker beat`，并按本页 HTTPS 章节检查和重载外部 NGINX。CDN 上的 JS/CSS 必须已更新且可访问后才切换前端，否则页面可能加载到旧资源或因缺少资源而无法打开。

已有的 `release-*` 目录不会自动删除。迁移并确认站点使用固定目录后，可自行清理不再引用的旧目录。

配置参考：[OSS V4 表单签名](https://help.aliyun.com/zh/oss/developer-reference/signature-version-4-recommend)、[OSS CORS](https://help.aliyun.com/zh/oss/user-guide/configure-cross-origin-resource-sharing)、[CDN 加速 OSS 与私有回源](https://help.aliyun.com/zh/oss/user-guide/use-cdn-to-accelerate-access-to-oss)。

## 后台 CDN 运维

管理员可在“管理后台 → 运维管理 → CDN 运维”提交文件 URL 刷新、目录刷新、正则刷新及 URL 预热任务，并手动查询近 3 天的任务状态、进度和失败说明。URL 每行一条，允许操作当前阿里云账号有权限管理的 CDN 加速域名；空行和重复地址会在页面合并。操作使用服务端的 `ACCESS_KEY_ID`、`ACCESS_KEY_SECRET`，配置了 `OSS_SECURITY_TOKEN` 时同时使用该临时凭据，浏览器不会获得密钥。凭据需要 `cdn:RefreshObjectCaches`、`cdn:PushObjectCache` 和 `cdn:DescribeRefreshTasks` 权限，只有 OSS 上传权限的账号需要另外授予这些 CDN 操作权限。

每次最多提交 1000 条文件刷新、100 条目录刷新、1 条正则刷新或 100 条预热地址，最多涉及 10 个域名，每条地址不超过 1024 字符；实际每日额度以阿里云账号为准。目录必须以 `/` 结尾且不能带查询参数；预热使用精确文件 URL，不支持以 `/` 结尾的目录。正则刷新遵循阿里云支持的 `[0-9]`、`[a-z]`、`[^/]*`、`.*` 四种模式，例如 `https://cdn.example.com/images/.*`。目录和正则刷新使用阿里云默认的标记过期行为，预热使用域名配置的加速区域。

提交成功表示异步任务已受理，不代表缓存已刷新或预热完成；使用任务编号查询状态。遇到超时或网络中断时，先查询最近任务，确认是否已受理后再决定是否重试，避免重复消耗配额。后台仅调用 CDN 接口，不会上传源站资源或删除 OSS 文件。无需新增数据表或数据库升级。

接口与限制参考：[刷新与预热资源](https://help.aliyun.com/zh/cdn/user-guide/refresh-and-prefetch-resources)、[RefreshObjectCaches](https://help.aliyun.com/zh/cdn/developer-reference/api-cdn-2018-05-10-refreshobjectcaches)、[PushObjectCache](https://help.aliyun.com/zh/cdn/developer-reference/api-cdn-2018-05-10-pushobjectcache)、[DescribeRefreshTasks](https://help.aliyun.com/zh/cdn/developer-reference/api-cdn-2018-05-10-describerefreshtasks)。

## QQWry 与可信代理

后端使用传统 QQWry IPv4 格式的 `qqwry.dat` 本地查询归属地，无需在线定位接口或 API Key。公开评论的国内归属地展示城市简称，例如“江苏省南京市”显示为“南京”、“浙江省杭州市”显示为“杭州”，直辖市如“北京市”显示为“北京”；自治州、地区保留名称，境外显示国家，不展示区县、运营商或详细地址。管理后台按已记录的 IP 查询离线库中的完整地理位置，包括库中可用的省、市、区县等信息；长地址可悬停查看，已有评论同样适用，无需改写数据。离线库不可用时，后台回退到已保存的归属地。地址精度取决于离线库，仅能定位到省市时显示对应层级；IPv6、内网地址、缺失或无法读取的数据库显示“未知”，不阻止评论提交。

仓库提供 [backend/data/qqwry.dat](../backend/data/qqwry.dat)，拉取代码后即可使用。更新时可从[纯真官网](https://www.cz88.net/)或已获授权的数据渠道获取兼容文件，并遵守数据提供方的使用条款。项目不自动下载；`.czdb` 与传统 `.dat` 格式不同，不能直接改名使用。

Docker 部署时，将文件放到 `backend/data/qqwry.dat`，Compose 会将 `backend/data` 只读挂载到后端的 `/app/data`。在 `.env` 中配置：

```dotenv
QQWRY_DB_PATH=data/qqwry.dat
# 填写实际的代理容器 IP 或专用代理网络 CIDR，多个以逗号分隔。
TRUSTED_PROXY_CIDRS=172.30.0.0/24
```

上面的网段仅为示例。可以用 `docker network inspect 网络名 --format '{{range .IPAM.Config}}{{.Subnet}}{{end}}'` 查看实际代理网络网段；只填写受信任代理所在的网络或固定 IP，不要填写 `0.0.0.0/0` 或 `::/0`。通过本项目的独立外部 NGINX 和前端容器入口访问时，后端必须信任实际转发请求的 NGINX 容器地址，才能记录访客 IP。

直接本地运行也可把文件放到 `backend/data/qqwry.dat`，使用相同的 `QQWRY_DB_PATH=data/qqwry.dat`；相对路径始终以 `backend` 为基准，也可配置绝对路径。没有反向代理时，`TRUSTED_PROXY_CIDRS` 留空，后端直接记录连接来源 IP；如果使用本机 NGINX 或 Vite 代理，需要按实际代理来源配置受信任地址，并确保代理覆盖 `X-Forwarded-For`。

项目的两份 NGINX 配置会用连接来源覆盖 `X-Forwarded-For`。后端仅接受来自受信任代理的转发信息，忽略其他来源提供的 IP 请求头。如果另有 CDN 或负载均衡，需要先在入口 NGINX 中依据提供方的官方网段配置真实 IP，再传递给后端。

修改 `.env` 后重建后端容器；更新离线库后，后续评论会使用更新的数据，已保存的评论归属地保持原记录。首次部署由初始化脚本建表；已有安装先按 [README](../README.md) 执行数据库升级，再启动新版后端。

## 已有数据库升级说明

首次部署使用 `init_db.py`；旧安装在启动新版后端前使用 `upgrade_site_content.py`。升级会补齐分类权重、站点设置、打赏与音乐设置、API 请求记录与访客评论字段，保留已有文章、阅读数、分类、管理员、评论和站点设置；已经被旧版删除的驳回评论无法恢复。脚本可重复运行，账号需有 `CREATE`、`ALTER` 权限。完整执行顺序见 [README 的更新流程](../README.md#更新应用)。
