"""API 路由蓝图汇总。"""
from sanic import Blueprint, Sanic

from app.api.admin import bp as admin_bp
from app.api.article import bp as article_bp
from app.api.auth import bp as auth_bp
from app.api.category import bp as category_bp
from app.api.comment import bp as comment_bp
from app.api.health import bp as health_bp
from app.api.tag import bp as tag_bp


def register_blueprints(app: Sanic) -> None:
    api = Blueprint.group(
        health_bp,
        auth_bp,
        article_bp,
        category_bp,
        tag_bp,
        comment_bp,
        admin_bp,
        url_prefix="/api",
    )
    app.blueprint(api)
