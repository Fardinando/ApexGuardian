import json
import httpx
from typing import Optional

from app.config import settings


async def _call_ollama(prompt: str, system: str = "", max_tokens: int = 4096) -> Optional[str]:
    url = f"{settings.ollama_host.rstrip('/')}/api/generate"
    payload = {
        "model": settings.ollama_model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "num_predict": max_tokens,
            "temperature": 0.2,
        },
    }
    async with httpx.AsyncClient(timeout=180) as client:
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("response", "").strip()
        except Exception:
            return None
    return None


SYSTEM_DIAGNOSE = """You are a senior Next.js/React/Vercel expert debugging errors.
Analyze the error, explain root cause and user impact. Be concise and technical."""

SYSTEM_PLAN = """Create a step-by-step fix plan for this error.
Be specific about files to change and what to modify.
IMPORTANT: Do NOT suggest changes to CSS, styles, design, or layout."""

SYSTEM_CODE_FIX = """Fix the bug in this code. 
🚫 RESTRIÇÃO ABSOLUTA: NÃO modifique CSS, classes Tailwind, estilos, layout, design visual.
Modifique APENAS a lógica do bug, especificamente a linha do erro.
Retorne APENAS o código corrigido, nada mais."""

SYSTEM_INVESTIGATE = """You are investigating whether this error report is a legitimate bug or a false positive.
Analyze the stack trace and description.
Respond in JSON format:
{"is_real_bug": true/false, "confidence": 0-100, "reason": "brief explanation"}"""


async def diagnose_error(stack_trace: str, description: str, search_results: str = "") -> str:
    prompt = f"""Stack Trace:
{stack_trace[:3000]}

Description:
{description[:1000]}

Web Search Results:
{search_results[:2000]}

Explain root cause and user impact:"""
    return await _call_ollama(prompt, SYSTEM_DIAGNOSE) or "Não foi possível gerar diagnóstico automaticamente."


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

Create a numbered step-by-step fix plan:"""
    return await _call_ollama(prompt, SYSTEM_PLAN) or "Não foi possível gerar plano automaticamente."


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

    result = await _call_ollama(prompt, SYSTEM_CODE_FIX, max_tokens=6144)
    if result:
        result = result.strip()
        if "```" in result:
            result = result.split("```")[1]
            if "\n" in result:
                result = result[result.index("\n") + 1:]
    return result


async def investigate_error(stack_trace: str, description: str, search_results: str = "") -> dict:
    prompt = f"""Stack Trace:
{stack_trace[:2000]}

Description:
{description[:1000]}

Web Search Results:
{search_results[:2000]}

Is this a real bug or false positive? Respond in JSON."""
    result = await _call_ollama(prompt, SYSTEM_INVESTIGATE, max_tokens=1024)
    if result:
        try:
            cleaned = result.strip()
            if "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]
            return json.loads(cleaned)
        except (json.JSONDecodeError, IndexError):
            pass
    return {"is_real_bug": True, "confidence": 50, "reason": "Fallback: treating as real bug"}


async def check_ollama_health() -> dict:
    url = f"{settings.ollama_host.rstrip('/')}/api/tags"
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                has_model = any(
                    settings.ollama_model in m.get("name", "") for m in models
                )
                return {"status": "ok", "model_loaded": has_model}
            return {"status": "error", "detail": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"status": "error", "detail": str(e)}
