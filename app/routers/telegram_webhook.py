from fastapi import APIRouter, Request, HTTPException
import json

from app.config import settings
from app.services.telegram import process_telegram_update

router = APIRouter(prefix="/webhook", tags=["telegram"])


@router.post("/telegram")
async def telegram_webhook(request: Request):
    try:
        body = await request.json()
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    await process_telegram_update(body)
    return {"status": "ok"}
