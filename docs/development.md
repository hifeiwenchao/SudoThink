# 开发机制与接口

启动命令见 [README](../README.md)，生产配置见 [部署配置参考](./deployment-reference.md)。

## Celery 任务与周期计划

在 `backend/app/tasks` 下新增任务模块，并在该目录的 `__init__.py` 中导入。任务使用 Celery 的同步入口，例如已有的 `app.tasks.diagnostics.ping`；通过 `ping.delay()` 或 `celery_app.send_task("app.tasks.diagnostics.ping")` 投递。Sanic 请求处理中投递任务会进行同步 broker I/O，应使用 `await asyncio.to_thread(ping.delay)`，避免阻塞事件循环。

周期计划集中在 [backend/app/celery_app.py](../backend/app/celery_app.py) 的 `BEAT_SCHEDULE` 中，内置每 60 秒检查待办提醒、每小时清理过期 API 请求日志的任务。新增计划时填写已注册的任务名和 `schedule`，例如 `crontab(hour=2, minute=0)` 表示按 `CELERY_TIMEZONE` 每天凌晨两点投递；修改后重建 worker 和 beat。文章阅读数使用下文的延迟任务，由访问触发，不依赖 beat 的周期扫描。

任务通过 `run_with_worker_resources` 复用 worker 进程生命周期管理的事件循环、ORM 和 Redis，不复用 Sanic 的资源。不要在每次任务中初始化与关闭连接，不要直接把 `async def` 注册为 Celery 任务，也不要跨事件循环复用 ORM 连接。任务发现阶段保持轻量导入，业务服务与模型在执行阶段导入。任务应按可能重复执行设计为幂等。

默认不保存任务结果，适合仅需后台执行的任务；`.delay()` 返回任务 ID，但不能直接读取执行结果。如需查询结果，可设置 Celery 支持的 `CELERY_RESULT_BACKEND`，并重建服务。仅接受 JSON 消息，不接受 pickle 等序列化格式。

## 待办提醒

管理员私有待办保存在 `todos` 表，接口为 `/api/admin/todos` 的列表、创建、修改、删除及 `/<id>/completion`、`/<id>/retry` 操作。新提醒使用 `reminder_repeat=cron`、`reminder_cron` 五段表达式和 `reminder_timezone` IANA 时区；无需旧的截止时间。`POST /api/admin/todos/preview` 返回未来 5 次时间，与 worker 共同使用 `todo_cron.py` 和 croniter。解析限定标准字段、128 字符、8 年搜索窗口，日与星期采用 OR 语义；前端中文说明只辅助展示，发送时间以服务端预览为准。

`reminder_next_run_at` 保存本次计划时间，`reminder_next_attempt_at` 独立控制发送重试。发送成功后计算当前时间之后的下个匹配时刻并清零本轮尝试次数；遗漏的多个周期只补发一次。crontab 夏令时缺失时刻使用下一有效时刻，折返时同一当地分钟只提醒一次。原有 `once/daily/monthly/yearly` 和 `due_at` 仅用于兼容旧记录，保留月末与闰年规则；修改内容不会隐式转换为 crontab。升级脚本仅增加表达式字段，保留原有计划和已发送状态。

`POST /api/admin/todos/<id>/skip-period/preview` 接收 `period=day|week|month|year`，返回待办时区、周期结束边界、提醒版本和跳过后的下次提醒时间，不修改记录。`POST /api/admin/todos/<id>/skip-period` 接收周期，并可携带 `expected_period_ends_at`、`expected_reminder_revision`、`expected_next_run_at`；管理界面提交完整预览快照，服务端在事务中校验，跨周期或计划变化时拒绝旧预览并要求重新确认。操作锁定自己的待办，将下一次计划和重试时间推迟到下一周期边界（含）之后的首个匹配时间，并保留更晚的现有计划，同时递增提醒版本、清空旧领取令牌和本轮错误/尝试次数；不增加额外定时任务或数据库字段。日历边界由执行时区和服务端当前时间计算，周从周一开始；重复请求不会逐次累加跳过周期。

`app.tasks.todos.send_due_reminders` 每分钟处理最多 20 条到期提醒。数据库条件更新原子领取，租约为 5 分钟；版本及令牌防止重复领取、旧发送结果覆盖后续编辑。发送前重新检查事项、提醒开关和收件邮箱。没有 SMTP 配置或未填写收件邮箱时不消耗尝试次数。

邮件在后台线程通过 SSL/STARTTLS 发送，失败分别等待 1 分钟和 5 分钟，最多尝试 3 次；用完后在列表中手动重试。领取后进程中断，由后续检查回收过期租约。SMTP 接受邮件与数据库记录发送结果无法组成原子事务，两者之间进程异常中断时可能重复提醒；正常重复扫描不会重复发送。修改、完成或删除可取消尚未开始发送的旧提醒，已提交给邮件服务器的邮件无法撤回。

`GET /api/admin/todos/<id>/history` 分页读取所属管理员的私有提醒历史。`todo_reminder_history` 保存本次升级后的 sent/failed/skipped 事件、计划时间、后续时间及脱敏错误，不保存邮箱、正文或领取令牌。结果状态和历史在同一数据库事务中写入，旧版本投递不产生新历史；删除待办时级联清理。

## API 请求记录与文章阅读数

管理员进入“运维管理 → API 请求记录”，可按 URL、请求方法、HTTP 状态码和请求时间范围筛选，并分页查看请求时间、耗时、URL 及查询、路径、请求体参数。该功能独立于 CDN 配置，只有管理员可以查询。

后端将 `/api` 下的请求记录到 MySQL 的 `api_request_logs` 表，包含成功和失败响应。URL 使用站内路径与脱敏后的查询字符串，不保存请求头、Cookie 或响应体。密码、令牌、密钥等敏感字段会替换为脱敏标记；待办接口的请求体及查询参数整体省略，避免私人事项进入管理员共享日志。参数限制层级、数量和长度，过大的内容会截断或省略。文件内容和无法解析的请求体不保存。请求记录写入失败时会输出简要日志，不影响原接口响应。

成功访问公开文章详情 `GET /api/articles/<id>` 时，后端先使用 Redis 中的阅读数；缓存未命中时以数据库阅读数初始化；每次访问在同一原子操作中取数据库快照与缓存值的较大者再加一，并返回最新结果。多次并发访问不会覆盖已经增加的缓存值。列表、评论、后台编辑、失败响应和 HEAD 请求不增加阅读数；该口径统计访问次数，不按访客去重。列表和后台读取数据库值，因此可能比详情页延迟。

每篇文章在第一次访问时安排一个 120 秒后执行的 Celery 写回任务；等待和执行期间的后续访问只累加 Redis，重复触发直接丢弃，不重复安排任务，也不延长计时。任务执行时读取最新缓存值，再写入数据库。写入只允许阅读数增加，重复执行或旧任务晚到都不会使阅读数回退。任务结束后不会检查增量并补排任务；执行快照之后产生的计数继续保留在 Redis，待以后独立访问触发的任务写回。阅读统计不再扫描 API 请求日志。

首次部署由 `init_db.py` 建表；已有安装按 [README](../README.md#更新应用) 升级，并同时更新 backend、worker、beat。直接本地运行时，确保 Redis、RabbitMQ 和 worker 可用。可以手动投递某篇文章的写回任务，将示例 ID 替换为实际文章 ID：

```bash
docker compose exec backend celery -A app.celery_app:celery_app call app.tasks.article_views.persist_article_views --args='[123]'
docker compose logs --tail=30 worker
```

阅读计数缓存不自动过期。Redis 不可用时，详情接口使用数据库值并输出简要日志；这期间无法完成 Redis 阅读累加。投递任务失败时保留缓存计数，后续访问可重新安排写回。Redis 中尚未写回的数据依赖 Redis 的持久化，请按部署需求配置 AOF/RDB 和内存淘汰策略；清空计数缓存会丢失未写回的增量。API 请求日志固定保留最近 7 天，无环境变量配置。Celery 每小时分批删除严格早于当前时间减 7 天的记录，每批最多 1000 条，每次最多 100 批，剩余积压由后续运行继续清理。因此两次清理之间可能短暂存在超过 7 天的记录；清理与阅读统计相互独立。查询参数 `created_from` 和 `created_to` 接受包含时区的 ISO 时间、包括边界，查询前转换到数据库时区；非法或反向时间范围返回校验错误。

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
| 公开音乐列表 | GET | `/api/music`（未启用或空列表时返回隐藏状态） |
| 读取 / 保存音乐设置 | GET / PUT | `/api/admin/music`（管理员，`enabled`、有序 `tracks`，每项含 `title`、`artist`、`url`） |
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

## 文章回收站与公开索引

文章 `deleted_at` 为空表示活动记录。两个删除入口均改为软删除，`POST /api/admin/articles/<id>/restore` 恢复；后台 `status=all|published|draft|trash` 筛选，默认排除回收站。公开列表、详情、评论入口、首页统计及 sitemap 均排除回收站，升级幂等添加删除时间与索引。列表查询不读取或返回 `content`，详情保留完整正文。

`/api/seo/sitemap.xml` 使用配置的 `PUBLIC_SITE_URL` 生成公开文章索引，超过 10000 篇时返回分页 sitemap index；`/api/seo/robots.txt` 提供公开站规则。NGINX 将根目录的 sitemap/robots 代理到相应接口，管理域返回禁止抓取规则。页面 meta 与 canonical 由 Vue 更新，非执行 JavaScript 的抓取器可能无法获得文章 meta；SPA 未知路径仍可能返回 HTTP 200，页面本身显示 404 并设置 noindex。严格爬虫状态码及非 JS 分享卡片需要后续预渲染或服务端渲染。
