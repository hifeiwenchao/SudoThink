"""Private reminder outcome history; no mail body, address or claim tokens."""
from tortoise import fields, models
from app.models.todo import TodoDatetimeField


class TodoReminderHistory(models.Model):
    id = fields.BigIntField(pk=True)
    todo = fields.ForeignKeyField("models.Todo", related_name="reminder_history", on_delete=fields.CASCADE)
    event = fields.CharField(max_length=16)
    scheduled_at = TodoDatetimeField(null=True)
    created_at = TodoDatetimeField(auto_now_add=True)
    next_run_at = TodoDatetimeField(null=True)
    error = fields.CharField(max_length=255, default="")
    period = fields.CharField(max_length=8, default="")

    class Meta:
        table = "todo_reminder_history"
        indexes = (("todo_id", "created_at"),)
