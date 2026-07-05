import asyncio
import logging
from typing import Optional

from app.database import is_maintenance_mode
from app.services.telegram import send_simple_message

logger = logging.getLogger("apexguardian.maintenance")

_reminder_task: Optional[asyncio.Task] = None
REMINDER_INTERVAL = 1800  # 30min


async def send_maintenance_alert(ativado: bool):
    if ativado:
        await send_simple_message(
            "🚧 *MODO DE MANUTENÇÃO ATIVADO*\n\n"
            "O controle de erros do ApexEnem está pausado.\n"
            "Nenhum novo erro será investigado até que o modo seja desativado.\n\n"
            "Lembrete automático a cada 30min enquanto estiver ativo."
        )
    else:
        await send_simple_message(
            "✅ *MODO DE MANUTENÇÃO DESATIVADO*\n\n"
            "O controle de erros do ApexEnem foi retomado."
        )


async def _send_reminder():
    await send_simple_message(
        "🔁 *LEMBRETE — Manutenção Ativa*\n\n"
        "O modo de manutenção do ApexEnem continua ativo.\n"
        "Investigações de erros estão pausadas.\n\n"
        "Desative no painel admin quando finalizar."
    )


async def _reminder_loop():
    try:
        while True:
            await asyncio.sleep(REMINDER_INTERVAL)
            if is_maintenance_mode():
                await _send_reminder()
    except asyncio.CancelledError:
        pass


def start_reminder():
    global _reminder_task
    if _reminder_task is None or _reminder_task.done():
        _reminder_task = asyncio.create_task(_reminder_loop())
        logger.info("Lembrete de manutenção iniciado (30min)")


def stop_reminder():
    global _reminder_task
    if _reminder_task and not _reminder_task.done():
        _reminder_task.cancel()
        _reminder_task = None
        logger.info("Lembrete de manutenção parado")


async def notify_and_toggle(ativado: bool):
    if ativado:
        await send_maintenance_alert(True)
        start_reminder()
    else:
        await send_maintenance_alert(False)
        stop_reminder()
