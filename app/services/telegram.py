import json
import asyncio
import httpx
from datetime import datetime
from typing import Optional

from app.config import settings

_template = """🚨 *Erro detectado no ApexEnem*

*Origem:* {origem}
*Afetando:* {usuarios}

*O que tá acontecendo:*
```
{erro}
```

*Meu diagnóstico:*
{diagnostico}

*Plano pra resolver:*
{plano}

*Como reproduzir:*
{reproducao}

*Preview:*
{preview_url}

---
Responde com:
✅ "Ok" — Aprova e publica
❌ "Não gostei" — Refaz o plano
🔄 "Reverte" — Cancela e desfaz"""


async def send_typing():
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendChatAction"
    async with httpx.AsyncClient(timeout=10) as client:
        await client.post(url, json={
            "chat_id": settings.allowed_telegram_user_id,
            "action": "typing",
        })


async def _keep_typing(stop_event: asyncio.Event):
    while not stop_event.is_set():
        try:
            await send_typing()
        except Exception:
            pass
        await asyncio.sleep(4)


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
    try:
        message = update.get("message", {})
        if not message:
            return

        chat_id = message.get("chat", {}).get("id")
        if chat_id != settings.allowed_telegram_user_id:
            return

        if message.get("from", {}).get("is_bot"):
            return

        if not message.get("text"):
            return

        text = message.get("text", "").strip().lower()
        reply = message.get("reply_to_message", {}).get("text", "")

        if text == "/start":
            await send_telegram_message(
                "E aí, Fernando! Tô online. 👋\n\n"
                "Manda a mensagem que eu resolvo. Se quiser ver o status do sistema, é /status."
            )
        elif text == "/status":
            try:
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
            except Exception as e:
                await send_telegram_message(f"❌ Erro ao obter status: {str(e)}")
        elif text == "/help":
            await send_telegram_message(
                "Bora lá:\n\n"
                "/status — Resumo do sistema\n"
                "/help — Isso aqui\n\n"
                "Outras coisas que rola fazer:\n"
                "✅ \"Ok\" / \"Aprovado\" — Aprova o fix\n"
                "❌ \"Não gostei\" / \"Refaça\" — Gera outro plano\n"
                "🔄 \"Reverte\" / \"Deu problema\" — Faz rollback"
            )

        active_fix = _get_active_fix_from_reply(reply)
        if active_fix:
            from app.database import get_error_by_id, update_fix_attempt, update_error_status, increment_fix_attempts, set_cooldown, set_error_give_up
            from app.services.pipeline import handle_fix_feedback

            action = _classify_feedback(text)
            await handle_fix_feedback(active_fix, action)
            return

        inv_error_id = _get_pending_investigation_from_reply(reply)
        if inv_error_id:
            await _handle_investigation_response(inv_error_id, text)
            return

        if not reply and text in ("sim", "não", "nao", "investigar", "ignorar"):
            from app.routers.reports import get_latest_pending
            latest = get_latest_pending()
            if latest is not None:
                await _handle_investigation_response(latest, text)
                return

        if text and not text.startswith("/") and not reply:
            await _answer_user_message(text)
    except Exception as e:
        await send_telegram_message(f"❌ Erro inesperado: {str(e)}")


async def _try_execute_action(text: str) -> bool:
    import re
    from app.database import get_error_by_id, get_error_by_hash, update_error_status

    tl = text.lower().strip()

    archive_match = re.search(r'(?:arquiv|archive|arquiv)\w*\s+(?:o\s+)?(?:erro\s+)?#?(\d+)', tl)
    if archive_match:
        eid = int(archive_match.group(1))
        err = get_error_by_id(eid)
        if err:
            update_error_status(eid, "archived_no_log")
            await send_telegram_message(f"Pronto, erro #{err['hash']} arquivado. 👍")
        else:
            await send_telegram_message(f"Erro #{eid} não achei no banco. Verifica o ID.")
        return True

    reopen_match = re.search(r'(?:reabra|reabrir|reopen)\w*\s+(?:o\s+)?(?:erro\s+)?#?(\d+)', tl)
    if reopen_match:
        eid = int(reopen_match.group(1))
        err = get_error_by_id(eid)
        if err:
            update_error_status(eid, "new")
            await send_telegram_message(f"Erro #{err['hash']} reaberto! Tá de volta na fila.")
        else:
            await send_telegram_message(f"Erro #{eid} não achei. Confere o ID.")
        return True

    return False


async def _answer_user_message(text: str):
    if await _try_execute_action(text):
        return

    from app.services.ai_client import chat_with_ai
    from app.database import get_dashboard_stats, get_recent_activity, is_maintenance_mode, get_errors_paginated

    stop_typing = asyncio.Event()
    typing_task = asyncio.create_task(_keep_typing(stop_typing))

    try:
        stats = get_dashboard_stats()
        recent_errors_list, _ = get_errors_paginated(page=1, per_page=10)
        errors_summary = "\n".join(
            f"- #{e['id']} (hash: {e['hash'][:12]}): {e['description'][:100]} — status: {e['status']}"
            for e in (recent_errors_list or [])
        ) or "Nenhum erro registrado."

        mm = "ATIVO" if is_maintenance_mode() else "inativo"
        system_prompt = (
            "Você é o ApexGuardian — um programador sênior com mais de 15 anos de experiência em desenvolvimento web, "
            "devops e arquitetura de sistemas. Você trabalha diretamente com o Fernando, o dono do ApexEnem.\n\n"
            "Personalidade:\n"
            "- Fale como um humano real, com gírias leves do dia a dia de um dev (tipo 'caramba', 'porra', 'beleza', 'mano').\n"
            "- Seja direto, mas sem ser grosso. Explica as coisas como se estivesse conversando com um colega de trabalho.\n"
            "- Usa emojis com moderação, só quando faz sentido (tipo ✅ pra confirmar, 🔥 pra coisa boa).\n"
            "- Se não sabe algo, admite na hora — programador sênior não inventa resposta.\n"
            "- Pode usar humor quando apropriado, nada forçado.\n"
            "- Trata o Fernando como parceiro de trabalho, não como cliente.\n\n"
            "Estilo de resposta:\n"
            "- Respostas curtas e diretas (máximo 4-5 linhas).\n"
            "- Não usa linguagem robótica tipo 'Claro! Posso ajudá-lo com isso!'.\n"
            "- Se a pergunta é simples, responde simples. Não enrola.\n"
            "- Se o assunto é sério (erro crítico, produção fora do ar), fala sério.\n"
            "- Mistura português natural com termos técnicos em inglês quando necessário (tipo 'deploy', 'hotfix', 'rollback').\n\n"
            f"Status do sistema agora: manutenção={mm}, {stats['active']} erros ativos, {stats['resolved']} resolvidos, "
            f"{stats['total']} total, {stats['total_users']} usuários únicos.\n\n"
            f"Erros recentes:\n{errors_summary}\n\n"
            "Responda em português do Brasil. Se o usuário escrever em inglês, responda em inglês."
        )

        result = await chat_with_ai([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ], timeout=90)

        if result:
            await send_telegram_message(result)
            return

        import logging
        log = logging.getLogger("telegram")
        log.warning("chat_with_ai retornou None para: %s", text[:50])

        try:
            from app.database import get_dashboard_stats, get_recent_activity, is_maintenance_mode
            stats = get_dashboard_stats()
            tl = text.lower()

            if any(p in tl for p in ["status", "resumo"]):
                mm = "🚧 ativo" if is_maintenance_mode() else "✅ inativo"
                await send_telegram_message(
                    f"📊 *Resumo do ApexGuardian*\n\n"
                    f"Manutenção: {mm}\n"
                    f"Erros ativos: {stats['active']}\n"
                    f"Resolvidos: {stats['resolved']}\n"
                    f"Em preview: {stats['preview']}\n"
                    f"Ignorados: {stats['ignored']}\n"
                    f"Total: {stats['total']}\n"
                    f"Usuários únicos: {stats['total_users']}"
                )
                return

            if any(p in tl for p in ["erro", "erros", "bug", "bugs"]):
                recent = get_recent_activity(5)
                lines = "\n".join(
                    f"• #{a['id']} — {a['description'][:80]}"
                    for a in recent
                ) if recent else "Nenhum erro recente."
                await send_telegram_message(f"🔍 *Erros recentes:*\n\n{lines}")
                return

            if any(p in tl for p in ["quem é você", "quem és", "o que você faz", "ajuda", "help"]):
                await send_telegram_message(
                    "Sou o ApexGuardian, mano. Cuido dos erros do ApexEnem — pego os logs da Vercel, "
                    "investigo o que tá quebrado e proponho correções.\n\n"
                    "/status — Resumo rápido\n"
                    "/help — Comandos"
                )
                return

            await send_telegram_message(
                "Ih, a IA tá fora do ar no momento. 😅\n"
                "Mas o sistema tá de pé — usa /status pra ver o que rola."
            )
        except Exception:
            await send_telegram_message(
                "Tô aqui! Usa /status pra ver o estado do sistema."
            )
    finally:
        stop_typing.set()
        typing_task.cancel()


def _get_pending_investigation_from_reply(reply: str) -> Optional[int]:
    import re
    match = re.search(r'ERROR_ID[:_]\s*(\d+)', reply)
    if match:
        return int(match.group(1))
    return None


async def _handle_investigation_response(error_id: int, text: str):
    from app.database import update_error_status
    from app.services.pipeline import run_investigation_pipeline
    from app.routers.reports import get_pending_investigation, remove_pending_investigation
    hash_val = get_pending_investigation(error_id)
    if not hash_val:
        return

    approve = ["sim", "investigar", "pode investigar", "vai", "ok", "pode ir", "iniciar"]
    reject = ["não", "nao", "ignorar", "arquivar", "deixa", "deixa quieto", "para"]

    if any(p in text for p in approve):
        remove_pending_investigation(error_id)
        stop = asyncio.Event()
        typing = asyncio.create_task(_keep_typing(stop))
        await send_telegram_message(f"Beleza, investigating error #{error_id}... 🔍")
        try:
            await run_investigation_pipeline(error_id)
        finally:
            stop.set()
            typing.cancel()
    elif any(r in text for r in reject):
        remove_pending_investigation(error_id)
        update_error_status(error_id, "ignored")
        await send_telegram_message(f"Certo, erro #{error_id} ignorado. Se mudar de ideia, é só falar.")
    else:
        await send_telegram_message(
            f"Não entendi. Manda \"Sim\" pra eu investigar ou \"Não\" pra ignorar."
        )


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
