from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    telegram_bot_token: str
    allowed_telegram_user_id: int
    vercel_token: str
    vercel_project_id: str
    github_token: str
    repo_url: str = "https://github.com/Fardinando/ApexEnem.git"
    admin_user: str = "supreme"
    admin_pass: str
    database_path: str = "data/apexguardian.db"
    log_level: str = "INFO"
    session_secret: str = "change-me-to-a-random-string"

    # ─── Ollama (primário) ─────────────────────────────────
    ollama_host: str = ""
    ollama_model: str = "llama3.1"
    ollama_timeout: int = 10

    # ─── Fallback API (Groq, Together, etc) ───────────────
    ai_api_key: str = ""
    ai_api_base_url: str = "https://api.groq.com/openai/v1"
    ai_model: str = "llama3-8b-8192"

    @property
    def database_full_path(self) -> Path:
        return Path(self.database_path).resolve()

    @property
    def repo_name(self) -> str:
        return self.repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
