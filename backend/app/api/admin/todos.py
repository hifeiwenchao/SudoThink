"""管理员私有待办管理；提醒投递由独立的 Celery 任务处理。"""
from datetime import datetime, timezone

from pydantic import ValidationError as PydanticValidationError
from sanic import Blueprint, Request
from sanic.exceptions import BadRequest
from tortoise.expressions import Q
from tortoise.transactions import in_transaction

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationError
from app.core.mail import smtp_ready
from app.core.response import success
from app.core.todo_cron import cron_occurrences, next_cron_at
from app.core.todo_skip_period import skip_period_schedule
from app.middlewares.auth import login_required
from app.models.todo import Todo
from app.schemas.todo import TodoCompletionIn, TodoCronPreviewIn, TodoIn, TodoSkipPeriodIn


bp = Blueprint("admin_todos", url_prefix="/todos")


def _ensure_admin(request):
    if not request.ctx.user.is_admin:
        raise ForbiddenError("admin only")


def _payload(request, schema):
    content_type = request.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise ValidationError("request body must be JSON")
    try:
        body = request.json
    except BadRequest:
        raise ValidationError("invalid JSON request body") from None
    if not isinstance(body, dict):
        raise ValidationError("request body must be an object")
    try:
        return schema.model_validate(body)
    except PydanticValidationError as exc:
        raise ValidationError("; ".join(item["msg"] for item in exc.errors())) from None


def _argument(arguments, name, default):
    value = arguments.get(name, default)
    if hasattr(arguments, "getlist") and name in arguments and len(arguments.getlist(name)) != 1:
        raise ValidationError(f"{name} 不允许重复")
    if not isinstance(value, str):
        raise ValidationError(f"{name} 必须为字符串")
    return value


def _integer(arguments, name, default, maximum):
    value = _argument(arguments, name, default)
    if (not value.isascii() or not value.isdecimal() or len(value) > 10
            or not 1 <= int(value) <= maximum):
        raise ValidationError(f"{name} 必须为 1 至 {maximum} 的整数")
    return int(value)


def todo_dict(todo):
    return {
        "id": todo.id, "title": todo.title, "content": todo.content,
        "due_at": todo.due_at.isoformat() if todo.due_at else None,
        "is_completed": todo.is_completed, "reminder_enabled": todo.reminder_enabled,
        "reminder_email": todo.reminder_email,
        "reminder_repeat": todo.reminder_repeat,
        "reminder_cron": todo.reminder_cron,
        "reminder_timezone": todo.reminder_timezone,
        "reminder_next_run_at": todo.reminder_next_run_at.isoformat() if todo.reminder_next_run_at else None,
        "reminder_status": todo.reminder_status,
        "reminder_sent_at": todo.reminder_sent_at.isoformat() if todo.reminder_sent_at else None,
        "reminder_attempts": todo.reminder_attempts, "reminder_error": todo.reminder_error,
        "created_at": todo.created_at.isoformat(), "updated_at": todo.updated_at.isoformat(),
    }


def _invalidate_claim(todo):
    todo.reminder_revision += 1
    todo.reminder_claim_token = ""
    todo.reminder_claim_until = None


def _reset_reminder(todo, *, reset_schedule=False):
    todo.reminder_attempts = 0
    todo.reminder_error = ""
    if reset_schedule or todo.reminder_repeat == "once":
        todo.reminder_sent_at = None
    if todo.reminder_enabled and not todo.is_completed:
        if reset_schedule or todo.reminder_next_run_at is None:
            if todo.reminder_repeat == "cron":
                try:
                    todo.reminder_next_run_at = next_cron_at(
                        todo.reminder_cron, todo.reminder_timezone, after=datetime.now(timezone.utc),
                    )
                except ValueError as exc:
                    raise ValidationError(str(exc)) from None
            else:
                todo.reminder_next_run_at = todo.due_at
        todo.reminder_status = "pending"
        todo.reminder_next_attempt_at = todo.reminder_next_run_at
    else:
        todo.reminder_status = "disabled"
        todo.reminder_next_run_at = None
        todo.reminder_next_attempt_at = None


async def _locked_todo(user_id, todo_id, connection):
    todo = await Todo.filter(id=todo_id, owner_id=user_id).using_db(connection).select_for_update().first()
    if todo is None:
        raise NotFoundError("待办事项不存在")
    return todo


def _skip_period_schedule(todo, period):
    try:
        return skip_period_schedule(todo, period, now=datetime.now(timezone.utc))
    except (ValueError, OverflowError) as exc:
        raise ValidationError(str(exc)) from None


@bp.get("")
@login_required
async def list_todos(request: Request):
    _ensure_admin(request)
    arguments = request.get_args(keep_blank_values=True)
    page = _integer(arguments, "page", "1", 2147483647)
    size = _integer(arguments, "size", "20", 100)
    status = _argument(arguments, "status", "all")
    if status not in {"all", "pending", "completed", "overdue"}:
        raise ValidationError("待办状态必须为 all、pending、completed 或 overdue")
    query = _argument(arguments, "q", "").strip()
    if len(query) > 200:
        raise ValidationError("搜索内容最多 200 个字符")
    qs = Todo.filter(owner_id=request.ctx.user.id)
    if status == "pending":
        qs = qs.filter(is_completed=False)
    elif status == "completed":
        qs = qs.filter(is_completed=True)
    elif status == "overdue":
        now = datetime.now(timezone.utc)
        qs = qs.filter(
            Q(reminder_repeat="once", due_at__lt=now)
            | (~Q(reminder_repeat="once") & Q(reminder_next_run_at__lt=now)),
            is_completed=False,
        )
    if query:
        qs = qs.filter(Q(title__icontains=query) | Q(content__icontains=query))
    total = await qs.count()
    todos = await qs.order_by("is_completed", "-created_at", "-id").offset((page - 1) * size).limit(size)
    return success({
        "items": [todo_dict(todo) for todo in todos], "total": total, "page": page, "size": size,
        "email_configured": smtp_ready(),
    })


@bp.post("")
@login_required
async def create_todo(request: Request):
    _ensure_admin(request)
    payload = _payload(request, TodoIn)
    todo = Todo(owner_id=request.ctx.user.id, **payload.model_dump())
    _reset_reminder(todo)
    await todo.save()
    return success(todo_dict(todo), message="created")


@bp.post("/preview")
@login_required
async def preview_todo_cron(request: Request):
    _ensure_admin(request)
    payload = _payload(request, TodoCronPreviewIn)
    try:
        times = cron_occurrences(
            payload.reminder_cron, payload.reminder_timezone, after=datetime.now(timezone.utc), count=5,
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from None
    return success({
        "expression": payload.reminder_cron, "timezone": payload.reminder_timezone,
        "times": [value.isoformat() for value in times],
    })


@bp.post("/<todo_id:int>/skip-period/preview")
@login_required
async def preview_todo_skip_period(request: Request, todo_id: int):
    _ensure_admin(request)
    payload = _payload(request, TodoSkipPeriodIn)
    todo = await Todo.get_or_none(id=todo_id, owner_id=request.ctx.user.id)
    if todo is None:
        raise NotFoundError("待办事项不存在")
    boundary, next_run = _skip_period_schedule(todo, payload.period)
    return success({
        "period": payload.period, "timezone": todo.reminder_timezone,
        "period_ends_at": boundary.isoformat(), "next_run_at": next_run.isoformat(),
        "reminder_revision": todo.reminder_revision,
    })


@bp.post("/<todo_id:int>/skip-period")
@login_required
async def skip_todo_period(request: Request, todo_id: int):
    _ensure_admin(request)
    payload = _payload(request, TodoSkipPeriodIn)
    async with in_transaction() as connection:
        todo = await _locked_todo(request.ctx.user.id, todo_id, connection)
        boundary, next_run = _skip_period_schedule(todo, payload.period)
        if (
            (payload.expected_period_ends_at is not None
                and payload.expected_period_ends_at.astimezone(timezone.utc)
                != boundary.astimezone(timezone.utc))
            or (payload.expected_reminder_revision is not None
                and payload.expected_reminder_revision != todo.reminder_revision)
            or (payload.expected_next_run_at is not None
                and payload.expected_next_run_at.astimezone(timezone.utc)
                != next_run.astimezone(timezone.utc))
        ):
            raise ValidationError("预览已过期，请重新确认")
        _invalidate_claim(todo)
        todo.reminder_next_run_at = next_run
        todo.reminder_next_attempt_at = next_run
        todo.reminder_attempts = 0
        todo.reminder_error = ""
        todo.reminder_status = "pending"
        await todo.save(using_db=connection)
    return success(todo_dict(todo), message="updated")


@bp.put("/<todo_id:int>")
@login_required
async def update_todo(request: Request, todo_id: int):
    _ensure_admin(request)
    payload = _payload(request, TodoIn)
    async with in_transaction() as connection:
        todo = await _locked_todo(request.ctx.user.id, todo_id, connection)
        if todo.is_completed and payload.reminder_enabled:
            raise ValidationError("请先将事项恢复为未完成，再启用提醒")
        reset_schedule = (
            todo.due_at != payload.due_at
            or todo.reminder_repeat != payload.reminder_repeat
            or todo.reminder_timezone != payload.reminder_timezone
            or todo.reminder_cron != payload.reminder_cron
            or (not todo.reminder_enabled and payload.reminder_enabled)
        )
        reschedule = (
            reset_schedule
            or todo.reminder_enabled != payload.reminder_enabled
            or todo.reminder_email != payload.reminder_email
        )
        pending = todo.reminder_status in {"pending", "sending"}
        for name, value in payload.model_dump().items():
            setattr(todo, name, value)
        _invalidate_claim(todo)
        if reschedule or pending or not todo.reminder_enabled:
            _reset_reminder(todo, reset_schedule=reset_schedule or todo.reminder_repeat == "once")
        await todo.save(using_db=connection)
    return success(todo_dict(todo), message="updated")


@bp.patch("/<todo_id:int>/completion")
@login_required
async def set_todo_completion(request: Request, todo_id: int):
    _ensure_admin(request)
    payload = _payload(request, TodoCompletionIn)
    async with in_transaction() as connection:
        todo = await _locked_todo(request.ctx.user.id, todo_id, connection)
        if todo.is_completed != payload.is_completed:
            todo.is_completed = payload.is_completed
            todo.reminder_enabled = False
            _invalidate_claim(todo)
            todo.reminder_status = "disabled"
            todo.reminder_next_run_at = None
            todo.reminder_next_attempt_at = None
            todo.reminder_error = ""
            await todo.save(using_db=connection)
    return success(todo_dict(todo), message="updated")


@bp.delete("/<todo_id:int>")
@login_required
async def delete_todo(request: Request, todo_id: int):
    _ensure_admin(request)
    async with in_transaction() as connection:
        todo = await _locked_todo(request.ctx.user.id, todo_id, connection)
        await todo.delete(using_db=connection)
    return success(message="deleted")


@bp.post("/<todo_id:int>/retry")
@login_required
async def retry_todo_reminder(request: Request, todo_id: int):
    _ensure_admin(request)
    async with in_transaction() as connection:
        todo = await _locked_todo(request.ctx.user.id, todo_id, connection)
        if todo.reminder_status != "failed" or not todo.reminder_enabled or todo.is_completed:
            raise ValidationError("仅发送失败且未完成的提醒可以重试")
        _invalidate_claim(todo)
        _reset_reminder(todo)
        await todo.save(using_db=connection)
    return success(todo_dict(todo), message="updated")
