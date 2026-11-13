# API 请求记录、Redis 阅读数与通用延迟任务计划

**目标：** 记录 API URL 和请求参数，在运维管理查询；文章阅读数使用 Redis 原子计数并延迟写回；将固定窗口去重封装供其他业务复用。

**设计：** Sanic 响应中间件写入 MySQL 请求日志并脱敏。成功读取文章详情后，Redis 计数加一，第一次触发安排 120 秒后的 Celery 任务，等待及执行期间重复触发均丢弃，不自动补排。详情返回缓存中的实时总数，数据库通过任务单调写回；日志查询与阅读统计独立。

**约束：** 不记录认证头、Cookie 或响应体；保留已有阅读数；只有公开详情 GET 增加阅读数；不增加 API CDN 缓存，不自动清理请求日志，不执行部署。

## 接口

- `ApiRequestLog` 保存 `id,method,url,path,query_params,path_params,body_params,status_code,duration_ms,created_at`，不包含阅读统计字段。URL 为脱敏后的相对路径与查询字符串。
- 管理员 `GET /api/admin/operations/requests`：`page=1,size=20`（最大 100）、`url` 子串、`method`、`status_code`。返回 `items,total,page,size`，时间 ISO 格式。
- `record_article_view(article: Article) -> int`：读取 Redis `article:views:<id>`，缓存未命中时从数据库值初始化，Lua 原子累计，并调用通用调度器；缓存计数无过期时间。
- 异步 `persist_article_views(article_id: int, redis_client) -> dict`：读取缓存总数，仅当数据库值更小时更新，不删除或回写缓存；已删除文章或缺失缓存不写入。
- Celery `app.tasks.article_views.persist_article_views(article_id)`：自行初始化并关闭 ORM 和 Redis，避免跨事件循环复用连接。
- `schedule_task_once(task_name, dedupe_key, delay_seconds, args=(), kwargs=None, *, redis_client=None, execution_timeout=300) -> bool`：以任务名和业务标识生成窗口键；第一次触发投递通用包装任务，后续触发返回 False，保留第一次参数。
- 包装任务 `app.tasks.delayed.execute_once` 在取得执行锁后执行业务任务；等待和执行期间保留业务窗口，重复触发直接丢弃。成功时记录完成标记并释放窗口，重复消息跳过，失败保留可重试状态。不补排任务；业务任务须幂等，执行锁租期覆盖 Celery 任务时限。
- 文章列表和后台读取数据库阅读数；详情优先缓存。Redis 故障时详情降级返回数据库值，不能保证该期间统计。不新增逐请求同步数据库计数。
- 单次写回采用执行时快照；快照之后的计数保留 Redis，不自动安排后续任务。任务完全结束后的独立访问可重新触发一次延迟写回。

## 实施与验证

- [x] 实现日志模型、中间件、管理员查询和独立运维页签；验证脱敏、载荷上限、异常响应、鉴权、筛选与分页。
- [x] 移除文章编辑中的全字段保存，避免覆盖并发更新的阅读数；回归验证文章内容、分类、标签和发布时间。
- [ ] 用 Redis 原子计数替换日志扫描统计；验证缓存未命中并发、HEAD 和草稿排除、实时返回、单调写回、任务期间重复触发丢弃。
- [ ] 实现通用固定窗口延迟任务；验证并发首次触发、首次参数保留、业务键隔离、投递失败释放、重复消息、执行失败重试及等待和执行期间均丢弃重复触发。
- [x] 精简请求日志中已不适用的阅读处理字段、筛选和展示；保留 CDN 功能。
- [ ] 更新 README 的两种运行方式和通用调度器使用说明，删除日志扫描及 beat 阅读统计说明。
- [ ] 验证完整后端测试、前端测试与生产构建、真实 Redis Lua、隔离 MySQL 单调写入和升级，以及真实 Celery 延迟执行和浏览器页面。

验证过程使用独立 Redis 容器和随机临时 MySQL 数据库，不改动运行中的应用数据。
