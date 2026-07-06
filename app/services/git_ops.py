import os
import re
import tempfile
import shutil
from typing import Optional

from app.config import settings
from app.services.ai_client import generate_code_fix
from app.services.vercel_logs import deploy_preview, deploy_production

DESIGN_PROTECTED_PATTERNS = [
    r".*\.css$", r".*\.scss$", r".*\.less$", r".*\.sass$",
    r".*tailwind\.config\..*", r".*postcss\.config\..*",
    r".*theme\..*", r".*public/.*\.svg$", r".*public/.*\.png$",
    r".*public/.*\.jpg$", r".*public/.*\.ico$",
    r".*src/index\.css$", r".*src/styles/.*",
    r".*src/config/ads\.ts$",
]

DESIGN_CHANGE_PATTERNS = [
    r'className\s*[=]', r'className\s*\{',
    r'style\s*[=]\s*\{', r'style\s*[=]\s*"',
    r'<div(\s|>)', r'<section(\s|>)',
    r'<main(\s|>)', r'<header(\s|>)',
    r'<footer(\s|>)', r'<nav(\s|>)',
    r'tailwindcss', r'@apply',
    r'bg-[\w\[\]]+', r'text-[\w\[\]]+', r'p-[\d\w\[\]]+',
    r'm-[\d\w\[\]]+', r'gap-[\w\[\]]+', r'flex-[\w]+',
    r'grid-[\w-]+', r'rounded-[\w]+', r'shadow-[\w]+',
    r'font-[\w]+', r'border-[\w-]+', r'w-[\d\w\[\]]+',
    r'h-[\d\w\[\]]+',
]


def _is_design_file(file_path: str) -> bool:
    for pattern in DESIGN_PROTECTED_PATTERNS:
        if re.match(pattern, file_path):
            return True
    return False


def _has_design_changes(diff_text: str) -> list[str]:
    violations = []
    for pattern in DESIGN_CHANGE_PATTERNS:
        matches = re.findall(pattern, diff_text, re.IGNORECASE)
        if matches:
            violations.append(pattern)
    return violations


def _get_repo_url_with_token() -> str:
    token = settings.github_token
    repo_url = settings.repo_url
    if token and "github.com" in repo_url:
        return repo_url.replace("https://github.com/", f"https://{token}@github.com/")
    return repo_url


async def _apply_supabase_fix(plan: str, error: dict) -> dict | None:
    import re
    from app.services.supabase import supabase_update, supabase_insert, supabase_delete, supabase_query, supabase_available

    if not supabase_available():
        return None

    supabase_actions = re.findall(r'SUPABASE_ACTION:\s*(.*?)(?:\n|$)', plan, re.IGNORECASE)
    if not supabase_actions:
        return None

    results = []
    for action_str in supabase_actions:
        try:
            parts = {}
            for pair in action_str.split(","):
                kv = pair.strip().split("=", 1)
                if len(kv) == 2:
                    parts[kv[0].strip().lower()] = kv[1].strip()
            table = parts.get("table")
            action = parts.get("action", "").lower().strip()
            filter_col = parts.get("filter", "").strip()
            filter_val = parts.get("values", "").strip()
            values_str = parts.get("values", "{}").strip()

            if not table:
                continue

            values = {}
            if values_str.startswith("{") and values_str.endswith("}"):
                inner = values_str[1:-1]
                for item in inner.split(","):
                    kv = item.strip().split(":", 1)
                    if len(kv) == 2:
                        values[kv[0].strip()] = kv[1].strip()

            if action == "update" and filter_col:
                ok = supabase_update(table, values, (filter_col, filter_val))
                results.append({"table": table, "action": "update", "success": ok})
            elif action == "insert":
                ok = supabase_insert(table, values)
                results.append({"table": table, "action": "insert", "success": ok})
            elif action == "delete" and filter_col:
                ok = supabase_delete(table, (filter_col, filter_val))
                results.append({"table": table, "action": "delete", "success": ok})
        except Exception:
            continue

    if results:
        return {"applied": True, "actions": results}
    return None


async def apply_fix_and_deploy(error: dict, fix_data: dict) -> dict:
    plan = fix_data.get("plan", "")

    supabase_result = await _apply_supabase_fix(plan, error)
    if supabase_result and supabase_result.get("applied"):
        return {
            "success": True,
            "branch": "supabase_only",
            "preview_url": "N/A (Supabase)",
            "file_changed": "Supabase data",
            "supabase_action": supabase_result,
        }

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="apexguardian_")
        repo_path = os.path.join(temp_dir, settings.repo_name)
        branch_name = f"hotfix/{error['hash']}-{error['id']}"

        try:
            import git
            repo = git.Repo.clone_from(_get_repo_url_with_token(), repo_path)
        except Exception as e:
            return {"success": False, "error": f"Falha ao clonar repositório: {str(e)}"}

        try:
            origin = repo.remotes.origin
            origin.fetch()
            current_branch = repo.active_branch
            if current_branch.name != "main":
                repo.git.checkout("main")
            repo.git.pull("origin", "main")
            repo.git.checkout("-b", branch_name)
        except Exception as e:
            return {"success": False, "error": f"Falha ao criar branch: {str(e)}"}

        stack_trace = error.get("stack_trace") or ""
        description = error.get("description") or ""
        plan = fix_data.get("plan", "")

        search_terms = re.findall(r'(?:src/|api/|app/)?[\w/]+\.\w+', stack_trace)
        target_file = search_terms[0] if search_terms else None

        if not target_file:
            return {"success": False, "error": "Não foi possível identificar o arquivo alvo."}

        full_path = os.path.join(repo_path, target_file)
        if not os.path.exists(full_path):
            alt_paths = [
                os.path.join(repo_path, "src", target_file.lstrip("src/")),
                os.path.join(repo_path, "api", target_file.lstrip("api/")),
            ]
            for ap in alt_paths:
                if os.path.exists(ap):
                    full_path = ap
                    break
            else:
                return {"success": False, "error": f"Arquivo não encontrado: {target_file}"}

        rel_path = os.path.relpath(full_path, repo_path).replace("\\", "/")

        if _is_design_file(rel_path):
            return {"success": False, "error": f"DESIGN GUARD: {rel_path} é um arquivo de design protegido."}

        with open(full_path, "r", encoding="utf-8") as f:
            original_content = f.read()

        fixed_code = await generate_code_fix(rel_path, original_content, stack_trace, plan)
        if not fixed_code:
            return {"success": False, "error": "Falha ao gerar correção via IA."}

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(fixed_code)

        diff = repo.git.diff()
        violations = _has_design_changes(diff)
        if violations:
            repo.git.checkout("--", ".")
            from app.database import db
            with db() as conn:
                conn.execute(
                    "UPDATE error_signatures SET design_guard_rejections = design_guard_rejections + 1 WHERE id = ?",
                    (error["id"],)
                )
            max_rejections = 3
            with db() as conn:
                rej = conn.execute(
                    "SELECT design_guard_rejections FROM error_signatures WHERE id = ?",
                    (error["id"],)
                ).fetchone()[0]
            if rej >= max_rejections:
                return {"success": False, "error": f"DESIGN GUARD: Correção rejeitada {max_rejections}x. Design protegido."}
            return {"success": False,
                    "error": f"DESIGN GUARD: Tentativa de alterar design detectada ({len(violations)} padrões). Correção revertida."}

        try:
            repo.index.add([rel_path])
            repo.index.commit(f"fix: correção automática do erro {error['hash']}")
            origin.push(branch_name)
        except Exception as e:
            return {"success": False, "error": f"Falha no git push: {str(e)}"}

        preview_url = ""
        try:
            url = await deploy_preview(branch_name)
            if url:
                preview_url = f"https://{url}"
        except Exception:
            preview_url = "URL indisponível"

        return {
            "success": True,
            "branch": branch_name,
            "preview_url": preview_url or "N/A",
            "file_changed": rel_path,
        }

    except Exception as e:
        return {"success": False, "error": f"Erro inesperado: {str(e)}"}
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass


async def merge_to_main(branch_name: str) -> dict:
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="apexguardian_merge_")
        repo_path = os.path.join(temp_dir, settings.repo_name)

        import git
        repo = git.Repo.clone_from(_get_repo_url_with_token(), repo_path)
        origin = repo.remotes.origin
        origin.fetch()

        repo.git.checkout("main")
        repo.git.pull("origin", "main")
        repo.git.merge(branch_name, no_ff=True)

        try:
            repo.git.push("origin", "main")
        except Exception as e:
            return {"success": False, "error": f"Falha no push para main: {str(e)}"}

        try:
            repo.git.push("origin", "--delete", branch_name)
        except Exception:
            pass

        prod_success = False
        try:
            prod_success = await deploy_production()
        except Exception:
            pass

        return {
            "success": True,
            "message": f"Branch {branch_name} mergeada em main com sucesso.",
            "production_deploy": prod_success,
        }
    except Exception as e:
        return {"success": False, "error": f"Falha no merge: {str(e)}"}
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass


def rollback_fix(branch_name: str) -> dict:
    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp(prefix="apexguardian_rollback_")
        repo_path = os.path.join(temp_dir, settings.repo_name)

        import git
        repo = git.Repo.clone_from(_get_repo_url_with_token(), repo_path)
        origin = repo.remotes.origin

        local_branch = f"temp_{branch_name.replace('/', '_')}"
        try:
            repo.git.fetch("origin", branch_name)
            repo.git.checkout("-b", local_branch, f"origin/{branch_name}")
        except Exception:
            pass

        repo.git.checkout("main")
        try:
            repo.git.push("origin", "--delete", branch_name)
        except Exception:
            pass

        return {"success": True, "message": f"Branch {branch_name} deletada."}
    except Exception as e:
        return {"success": False, "error": f"Falha no rollback: {str(e)}"}
    finally:
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass
