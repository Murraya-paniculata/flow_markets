"""全局依赖：鉴权、DB Session、Request ID 等。"""

from uuid import uuid4

from fastapi import Request

from app.core.security import verify_api_key
from app.db.clients.oceanbase_client import get_db
from app.observability.logging import set_request_id

# 鉴权：直接复用 security 中的依赖
require_api_key = verify_api_key


async def get_request_id(request: Request) -> str:
    """从请求头获取或生成 request_id，并注入上下文。"""
    rid = request.headers.get("X-Request-ID") or str(uuid4())
    set_request_id(rid)
    return rid


# DB Session：供 API 层通过 Depends(get_db) 注入
__all__ = ["require_api_key", "get_request_id", "get_db"]
