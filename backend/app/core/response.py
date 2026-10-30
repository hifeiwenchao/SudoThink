"""统一响应。"""
from __future__ import annotations

from typing import Any

from sanic.response import JSONResponse, json


def success(data: Any = None, message: str = "ok", code: int = 0) -> JSONResponse:
    return json({"code": code, "message": message, "data": data})


def fail(message: str = "error", code: int = 1, status: int = 400, data: Any = None) -> JSONResponse:
    return json({"code": code, "message": message, "data": data}, status=status)
