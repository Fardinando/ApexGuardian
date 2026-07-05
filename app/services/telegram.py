import json
import httpx
from datetime import datetime
from typing import Optional

from app.config import settings

_template = """🛡️ *APEXGUARDIAN - NOVA INTERAÇÃO*

📌 *Origem:* {origem}
👥 *Usuários afetados:* {usuarios}

🔍 *Erro Detectado:*
```
{erro}
```

🧠 *Diagnóstico e Significado:*
{diagnostico}

📋 *Plano de Correção Proposto:*
{plano}

📎 *Reprodução (como obter o erro):*
{reproducao}

🔗 *Link do Deploy Preview:*
{preview_url}

---
*Comandos:*
✅ "Ok" / "Aprovado" -> Publica em Produção.
❌ "Não gostei" / "Refaça" -> Gera novo plano.
🔄 "Reverte" / "Deu problema" -> Cancela deploy e deleta branch."""


async def send_telegram_message(text: str, parse_mode: str = "Markdown") -> dict:
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json={
            "chat_id": settings.allowed_telegram_user_id,
            "text": text,
            "parse_mode": parse_mode,
        })
        return resp.json()


async def send_error_notification(origem: str, usuarios: str, erro: str,
                                  diagnostico: str, plano: str, reproducao: str,
                                  preview_url: str = "N/A (aguardando aprovação)"):
    text = _template.format(
        origem=origem,
        usuarios=usuarios,
        erro=erro[:4000],
        diagnostico=diagnostico,
        plano=plano,
        reproducao=reproducao,
        preview_url=preview_url,
    )
    return await send_telegram_message(text)


async def send_simple_message(message: str):
    return await send_telegram_message(message)


async def send_urgent_message(message: str):
    text = f"🚨 *APEXGUARDIAN - URGENTE* 🚨\n\n{message}"
    return await send_telegram_message(text)


async def process_telegram_update(update: dict):
    message = update.get("message", {})
    if not message:
        return

    chat_id = message.get("chat", {}).get("id")
    if chat_id != settings.allowed_telegram_user_id:
        return

    text = (message.get("text") or "").strip().lower()
    reply = message.get("reply_to_message", {}).get("text", "")

    if text == "/start":
        await send_telegram_message(
            "🛡️ ApexGuardian ativo!\n\n"
            "Monitore os erros do ApexEnem e gerencie correções.\n"
            "Use /status para ver o estado atual."
        )
    elif text == "/status":
        from app.database import get_dashboard_stats, is_maintenance_mode
        stats = get_dashboard_stats()
        mm = "🚧 *ATIVO*" if is_maintenance_mode() else "✅ *Inativo*"
        msg = (
            f"📊 *Status do ApexGuardian*\n\n"
            f"Manutenção: {mm}\n"
            f"Total de erros: {stats['total']}\n"
            f"Ativos: {stats['active']}\n"
            f"Em preview: {stats['preview']}\n"
            f"Resolvidos: {stats['resolved']}\n"
            f"Arquivados completos: {stats['fully_archived']}\n"
            f"Arquivados parciais: {stats['partially_archived']}\n"
            f"Em cooldown: {stats['cooldown']}\n"
            f"Ignorados: {stats['ignored']}\n"
            f"Usuários únicos: {stats['total_users']}"
        )
        await send_telegram_message(msg)
    elif text == "/help":
        await send_telegram_message(
            "Comandos disponíveis:\n"
            "/status - Status do sistema\n"
            "/help - Esta mensagem\n\n"
            "Responda a uma notificação com:\n"
            "✅ Ok / Aprovado - Avança\n"
            "❌ Não gostei / Refaça - Novo plano\n"
            "🔄 Reverte / Deu problema - Rollback"
        )

    active_fix = _get_active_fix_from_reply(reply)
    if active_fix:
        from app.database import get_error_by_id, update_fix_attempt, update_error_status, increment_fix_attempts, set_cooldown, set_error_give_up
        from app.services.pipeline import handle_fix_feedback

        action = _classify_feedback(text)
        await handle_fix_feedback(active_fix, action)


def _get_active_fix_from_reply(reply: str) -> Optional[int]:
    import re
    match = re.search(r'FIX_ID[:_]\s*(\d+)', reply)
    if match:
        return int(match.group(1))
    return None


def _classify_feedback(text: str) -> str:
    positive = ["ok", "aprovado", "vamos em frente", "sim", "pode ir", "vai"]
    negative = ["não gostei", "refaça", "refazer", "mude", "altere", "nao gostei"]
    rollback = ["reverte", "deu problema", "volt", "cancel", "desfaz"]

    if any(p in text for p in positive):
        return "approved"
    if any(r in text for r in rollback):
        return "rollback"
    if any(n in text for n in negative):
        return "rejected"
    return "unknown"
