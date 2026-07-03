from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ReportIn(BaseModel):
    screenshot_base64: str
    description: str
    timestamp_frontend: float
    user_id_anon: str


class ErrorManualAdd(BaseModel):
    stack_trace: str
    url: Optional[str] = None
    context: Optional[str] = None


class ErrorStats(BaseModel):
    total: int
    active: int
    preview: int
    resolved: int
    fully_archived: int
    partially_archived: int
    cooldown: int
    ignored: int


class AdminCreate(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    role: str = Field(default="basic")


class AdminChangeRole(BaseModel):
    role: str


class AdminLogin(BaseModel):
    username: str
    password: str


class FixFeedback(BaseModel):
    action: str = Field(description="approved, rejected, refazer, reverte")
