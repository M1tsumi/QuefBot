from dataclasses import dataclass
from typing import Optional
import datetime


@dataclass
class PunishmentRecord:
    user_id: int
    moderator_id: int
    action: str
    reason: Optional[str]
    created_at: datetime.datetime
    expires_at: Optional[datetime.datetime]


@dataclass
class NoteRecord:
    user_id: int
    moderator_id: int
    text: str
    created_at: datetime.datetime


@dataclass
class JailState:
    guild_id: int
    user_id: int
    role_id: int
    reason: Optional[str]
    created_at: datetime.datetime
    expires_at: Optional[datetime.datetime]
