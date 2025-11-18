from typing import Dict, Optional

from services.database import Database


class AutoRoleStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set_role(self, guild_id: int, trigger: str, role_id: int) -> None:
        trigger = trigger.lower().strip()
        if not trigger:
            return
        self._db.execute(
            """
            INSERT INTO auto_roles (guild_id, trigger, role_id)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, trigger) DO UPDATE SET role_id = excluded.role_id
            """,
            (guild_id, trigger, role_id),
        )

    def get_role(self, guild_id: int, trigger: str) -> Optional[int]:
        trigger = trigger.lower().strip()
        row = self._db.query_one(
            "SELECT role_id FROM auto_roles WHERE guild_id = ? AND trigger = ?",
            (guild_id, trigger),
        )
        if row is None:
            return None
        return int(row["role_id"])

    def all_triggers(self, guild_id: int) -> Dict[str, int]:
        rows = self._db.query_all(
            "SELECT trigger, role_id FROM auto_roles WHERE guild_id = ?",
            (guild_id,),
        )
        return {str(row["trigger"]): int(row["role_id"]) for row in rows}

    def clear_trigger(self, guild_id: int, trigger: str) -> None:
        trigger = trigger.lower().strip()
        if not trigger:
            return
        self._db.execute(
            "DELETE FROM auto_roles WHERE guild_id = ? AND trigger = ?",
            (guild_id, trigger),
        )
