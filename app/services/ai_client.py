import json
from typing import Optional
from openai import OpenAI, APIError, APITimeoutError
from httpx import Timeout

from app.config import settings

_ollama_client: Optional[OpenAI] = None
_fallback_client: Optional[OpenAI] = None
_ollama_available: Optional[bool] = None


def _get_ollama_client() -> Optional[OpenAI]:
    global _ollama_client
    if _ollama_client is None and settings.ollama_host:
        try:
            _ollama_client = OpenAI(
                base_url=settings.ollama_host.rstrip("/") + "/v1",
                api_key="ollama",
                timeout=Timeout(settings.ollama_timeout),
            )
        except Exception:
            return None
    return _ollama_client


def _get_fallback_client() -> OpenAI:
    global _fallback_client
    if _fallback_client is None:
        _fallback_client = OpenAI(
            base_url=settings.ai_api_base_url,
            api_key=settings.ai_api_key or "no-key-needed",
        )
    return _fallback_client


async def ping_ollama() -> bool:
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available
    if not settings.ollama_host:
        _ollama_available = False
        return False
    try:
        client = _get_ollama_client()
        if client:
            client.models.list()
            _ollama_available = True
            return True
        _ollama_available = False
        return False
    except Exception:
        _ollama_available = False
        return False


SYSTEM_DIAGNOSE = """You are a senior Next.js/React/Vercel/Supabase expert debugging errors.
Analyze the error, explain root cause and user impact. Be concise and technical.
Consider both code bugs AND Supabase data issues as possible root causes."""

SYSTEM_PLAN = """Create a step-by-step fix plan for this error.
Be specific about files to change and what to modify.
If the fix requires Supabase data changes, specify: SUPABASE_ACTION: table=X, action=update, filter=Y, values=Z
IMPORTANT: Do NOT suggest changes to CSS, styles, design, or layout."""

SYSTEM_CODE_FIX = """Fix the bug in this code.
🚫 RESTRIÇÃO ABSOLUTA: NÃO modifique CSS, classes Tailwind, estilos, layout, design visual.
Modifique APENAS a lógica do bug, especificamente a linha do erro.
Retorne APENAS o código corrigido, nada mais."""

SYSTEM_INVESTIGATE = """You are investigating whether this error report is a legitimate bug or a false positive.
Analyze the stack trace and description. Consider both code and Supabase data issues.
Respond in JSON format:
{"is_real_bug": true/false, "confidence": 0-100, "reason": "brief explanation"}"""


def _call(messages: list[dict], max_tokens: int = 4096, temperature: float = 0.2,
          model: Optional[str] = None) -> Optional[str]:
    global _ollama_available

    # Try Ollama first if available
    if _ollama_available is not False and settings.ollama_host:
        try:
            client = _get_ollama_client()
            if client:
                resp = client.chat.completions.create(
                    model=model or settings.ollama_model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout=settings.ollama_timeout,
                )
                return resp.choices[0].message.content.strip()
        except (APIError, APITimeoutError, Exception):
            _ollama_available = False

    # Fallback to configured AI API
    if not settings.ai_api_key:
        return None
    try:
        client = _get_fallback_client()
        resp = client.chat.completions.create(
            model=model or settings.ai_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return None


async def diagnose_error(stack_trace: str, description: str, search_results: str = "") -> str:
    prompt = f"""Stack Trace:
{stack_trace[:3000]}

Description:
{description[:1000]}

Web Search Results:
{search_results[:2000]}

Explain root cause and user impact:"""
    result = _call([
        {"role": "system", "content": SYSTEM_DIAGNOSE},
        {"role": "user", "content": prompt},
    ])
    return result or "Não foi possível gerar diagnóstico automaticamente."


async def generate_fix_plan(stack_trace: str, description: str, diagnosis: str,
                            search_results: str = "") -> str:
    prompt = f"""Stack Trace:
{stack_trace[:2000]}

Description:
{description[:1000]}

Diagnosis:
{diagnosis}

Web Search Results:
{search_results[:2000]}

Create a numbered step-by-step fix plan.
If the root cause is in Supabase data, include SUPABASE_ACTION: table=X, action=update, filter=Y, values=Z
in the relevant step. Otherwise specify which code file to change and how."""
    result = _call([
        {"role": "system", "content": SYSTEM_PLAN},
        {"role": "user", "content": prompt},
    ])
    return result or "Não foi possível gerar plano automaticamente."


async def generate_code_fix(file_path: str, file_content: str, stack_trace: str, plan: str) -> Optional[str]:
    prompt = f"""File: {file_path}

File Content:
```python
{file_content[:4000]}
```

Error:
{stack_trace[:2000]}

Fix Plan:
{plan[:2000]}

Return ONLY the corrected file content with the bug fixed. Do not change CSS, styles, or design."""

    result = _call([
        {"role": "system", "content": SYSTEM_CODE_FIX},
        {"role": "user", "content": prompt},
    ], max_tokens=6144)

    if result:
        if "```" in result:
            parts = result.split("```")
            if len(parts) >= 2:
                candidate = parts[1]
                if "\n" in candidate:
                    candidate = candidate[candidate.index("\n") + 1:]
                result = candidate
        return result.strip()
    return None


async def investigate_error(stack_trace: str, description: str, search_results: str = "") -> dict:
    prompt = f"""Stack Trace:
{stack_trace[:2000]}

Description:
{description[:1000]}

Web Search Results:
{search_results[:2000]}

Is this a real bug or false positive? Respond in JSON."""
    result = _call([
        {"role": "system", "content": SYSTEM_INVESTIGATE},
        {"role": "user", "content": prompt},
    ], max_tokens=1024, temperature=0.1)

    if result:
        try:
            cleaned = result.strip()
            if "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            pass
    return {"is_real_bug": True, "confidence": 50, "reason": "Fallback: treating as real bug"}


async def check_ai_health() -> dict:
    ollama_ok = False
    ollama_detail = ""
    if settings.ollama_host:
        try:
            client = _get_ollama_client()
            if client:
                client.models.list()
                ollama_ok = True
        except Exception as e:
            ollama_detail = str(e)

    fallback_ok = False
    fallback_detail = ""
    if settings.ai_api_key:
        try:
            client = _get_fallback_client()
            client.models.list()
            fallback_ok = True
        except Exception as e:
            fallback_detail = str(e)

    return {
        "ollama": {
            "status": "ok" if ollama_ok else "offline" if settings.ollama_host else "not configured",
            "host": settings.ollama_host or "",
            "model": settings.ollama_model,
            "detail": ollama_detail,
        },
        "fallback": {
            "status": "ok" if fallback_ok else "offline" if settings.ai_api_key else "not configured",
            "provider": settings.ai_api_base_url,
            "model": settings.ai_model,
            "detail": fallback_detail,
        },
        "active_provider": "ollama" if ollama_ok else "fallback" if fallback_ok else "none",
    }
