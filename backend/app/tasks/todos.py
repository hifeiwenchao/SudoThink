"""Due reminders using the Celery worker's persistent async resources."""
from app.celery_app import celery_app
from app.celery_runtime import run_with_worker_resources


@celery_app.task(name="app.tasks.todos.send_due_reminders", ignore_result=True)
def send_due_reminders() -> dict:
    async def run(redis) -> dict:
        # Beat/discovery must not import ORM, models, mail transport, or Sanic.
        from app.core.todo_reminders import process_due_reminders

        return await process_due_reminders()

    return run_with_worker_resources(run)
