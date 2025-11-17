from dataclasses import dataclass
from typing import Optional
import datetime

from services.database import Database


@dataclass
class Ticket:
    id: int
    priority: str
    status: str
    reporter_id: Optional[int]
    escalated_by: Optional[int]
    updated_at: datetime.datetime


class TicketService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def set_category(self, guild_id: int, category_id: int) -> None:
        self._db.execute(
            """
            INSERT INTO ticket_config (guild_id, category_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET category_id = excluded.category_id
            """,
            (guild_id, category_id),
        )

    def get_category(self, guild_id: int) -> Optional[int]:
        row = self._db.query_one(
            "SELECT category_id FROM ticket_config WHERE guild_id = ?",
            (guild_id,),
        )
        if row is None:
            return None
        return int(row["category_id"])

    def set_transcript_channel(self, guild_id: int, channel_id: int) -> None:
        self._db.execute(
            """
            INSERT INTO ticket_transcripts (guild_id, channel_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            """,
            (guild_id, channel_id),
        )

    def get_transcript_channel(self, guild_id: int) -> Optional[int]:
        row = self._db.query_one(
            "SELECT channel_id FROM ticket_transcripts WHERE guild_id = ?",
            (guild_id,),
        )
        if row is None:
            return None
        return int(row["channel_id"])

    def create_ticket(self, reporter_id: int, priority: str = "medium") -> Ticket:
        priority = priority.lower()
        if priority not in {"low", "medium", "high", "critical"}:
            priority = "medium"
        now = datetime.datetime.utcnow().isoformat()
        row = self._db.query_one("SELECT MAX(id) AS max_id FROM tickets", ())
        next_id = 1
        if row is not None and row["max_id"] is not None:
            next_id = int(row["max_id"]) + 1
        self._db.execute(
            """
            INSERT INTO tickets (id, priority, status, reporter_id, escalated_by, updated_at)
            VALUES (?, ?, 'open', ?, NULL, ?)
            """,
            (next_id, priority, reporter_id, now),
        )
        ticket = self.get_ticket(next_id)
        assert ticket is not None
        return ticket

    def link_channel(self, ticket_id: int, guild_id: int, channel_id: int) -> None:
        self._db.execute(
            """
            INSERT INTO ticket_channels (ticket_id, guild_id, channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT(ticket_id) DO UPDATE SET guild_id = excluded.guild_id, channel_id = excluded.channel_id
            """,
            (ticket_id, guild_id, channel_id),
        )

    def get_channel_for_ticket(self, ticket_id: int) -> Optional[int]:
        row = self._db.query_one(
            "SELECT channel_id FROM ticket_channels WHERE ticket_id = ?",
            (ticket_id,),
        )
        if row is None:
            return None
        return int(row["channel_id"])

    def get_ticket_by_channel(self, guild_id: int, channel_id: int) -> Optional[Ticket]:
        row = self._db.query_one(
            """
            SELECT t.*
            FROM tickets t
            JOIN ticket_channels c ON t.id = c.ticket_id
            WHERE c.guild_id = ? AND c.channel_id = ?
            """,
            (guild_id, channel_id),
        )
        if row is None:
            return None
        updated_at = datetime.datetime.fromisoformat(row["updated_at"])
        return Ticket(
            id=row["id"],
            priority=row["priority"],
            status=row["status"],
            reporter_id=row["reporter_id"],
            escalated_by=row["escalated_by"],
            updated_at=updated_at,
        )

    def get_open_ticket_for_user(self, guild_id: int, user_id: int) -> Optional[Ticket]:
        row = self._db.query_one(
            """
            SELECT t.*
            FROM tickets t
            JOIN ticket_channels c ON t.id = c.ticket_id
            WHERE c.guild_id = ? AND t.reporter_id = ? AND t.status = 'open'
            ORDER BY t.updated_at DESC
            LIMIT 1
            """,
            (guild_id, user_id),
        )
        if row is None:
            return None
        updated_at = datetime.datetime.fromisoformat(row["updated_at"])
        return Ticket(
            id=row["id"],
            priority=row["priority"],
            status=row["status"],
            reporter_id=row["reporter_id"],
            escalated_by=row["escalated_by"],
            updated_at=updated_at,
        )

    def escalate_ticket(self, ticket_id: int, priority: str, escalated_by: int) -> Ticket:
        priority = priority.lower()
        if priority not in {"low", "medium", "high", "critical"}:
            priority = "medium"
        now = datetime.datetime.utcnow().isoformat()
        existing = self._db.query_one(
            "SELECT id FROM tickets WHERE id = ?",
            (ticket_id,),
        )
        if existing is None:
            self._db.execute(
                """
                INSERT INTO tickets (id, priority, status, reporter_id, escalated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ticket_id, priority, "escalated", None, escalated_by, now),
            )
        else:
            self._db.execute(
                """
                UPDATE tickets
                SET priority = ?, status = 'escalated', escalated_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (priority, escalated_by, now, ticket_id),
            )
        ticket = self.get_ticket(ticket_id)
        assert ticket is not None
        return ticket

    def close_ticket(self, ticket_id: int) -> Optional[Ticket]:
        now = datetime.datetime.utcnow().isoformat()
        self._db.execute(
            "UPDATE tickets SET status = 'closed', updated_at = ? WHERE id = ?",
            (now, ticket_id),
        )
        return self.get_ticket(ticket_id)

    def get_ticket(self, ticket_id: int) -> Optional[Ticket]:
        row = self._db.query_one(
            "SELECT * FROM tickets WHERE id = ?",
            (ticket_id,),
        )
        if row is None:
            return None
        updated_at = datetime.datetime.fromisoformat(row["updated_at"])
        return Ticket(
            id=row["id"],
            priority=row["priority"],
            status=row["status"],
            reporter_id=row["reporter_id"],
            escalated_by=row["escalated_by"],
            updated_at=updated_at,
        )
