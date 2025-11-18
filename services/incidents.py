from dataclasses import dataclass
from typing import Optional
import datetime

from services.database import Database


@dataclass
class Incident:
    id: int
    title: str
    description: str
    status: str
    created_by: int
    created_at: datetime.datetime
    updated_at: datetime.datetime


class IncidentStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def create_incident(self, title: str, description: str, created_by: int) -> Incident:
        now = datetime.datetime.utcnow().isoformat()
        cur = self._db.execute(
            """
            INSERT INTO incidents (title, description, status, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (title, description, "open", created_by, now, now),
        )
        incident_id = int(cur.lastrowid)
        return self.get_incident(incident_id)  # type: ignore[return-value]

    def get_incident(self, incident_id: int) -> Optional[Incident]:
        row = self._db.query_one(
            "SELECT * FROM incidents WHERE id = ?",
            (incident_id,),
        )
        if row is None:
            return None
        created_at = datetime.datetime.fromisoformat(row["created_at"])
        updated_at = datetime.datetime.fromisoformat(row["updated_at"])
        return Incident(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            status=row["status"],
            created_by=row["created_by"],
            created_at=created_at,
            updated_at=updated_at,
        )

    def set_status(self, incident_id: int, status: str) -> Optional[Incident]:
        updated_at = datetime.datetime.utcnow().isoformat()
        self._db.execute(
            "UPDATE incidents SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, incident_id),
        )
        return self.get_incident(incident_id)

    def delete_incident(self, incident_id: int) -> bool:
        cur = self._db.execute(
            "DELETE FROM incidents WHERE id = ?",
            (incident_id,),
        )
        return cur.rowcount > 0
