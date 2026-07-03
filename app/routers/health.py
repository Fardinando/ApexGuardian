from fastapi import APIRouter
from datetime import datetime, timezone

from app.database import get_dashboard_stats

router = APIRouter(tags=["health"])
start_time = datetime.now(timezone.utc)


@router.get("/health")
async def health_check():
    uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
    return {
        "status": "ok",
        "service": "ApexGuardian",
        "version": "1.0.0",
        "uptime_seconds": int(uptime),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
