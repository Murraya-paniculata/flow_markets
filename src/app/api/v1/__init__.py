"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import demo
from app.api.v1 import flow_markets

api_router = APIRouter(prefix="/api/v1", tags=["v1"])
api_router.include_router(demo.router, prefix="/demo", tags=["demo"])
api_router.include_router(flow_markets.router, prefix="/flow-markets", tags=["flow-markets"])
