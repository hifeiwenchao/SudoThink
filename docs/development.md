# 开发机制与接口

启动命令见 [README](../README.md)，生产配置见 [部署配置参考](./deployment-reference.md)。

## Celery 任务与周期计划

在 `backend/app/tasks` 下新增任务模块，并在该目录的 `__init__.py` 中导入。任务使用 Celery 的同步入口，例如已有的 `app.tasks.diagnostics.ping`；通过 `ping.delay()` 或 `celery_app.send_task("app.tasks.diagnostics.ping")` 投递。Sanic 请求处理中投递任务会进行同步 broker I/O，应使用 `await asyncio.to_thread(ping.delay)`，避免阻塞事件循环。

周期计划集中在 [backend/app/celery_app.py](../backend/app/celery_app.py) 的 `BEAT_SCHEDULE` 中，默认是空字典。新增计划时填写已注册的任务名和 `schedule`，例如 `crontab(hour=2, minute=0)` 表示按 `CELERY_TIMEZONE` 每天凌晨两点投递；修改后重建 worker 和 beat。文章阅读数使用下文的延迟任务，由访问触发，不依赖 beat 的周期扫描。

任务不复用 Sanic 的数据库和 Redis 生命周期。未来任务需要异步 ORM 或缓存时，应在任务进程中自行建立并关闭连接；不要直接把 `async def` 注册为 Celery 任务，也不要跨事件循环复用 ORM 连接。任务应按可能重复执行设计为幂等。

默认不保存任务结果，适合仅需后台执行的任务；`.delay()` 返回任务 ID，但不能直接读取执行结果。如需查询结果，可设置 Celery 支持的 `CELERY_RESULT_BACKEND`，并重建服务。仅接受 JSON 消息，不接受 pickle 等序列化格式。

## API 请求记录与文章阅读数

管理员进入“运维管理 → API 请求记录”，可按 URL、请求方法和 HTTP 状态码筛选，并分页查看请求时间、耗时、URL 及查询、路径、请求体参数。该功能独立于 CDN 配置，只有管理员可以查询。

后端将 `/api` 下的请求记录到 MySQL 的 `api_request_logs` 表，包含成功和失败响应。URL 使用站内路径与脱敏后的查询字符串，不保存请求头、Cookie 或响应体。密码、令牌、密钥等敏感字段会替换为脱敏标记；参数限制层级、数量和长度，过大的内容会截断或省略。文件内容和无法解析的请求体不保存。请求记录写入失败时会输出简要日志，不影响原接口响应。

成功访问公开文章详情 `GET /api/articles/<id>` 时，后端先使用 Redis 中的阅读数；缓存未命中时以数据库阅读数初始化；每次访问在同一原子操作中取数据库快照与缓存值的较大者再加一，并返回最新结果。多次并发访问不会覆盖已经增加的缓存值。列表、评论、后台编辑、失败响应和 HEAD 请求不增加阅读数；该口径统计访问次数，不按访客去重。列表和后台读取数据库值，因此可能比详情页延迟。

每篇文章在第一次访问时安排一个 120 秒后执行的 Celery 写回任务；等待和执行期间的后续访问只累加 Redis，重复触发直接丢弃，不重复安排任务，也不延长计时。任务执行时读取最新缓存值，再写入数据库。写入只允许阅读数增加，重复执行或旧任务晚到都不会使阅读数回退。任务结束后不会检查增量并补排任务；执行快照之后产生的计数继续保留在 Redis，待以后独立访问触发的任务写回。阅读统计不再扫描 API 请求日志。

首次部署由 `init_db.py` 建表；已有安装按 [README](../README.md#更新应用) 升级，并同时更新 backend、worker、beat。直接本地运行时，确保 Redis、RabbitMQ 和 worker 可用。可以手动投递某篇文章的写回任务，将示例 ID 替换为实际文章 ID：

```bash
docker compose exec backend celery -A app.celery_app:celery_app call app.tasks.article_views.persist_article_views --args='[123]'
docker compose logs --tail=30 worker
```

阅读计数缓存不自动过期。Redis 不可用时，详情接口使用数据库值并输出简要日志；这期间无法完成 Redis 阅读累加。投递任务失败时保留缓存计数，后续访问可重新安排写回。Redis 中尚未写回的数据依赖 Redis 的持久化，请按部署需求配置 AOF/RDB 和内存淘汰策略；清空计数缓存会丢失未写回的增量。API 请求记录目前不自动删除，会随访问量增长，其清理与阅读统计相互独立。

## 通用延迟任务去重

[backend/app/core/delayed_tasks.py](../backend/app/core/delayed_tasks.py) 提供 `schedule_task_once`，适用于“首次触发后延迟 N 秒执行，等待期间重复触发只执行一次”的场景。例如：

```python
from app.core.delayed_tasks import schedule_task_once

await schedule_task_once(
    task_name="app.tasks.article_views.persist_article_views",
    dedupe_key=str(article_id),
    delay_seconds=120,
    args=[article_id],
    execution_timeout=300,
)
```

`task_name` 是已注册的同步 Celery 任务名，`dedupe_key` 为业务标识，`delay_seconds` 为 1–86400 秒；`args`、`kwargs` 只接受可序列化的 JSON 参数，`execution_timeout` 为 30–86400 秒，默认 300 秒。

同一任务名和业务标识共享一个等待窗口，不同文章或不同任务相互独立。函数返回 `True` 表示安排了任务，`False` 表示已有窗口，本次重复触发被丢弃；窗口采用第一次触发的参数，后续触发不替换参数。需要累计状态时，应像阅读数一样在 Redis 中更新状态，让任务执行时读取最新数据。

等待和执行期间始终保留去重标记，重复触发直接返回 `False`，不在任务结束后补排。任务成功或耗尽重试后释放标记，只有此后新的独立触发才可创建下一窗口。Redis 中的执行标记阻止同一投递重复执行；异常时 Celery 会重试，因此业务任务仍应具备幂等性。调度使用 RabbitMQ，Redis 负责去重，要求二者均可用。投递失败会释放尚未执行的本次等待标记并抛出异常，调用方可以记录失败并在后续触发时重试。

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
| CDN 运维配置 | GET | `/api/admin/operations/cdn/config`（管理员） |
| CDN 缓存刷新 | POST | `/api/admin/operations/cdn/refresh`（管理员，`urls`、`object_type`） |
| CDN 资源预热 | POST | `/api/admin/operations/cdn/preload`（管理员，`urls`） |
| CDN 任务查询 | GET | `/api/admin/operations/cdn/tasks`（管理员，`task_id`、`page`、`size`） |
| API 请求记录 | GET | `/api/admin/operations/requests`（管理员，`url`、`method`、`status_code`、`page`、`size`） |
