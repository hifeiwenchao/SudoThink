"""Sanic 应用入口。"""
from app.server import create_app
from app.core.config import settings


app = create_app()


if __name__ == "__main__":
    app.run(
        host=settings.APP_HOST,
        port=settings.APP_PORT,
        debug=settings.APP_DEBUG,
        auto_reload=settings.APP_DEBUG,
        access_log=settings.APP_DEBUG,
        single_process=True,
    )
