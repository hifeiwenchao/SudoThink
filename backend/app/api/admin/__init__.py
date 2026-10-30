"""管理后台 API。"""
from sanic import Blueprint

from app.api.admin.dashboard import bp as dashboard_bp
from app.api.admin.users import bp as users_bp
from app.api.admin.articles import bp as articles_bp
from app.api.admin.comments import bp as comments_bp


bp = Blueprint.group(
    dashboard_bp,
    users_bp,
    articles_bp,
    comments_bp,
    url_prefix="/admin",
)

__all__ = ["bp"]
