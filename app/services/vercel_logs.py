import httpx
from datetime import datetime
from typing import Optional

from app.config import settings

VERCEL_API = "https://api.vercel.com"


async def _get_headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.vercel_token}",
        "Content-Type": "application/json",
    }


async def fetch_recent_deployments(limit: int = 5) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{VERCEL_API}/v6/deployments",
            headers=await _get_headers(),
            params={"limit": limit, "projectId": settings.vercel_project_id},
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("deployments", [])
        return []


async def fetch_deployment_logs(deployment_id: str, limit: int = 100) -> list[dict]:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{VERCEL_API}/v1/deployments/{deployment_id}/events",
            headers=await _get_headers(),
            params={"limit": limit},
        )
        if resp.status_code == 200:
            return resp.json()
        return []


async def fetch_logs_in_window(start_timestamp: float, end_timestamp: float) -> list[dict]:
    errors = []
    try:
        deployments = await fetch_recent_deployments(10)

        for dep in deployments:
            dep_created = _parse_vercel_timestamp(dep.get("createdAt"))
            if dep_created is None:
                continue
            dep_ts = dep_created.timestamp()

            if dep_ts > end_timestamp:
                continue
            if dep_ts < start_timestamp - 86400:
                continue

            dep_id = dep.get("uid") or dep.get("id")
            if not dep_id:
                continue

            logs = await fetch_deployment_logs(dep_id)
            for log in logs:
                log_ts = _parse_log_timestamp(log)
                if log_ts is not None and start_timestamp <= log_ts <= end_timestamp:
                    if log.get("type") == "error" or log.get("level") == "error":
                        errors.append({
                            "deploymentId": dep_id,
                            "timestamp": datetime.fromtimestamp(log_ts).isoformat(),
                            "text": log.get("text") or log.get("message", ""),
                            "stack": log.get("stack", ""),
                            "type": "error",
                        })
    except Exception:
        pass

    return errors


async def deploy_preview(branch_name: str) -> Optional[str]:
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VERCEL_API}/v13/deployments",
            headers=await _get_headers(),
            json={
                "name": settings.repo_name,
                "project": settings.vercel_project_id,
                "target": "preview",
                "gitSource": {
                    "type": "github",
                    "ref": branch_name,
                    "repoId": settings.repo_url,
                },
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("url")
        return None


async def deploy_production():
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{VERCEL_API}/v13/deployments",
            headers=await _get_headers(),
            json={
                "name": settings.repo_name,
                "project": settings.vercel_project_id,
                "target": "production",
                "gitSource": {
                    "type": "github",
                    "ref": "main",
                    "repoId": settings.repo_url,
                },
            },
        )
        return resp.status_code == 200


async def check_api_health() -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                f"{VERCEL_API}/v9/projects/{settings.vercel_project_id}",
                headers=await _get_headers(),
            )
            return {"status": "ok" if resp.status_code == 200 else "error", "code": resp.status_code}
        except Exception as e:
            return {"status": "error", "detail": str(e)}


def _parse_vercel_timestamp(ts) -> Optional[datetime]:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(ts / 1000)
    except (TypeError, OSError):
        pass
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _parse_log_timestamp(log: dict) -> Optional[float]:
    ts = log.get("created") or log.get("timestamp")
    if ts is None:
        return None
    try:
        return float(ts) / 1000
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return dt.timestamp()
    except (ValueError, TypeError):
        return None
