from typing import List, Optional

import datetime

from models.punishments import JailState, NoteRecord, PunishmentRecord
from services.database import Database


class HistoryStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def add_punishment(self, guild_id: int, record: PunishmentRecord) -> None:
        self._db.execute(
            """
            INSERT INTO punishments (
                guild_id, user_id, moderator_id, action, reason, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                record.user_id,
                record.moderator_id,
                record.action,
                record.reason,
                record.created_at.isoformat(),
                record.expires_at.isoformat() if record.expires_at else None,
            ),
        )

    def add_note(self, guild_id: int, record: NoteRecord) -> None:
        self._db.execute(
            """
            INSERT INTO notes (
                guild_id, user_id, moderator_id, text, created_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                record.user_id,
                record.moderator_id,
                record.text,
                record.created_at.isoformat(),
            ),
        )

    def _row_to_punishment(self, row) -> PunishmentRecord:
        created_at = datetime.datetime.fromisoformat(row["created_at"])
        expires_at = (
            datetime.datetime.fromisoformat(row["expires_at"])
            if row["expires_at"]
            else None
        )
        return PunishmentRecord(
            user_id=row["user_id"],
            moderator_id=row["moderator_id"],
            action=row["action"],
            reason=row["reason"],
            created_at=created_at,
            expires_at=expires_at,
        )

    def _row_to_note(self, row) -> NoteRecord:
        created_at = datetime.datetime.fromisoformat(row["created_at"])
        return NoteRecord(
            user_id=row["user_id"],
            moderator_id=row["moderator_id"],
            text=row["text"],
            created_at=created_at,
        )

    def get_punishments(self, guild_id: int) -> List[PunishmentRecord]:
        rows = self._db.query_all(
            "SELECT * FROM punishments WHERE guild_id = ? ORDER BY created_at ASC",
            (guild_id,),
        )
        return [self._row_to_punishment(row) for row in rows]

    def get_notes(self, guild_id: int) -> List[NoteRecord]:
        rows = self._db.query_all(
            "SELECT * FROM notes WHERE guild_id = ? ORDER BY created_at ASC",
            (guild_id,),
        )
        return [self._row_to_note(row) for row in rows]

    def get_punishments_for_user(self, guild_id: int, user_id: int) -> List[PunishmentRecord]:
        rows = self._db.query_all(
            """
            SELECT * FROM punishments
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (guild_id, user_id),
        )
        return [self._row_to_punishment(row) for row in rows]

    def get_notes_for_user(self, guild_id: int, user_id: int) -> List[NoteRecord]:
        rows = self._db.query_all(
            """
            SELECT * FROM notes
            WHERE guild_id = ? AND user_id = ?
            ORDER BY created_at ASC
            """,
            (guild_id, user_id),
        )
        return [self._row_to_note(row) for row in rows]

    def set_jail(self, state: JailState) -> None:
        self._db.execute(
            """
            INSERT INTO jails (
                guild_id, user_id, role_id, reason, created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                role_id = excluded.role_id,
                reason = excluded.reason,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (
                state.guild_id,
                state.user_id,
                state.role_id,
                state.reason,
                state.created_at.isoformat(),
                state.expires_at.isoformat() if state.expires_at else None,
            ),
        )

    def get_jail(self, guild_id: int, user_id: int) -> Optional[JailState]:
        row = self._db.query_one(
            "SELECT * FROM jails WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row is None:
            return None
        created_at = datetime.datetime.fromisoformat(row["created_at"])
        expires_at = (
            datetime.datetime.fromisoformat(row["expires_at"])
            if row["expires_at"]
            else None
        )
        return JailState(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            role_id=row["role_id"],
            reason=row["reason"],
            created_at=created_at,
            expires_at=expires_at,
        )

    def clear_jail(self, guild_id: int, user_id: int) -> Optional[JailState]:
        state = self.get_jail(guild_id, user_id)
        if state is None:
            return None
        self._db.execute(
            "DELETE FROM jails WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return state
