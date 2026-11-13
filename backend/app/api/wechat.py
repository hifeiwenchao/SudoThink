"""微信网页分享接口。"""
from sanic import Blueprint, Request

from app.core.exceptions import APIError, ValidationError
from app.core.response import success
from app.core.wechat import WeChatError, create_signature

bp = Blueprint("wechat", url_prefix="/wechat")


@bp.get("/signature")
async def get_signature(request: Request):
    url = request.args.get("url")
    if not url:
        raise ValidationError("url is required")
    try:
        data = await create_signature(url)
    except ValueError as exc:
        raise ValidationError(str(exc)) from None
    except WeChatError:
        # 不把 AppSecret、access_token 或远端错误信息返回给浏览器。
        raise APIError("wechat sharing is temporarily unavailable", code=10503, status=503) from None
    return success(data)
