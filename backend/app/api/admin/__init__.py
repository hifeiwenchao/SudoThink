"""管理后台 API。"""
from sanic import Blueprint

from app.api.admin.dashboard import bp as dashboard_bp
from app.api.admin.users import bp as users_bp
from app.api.admin.articles import bp as articles_bp
from app.api.admin.comments import bp as comments_bp
from app.api.admin.about import bp as about_bp
from app.api.admin.donations import bp as donations_bp
from app.api.admin.uploads import bp as uploads_bp


bp = Blueprint.group(
    dashboard_bp,
    users_bp,
    articles_bp,
    comments_bp,
    about_bp,
    donations_bp,
    uploads_bp,
    url_prefix="/admin",
)

__all__ = ["bp"]
