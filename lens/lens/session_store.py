"""
session_store.py — Lens session persistence
CCA Domain 5: Context management + reliability

SQLite-backed session state. Checkpoints after every step.
Any interruption loses at most one step — never starts from zero.
"""

import json
from datetime import datetime
from uuid import uuid4

import sqlite_utils
import structlog

log = structlog.get_logger(__name__)


class SessionStore:
    """
    Persists research sessions to SQLite.

    On interruption, the coordinator calls get_session()
    and resumes from current_step — skipping all completed steps.
    """

    def __init__(self, db_path: str = "./data/lens.db"):
        self.db = sqlite_utils.Database(db_path)
        self._init_tables()

    def _init_tables(self) -> None:
        """Create tables if they don't exist."""

        # Projects
        if "projects" not in self.db.table_names():
            self.db["projects"].create({
                "id": str,
                "name": str,
                "description": str,
                "status": str,
                "created_at": str,
                "updated_at": str,
            }, pk="id")

        # Sessions — with checkpoint_data for resumption
        if "sessions" not in self.db.table_names():
            self.db["sessions"].create({
                "id": str,
                "project_id": str,
                "goal": str,
                "status": str,            # running|paused|complete|failed
                "current_step": str,      # last completed step
                "checkpoint_data": str,   # JSON blob
                "error": str,             # populated on failure
                "created_at": str,
                "updated_at": str,
            }, pk="id", foreign_keys=[
                ("project_id", "projects", "id")
            ])

        # Findings — provenance-tagged research findings
        if "findings" not in self.db.table_names():
            self.db["findings"].create({
                "id": str,
                "project_id": str,
                "session_id": str,
                "source_agent": str,
                "claim": str,
                "confidence": str,
                "source_url": str,        # nullable
                "contradicts_id": str,    # nullable
                "created_at": str,
            }, pk="id")

        # Reports — final outputs
        if "reports" not in self.db.table_names():
            self.db["reports"].create({
                "id": str,
                "project_id": str,
                "session_id": str,
                "title": str,
                "content_md": str,
                "finding_ids": str,       # JSON array
                "share_token": str,       # nullable
                "created_at": str,
            }, pk="id")

        log.info("session_store_initialised")

    async def create_project(self, name: str, description: str) -> dict:
        """Create a new research project."""
        project = {
            "id": str(uuid4()),
            "name": name,
            "description": description,
            "status": "active",
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.db["projects"].insert(project)
        log.info("project_created", project_id=project["id"], name=name)
        return project

    async def create_session(self, project_id: str, goal: str) -> "Session":
        """Create a new research session."""
        session_data = {
            "id": str(uuid4()),
            "project_id": project_id,
            "goal": goal,
            "status": "running",
            "current_step": "start",
            "checkpoint_data": "{}",
            "error": None,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        self.db["sessions"].insert(session_data)
        log.info("session_created", session_id=session_data["id"])
        return Session.from_dict(session_data)

    async def get_session(self, session_id: str) -> "Session | None":
        """Retrieve a session for resumption."""
        try:
            row = self.db["sessions"].get(session_id)
            return Session.from_dict(row)
        except Exception:
            return None

    async def checkpoint(
        self, session_id: str, step: str, data: dict
    ) -> None:
        """
        Save session state after a completed step.
        Merges new data with existing checkpoint data.
        """
        try:
            existing = self.db["sessions"].get(session_id)
            existing_data = json.loads(existing.get("checkpoint_data", "{}"))
            existing_data.update(data)

            self.db["sessions"].update(session_id, {
                "current_step": step,
                "checkpoint_data": json.dumps(existing_data),
                "updated_at": datetime.utcnow().isoformat(),
            })
            log.info("checkpoint_saved", session_id=session_id, step=step)
        except Exception as e:
            log.error("checkpoint_failed", session_id=session_id, error=str(e))
            raise

    async def complete_session(self, session_id: str) -> None:
        """Mark a session as complete."""
        self.db["sessions"].update(session_id, {
            "status": "complete",
            "current_step": "complete",
            "updated_at": datetime.utcnow().isoformat(),
        })
        log.info("session_completed", session_id=session_id)

    async def fail_session(self, session_id: str, error: str) -> None:
        """Mark a session as failed with the error message."""
        self.db["sessions"].update(session_id, {
            "status": "failed",
            "error": error,
            "updated_at": datetime.utcnow().isoformat(),
        })
        log.error("session_failed", session_id=session_id, error=error)

    async def save_finding(
        self,
        project_id: str,
        session_id: str,
        source_agent: str,
        claim: str,
        confidence: str,
        source_url: str | None = None,
        contradicts_id: str | None = None,
    ) -> str:
        """Save a research finding. Returns the finding ID."""
        finding = {
            "id": str(uuid4()),
            "project_id": project_id,
            "session_id": session_id,
            "source_agent": source_agent,
            "claim": claim,
            "confidence": confidence,
            "source_url": source_url,
            "contradicts_id": contradicts_id,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.db["findings"].insert(finding)
        return finding["id"]

    async def save_report(
        self,
        project_id: str,
        session_id: str,
        title: str,
        content_md: str,
        finding_ids: list[str],
    ) -> str:
        """Save the final report. Returns the report ID."""
        report = {
            "id": str(uuid4()),
            "project_id": project_id,
            "session_id": session_id,
            "title": title,
            "content_md": content_md,
            "finding_ids": json.dumps(finding_ids),
            "share_token": None,
            "created_at": datetime.utcnow().isoformat(),
        }
        self.db["reports"].insert(report)
        log.info("report_saved", report_id=report["id"])
        return report["id"]

    async def get_project_sessions(self, project_id: str) -> list[dict]:
        """Get all sessions for a project, most recent first."""
        rows = list(self.db["sessions"].rows_where(
            "project_id = ?",
            [project_id],
            order_by="created_at desc",
        ))
        return rows

    async def get_project_findings(
        self, project_id: str, limit: int = 50
    ) -> list[dict]:
        """Get findings for a project for cross-session research."""
        rows = list(self.db["findings"].rows_where(
            "project_id = ?",
            [project_id],
            order_by="created_at desc",
            limit=limit,
        ))
        return rows


class Session:
    """In-memory session object — loaded from SQLite."""

    def __init__(
        self,
        id: str,
        project_id: str,
        goal: str,
        status: str,
        current_step: str,
        checkpoint_data: dict,
    ):
        self.id = id
        self.project_id = project_id
        self.goal = goal
        self.status = status
        self.current_step = current_step
        self.checkpoint_data = checkpoint_data

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        return cls(
            id=data["id"],
            project_id=data["project_id"],
            goal=data["goal"],
            status=data["status"],
            current_step=data.get("current_step", "start"),
            checkpoint_data=json.loads(data.get("checkpoint_data", "{}")),
        )
