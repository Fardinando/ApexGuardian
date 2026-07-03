import asyncio
from typing import Optional

from app.database import (
    get_error_by_id, get_error_by_hash, get_reports_for_error,
    get_fix_attempts_for_error, create_fix_attempt, update_fix_attempt,
    update_error_status, increment_fix_attempts, set_cooldown, set_error_give_up,
    get_dashboard_stats, now_iso, hash_error, upsert_error_signature,
)
from app.services.ollama import diagnose_error, generate_fix_plan, investigate_error
from app.services.search import search_error
from app.services.telegram import send_error_notification, send_urgent_message, send_simple_message

_active_fixes: dict[int, dict] = {}


async def run_investigation_pipeline(error_sig_id: int):
    error = get_error_by_id(error_sig_id)
    if not error:
        return

    if error["status"] in ("cooldown", "give_up", "production", "ignored"):
        return

    update_error_status(error["id"], "analyzing")

    stack_trace = error["stack_trace"] or ""
    description = error["description"] or ""
    query = f"{stack_trace[:200]} {description[:100]} Next.js React Vercel"
    search_results = await search_error(query)

    diagnosis = await diagnose_error(stack_trace, description, search_results)
    plan = await generate_fix_plan(stack_trace, description, diagnosis, search_results)

    reports = get_reports_for_error(error["id"])
    unique_users = len(set(r["user_id_anon"] for r in reports))
    origin_map = {
        "user_report": "Denúncia de Usuário",
        "vercel_log": "Log Vercel",
        "volume_trigger": "Gatilho por Volume",
        "manual_input": "Adição Manual",
    }
    origin_label = origin_map.get(error["origin"], error["origin"])

    update_error_status(error["id"], "waiting_approval")

    fix_id = create_fix_attempt(
        error["id"],
        error["fix_attempts"] + 1,
        f"FIX_ID:{error['id']}\n\n{plan}",
    )

    _active_fixes[error["id"]] = {
        "fix_id": fix_id,
        "attempt": error["fix_attempts"] + 1,
        "plan": plan,
        "diagnosis": diagnosis,
        "reproducao": _generate_reproduction_steps(stack_trace, description),
    }

    await send_error_notification(
        origem=origin_label,
        usuarios=str(unique_users) if unique_users > 0 else "N/A",
        erro=stack_trace[:2000] or description[:2000],
        diagnostico=diagnosis,
        plano=plan,
        reproducao=_generate_reproduction_steps(stack_trace, description),
    )


async def handle_fix_feedback(error_id: int, action: str):
    error = get_error_by_id(error_id)
    if not error:
        return

    fix_data = _active_fixes.get(error_id)
    if not fix_data:
        return

    if action == "approved":
        from app.services.git_ops import apply_fix_and_deploy
        await send_simple_message(f"✅ Plano aprovado! Iniciando correção do erro #{error['hash']}...")
        result = await apply_fix_and_deploy(error, fix_data)
        if result["success"]:
            update_fix_attempt(fix_data["fix_id"], status="approved",
                               branch_name=result["branch"], preview_url=result["preview_url"])
            update_error_status(error_id, "preview")
            await send_error_notification(
                origem="Correção Automática",
                usuarios=str(error["unique_users"]),
                erro=error["stack_trace"] or error["description"] or "",
                diagnostico=fix_data["diagnosis"],
                plano=fix_data["plan"],
                reproducao=fix_data["reproducao"],
                preview_url=result["preview_url"],
            )
            await send_simple_message(
                f"🔗 *Preview URL:* {result['preview_url']}\n\n"
                f"📎 *Como testar:* Siga os passos de reprodução acima na URL de preview.\n\n"
                f"Responda com:\n"
                f"✅ \"Ok\" / \"Aprovado para produção\" → Publica em produção\n"
                f"🔄 \"Reverte\" / \"Deu problema\" → Cancela e deleta branch"
            )
        else:
            await send_urgent_message(f"❌ Falha ao aplicar correção: {result['error']}")

    elif action == "rollback":
        from app.services.git_ops import rollback_fix
        await send_simple_message(f"🔄 Revertendo correção do erro #{error['hash']}...")
        fix_attempts = get_fix_attempts_for_error(error["id"])
        last_fix = fix_attempts[-1] if fix_attempts else None
        if last_fix and last_fix.get("branch_name"):
            rollback_fix(last_fix["branch_name"])
        update_fix_attempt(fix_data["fix_id"], status="rolled_back")
        update_error_status(error_id, "new")
        _active_fixes.pop(error_id, None)
        await send_simple_message("✅ Rollback concluído. Branch deletada.")

    elif action == "rejected":
        neg_count = fix_data.get("feedback_round", 0) + 1
        fix_data["feedback_round"] = neg_count
        update_fix_attempt(fix_data["fix_id"], feedback_round=neg_count,
                           user_feedback="rejected")

        if neg_count >= 3:
            set_error_give_up(error_id)
            _active_fixes.pop(error_id, None)
            await send_urgent_message(
                f"🚨 *ERRO PERMANECE APÓS 3 TENTATIVAS* 🚨\n\n"
                f"Erro #{error['hash']}: {error['description'][:200]}\n\n"
                f"O ApexGuardian está desistindo deste erro por 24 horas.\n"
                f"Intervenção manual necessária.\n\n"
                f"Painel Admin: /admin/errors/{error['id']}"
            )
        else:
            await send_simple_message(f"🔄 Refazendo plano (tentativa {neg_count + 1}/3)...")
            stack_trace = error["stack_trace"] or ""
            description = error["description"] or ""
            query = f"{stack_trace[:200]} {description[:100]} Next.js React Vercel fix"
            search_results = await search_error(query)
            diagnosis = await diagnose_error(stack_trace, description, search_results)
            new_plan = await generate_fix_plan(stack_trace, description, diagnosis, search_results)

            fix_data["plan"] = new_plan
            fix_data["diagnosis"] = diagnosis
            fix_data["attempt"] += 1

            new_fix_id = create_fix_attempt(
                error["id"], fix_data["attempt"],
                f"FIX_ID:{error['id']}\n\n{new_plan}",
            )
            fix_data["fix_id"] = new_fix_id

            reports = get_reports_for_error(error["id"])
            unique_users = len(set(r["user_id_anon"] for r in reports))

            await send_error_notification(
                origem=f"Refatoração (tentativa {fix_data['attempt']}/3)",
                usuarios=str(unique_users) if unique_users > 0 else "N/A",
                erro=stack_trace[:2000] or description[:2000],
                diagnostico=diagnosis,
                plano=new_plan,
                reproducao=_generate_reproduction_steps(stack_trace, description),
            )


async def run_manual_investigation(stack_trace: str, description: str = "",
                                    url: str = "", context: str = "") -> dict:
    query = f"{stack_trace[:200]} {description[:100]} Next.js React Vercel"
    search_results = await search_error(query)
    result = await investigate_error(stack_trace, description, search_results)

    if result.get("is_real_bug") and result.get("confidence", 0) >= 50:
        hash_val = hash_error(stack_trace=stack_trace, description=description)
        error_id = upsert_error_signature(
            hash_val=hash_val, stack_trace=stack_trace,
            description=description or context, origin="manual_input",
        )
        update_error_status(error_id, "new")
        asyncio.create_task(run_investigation_pipeline(error_id))
        return {
            "is_real_bug": True,
            "confidence": result["confidence"],
            "reason": result["reason"],
            "error_id": error_id,
            "message": "Erro real detectado. Investigação iniciada.",
        }
    else:
        hash_val = hash_error(stack_trace=stack_trace, description=description)
        error_id = upsert_error_signature(
            hash_val=hash_val, stack_trace=stack_trace,
            description=f"IGNORADO: {description or context}",
            origin="manual_input",
        )
        update_error_status(error_id, "ignored")
        return {
            "is_real_bug": False,
            "confidence": result.get("confidence", 0),
            "reason": result.get("reason", "Não parece um erro real."),
            "error_id": error_id,
            "message": "Falso positivo. Erro ignorado.",
        }


def _generate_reproduction_steps(stack_trace: str, description: str) -> str:
    lines = (stack_trace or description or "").split("\n")
    relevant = [l for l in lines if l.strip() and not l.startswith(" ")][:3]
    if relevant:
        steps = []
        for i, line in enumerate(relevant[:3], 1):
            steps.append(f"{i}. Ação que leva ao erro: `{line[:100]}`")
        return "\n".join(steps)
    return "1. Acesse a página onde o erro ocorre\n2. Reproduza a ação descrita na denúncia"
