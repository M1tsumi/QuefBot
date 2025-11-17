from typing import Dict

from services.database import Database


class ReactionRoleStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set_mapping(self, guild_id: int, message_id: int, emoji: str, role_id: int) -> None:
        self._db.execute(
            """
            INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, message_id, emoji) DO UPDATE SET role_id = excluded.role_id
            """,
            (guild_id, message_id, emoji, role_id),
        )

    def clear_message(self, guild_id: int, message_id: int) -> None:
        self._db.execute(
            "DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )

    def get_mappings_for_message(self, guild_id: int, message_id: int) -> Dict[str, int]:
        rows = self._db.query_all(
            "SELECT emoji, role_id FROM reaction_roles WHERE guild_id = ? AND message_id = ?",
            (guild_id, message_id),
        )
        return {str(row["emoji"]): int(row["role_id"]) for row in rows}
