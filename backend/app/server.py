"""Sanic 应用工厂。"""
from __future__ import annotations

from sanic import Sanic
from sanic_ext import Extend
from tortoise.contrib.sanic import register_tortoise

from app.api import register_blueprints
from app.core.config import TORTOISE_ORM, settings
from app.core.exceptions import register_exception_handlers
from app.core.redis import close_redis, init_redis


def create_app() -> Sanic:
    app = Sanic("sudothink")

    # 基础配置
    app.config.SECRET = settings.APP_SECRET_KEY
    app.config.CORS_ORIGINS = settings.CORS_ORIGINS_LIST
    app.config.CORS_SUPPORTS_CREDENTIALS = True
    app.config.FALLBACK_ERROR_FORMAT = "json"

    Extend(app)

    # 注册路由
    register_blueprints(app)

    # 注册全局异常处理
    register_exception_handlers(app)

    # 注册 Tortoise ORM
    register_tortoise(
        app,
        config=TORTOISE_ORM,
        generate_schemas=False,
    )

    # Redis 生命周期
    @app.before_server_start
    async def _setup_redis(app_, _loop):
        await init_redis()

    @app.after_server_stop
    async def _close_redis(app_, _loop):
        await close_redis()

    return app
