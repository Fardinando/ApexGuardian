from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    telegram_bot_token: str
    allowed_telegram_user_id: int
    vercel_token: str
    vercel_project_id: str
    github_token: str
    repo_url: str = "https://github.com/Fardinando/ApexEnem.git"
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"
    admin_user: str = "admin"
    admin_pass: str
    database_path: str = "data/apexguardian.db"
    log_level: str = "INFO"
    session_secret: str = "change-me-to-a-random-string"

    @property
    def database_full_path(self) -> Path:
        return Path(self.database_path).resolve()

    @property
    def repo_name(self) -> str:
        return self.repo_url.rstrip("/").split("/")[-1].replace(".git", "")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
