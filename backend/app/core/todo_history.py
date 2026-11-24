"""Atomically store an outcome only when its reminder claim still owns state."""
from tortoise.transactions import in_transaction
from app.models.todo import Todo
from app.models.todo_history import TodoReminderHistory


async def save_reminder_outcome(todo, claim, changes, event) -> int:
    async with in_transaction() as connection:
        changed = await Todo.filter(**claim).using_db(connection).update(**changes)
        if changed:
            await TodoReminderHistory.create(
                todo_id=todo.id, event=event, scheduled_at=todo.reminder_next_run_at,
                next_run_at=changes.get("reminder_next_run_at", todo.reminder_next_run_at),
                error=changes.get("reminder_error", ""), using_db=connection,
            )
    return changed
