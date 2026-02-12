from fastapi import APIRouter

from router.various import various_router
from router.draft import draft_router
from router.l1 import l1_router
from router.l2 import l2_router

combine_router = APIRouter(prefix="/v1")
combine_router.include_router(various_router.router)
combine_router.include_router(draft_router.router)
combine_router.include_router(l1_router.router)
combine_router.include_router(l2_router.router)


