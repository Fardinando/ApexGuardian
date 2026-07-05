import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database import init_db, seed_admin, is_maintenance_mode
from app.services.maintenance import start_reminder
from app.routers import health, reports, telegram_webhook, admin
from app.workers.log_poller import poll_logs_loop
from app.workers.volume_checker import check_volume_loop

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("apexguardian")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Inicializando ApexGuardian...")
    init_db()
    seed_admin()
    logger.info("Banco de dados inicializado. Admin Supreme criado.")

    import asyncio
    poll_task = asyncio.create_task(poll_logs_loop(180))
    volume_task = asyncio.create_task(check_volume_loop(3600))
    logger.info("Workers iniciados: log poller (3min), volume checker (1h)")

    if is_maintenance_mode():
        logger.warning("Sistema em modo de manutenção!")
        start_reminder()
        from app.services.maintenance import send_maintenance_alert
        import asyncio
        asyncio.create_task(send_maintenance_alert(True))

    yield

    poll_task.cancel()
    volume_task.cancel()
    logger.info("Workers finalizados. ApexGuardian encerrando.")


app = FastAPI(
    title="ApexGuardian",
    description="Assistente automatizado de gerenciamento de bugs para ApexEnem",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return RedirectResponse(url="/admin", status_code=302)

app.include_router(health.router)
app.include_router(reports.router)
app.include_router(telegram_webhook.router)
app.include_router(admin.router)
