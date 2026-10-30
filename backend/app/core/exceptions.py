"""异常与全局异常处理。"""
from __future__ import annotations

from sanic import Request, Sanic
from sanic.exceptions import SanicException
from sanic.response import JSONResponse

from app.core.response import fail


class APIError(SanicException):
    """业务异常基类。"""

    def __init__(self, message: str = "error", code: int = 1, status: int = 400) -> None:
        super().__init__(message=message, status_code=status)
        self.code = code
        self.api_message = message
        self.status = status


class NotFoundError(APIError):
    def __init__(self, message: str = "not found") -> None:
        super().__init__(message=message, code=10404, status=404)


class UnauthorizedError(APIError):
    def __init__(self, message: str = "unauthorized") -> None:
        super().__init__(message=message, code=10401, status=401)


class ForbiddenError(APIError):
    def __init__(self, message: str = "forbidden") -> None:
        super().__init__(message=message, code=10403, status=403)


class ValidationError(APIError):
    def __init__(self, message: str = "validation error") -> None:
        super().__init__(message=message, code=10422, status=422)


def register_exception_handlers(app: Sanic) -> None:
    @app.exception(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return fail(message=exc.api_message, code=exc.code, status=exc.status)

    @app.exception(SanicException)
    async def _sanic_error(_: Request, exc: SanicException) -> JSONResponse:
        return fail(
            message=str(exc) or "server error",
            code=exc.status_code,
            status=exc.status_code,
        )

    @app.exception(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        return fail(message=str(exc) or "internal server error", code=500, status=500)
