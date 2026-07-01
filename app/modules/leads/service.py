"""Lead service layer — import, review, CRM, activity, bulk operations."""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import get_engine
from app.modules.leads.import_service import (
    ImportResult,
    parse_import_file,
)
from app.modules.leads.models import Activity, ImportBatch, Lead, LeadTagAssociation, Tag
from app.modules.leads.repository import (
    ActivityRepository,
    LeadRepository,
    TagRepository,
)
from app.modules.leads.safety import safe_tag_color


class LeadServiceError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Session helper
# ---------------------------------------------------------------------------


def _session(app: Flask) -> Session:
    session = Session(get_engine(app))
    session.expire_on_commit = False
    return session


# ---------------------------------------------------------------------------
# Import workflow — server-side batch mode (corrective pass)
# ---------------------------------------------------------------------------


def create_import_batch(
    app: Flask, *, tenant_id: str, filename: str, content: bytes
) -> ImportBatch:
    """Parse a file, store a preview batch with normalized rows, return it.

    The normalized rows are stored in ``rows_json`` so that the confirm
    step never needs the original file.  Expires after 1h.
    """
    result = parse_import_file(filename, content)
    errors_list = [r.errors for r in result.rows if r.errors]
    dup_count = sum(1 for r in result.rows if r.is_valid and _is_dup(app, tenant_id, r.email))

    # Build a list of safe, normalized row dicts for server-side confirm
    rows_data = [
        {
            "email": r.email,
            "first_name": r.first_name,
            "last_name": r.last_name,
            "company": r.company,
            "title": r.title,
            "phone": r.phone,
            "website": r.website,
            "industry": r.industry,
            "is_valid": r.is_valid,
        }
        for r in result.rows
    ]

    with _session(app) as session:
        now = datetime.now(UTC)
        batch = ImportBatch(
            tenant_id=tenant_id,
            filename=filename,
            status="preview",
            total_rows=result.total_rows,
            valid_rows=result.valid_rows,
            duplicate_rows=dup_count,
            invalid_rows=result.invalid_rows,
            errors_json=json.dumps(errors_list),
            unmapped_columns=", ".join(result.unmapped_columns),
            rows_json=json.dumps(rows_data),
            expires_at=now + timedelta(hours=1),
        )
        session.add(batch)
        session.commit()
        return batch


def confirm_import_batch(app: Flask, *, tenant_id: str, batch_id: str) -> int:
    """Confirm a preview batch — reads normalized rows from stored data.

    Browser submits only ``batch_id`` (and CSRF token).  The server
    reads the pre-validated, pre-normalized rows from ``rows_json``.
    No file content or client-supplied data is accepted.

    Idempotent: a ``completed`` batch returns 0.
    Transactional: all leads created atomically.
    """
    from app.modules.leads.repository import ActivityRepository, LeadRepository

    with _session(app) as session:
        batch = session.get(ImportBatch, batch_id)
        if batch is None or batch.tenant_id != tenant_id:
            raise LeadServiceError("Import batch not found")
        if batch.expires_at and batch.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
            raise LeadServiceError("Import batch has expired")
        if batch.status == "completed":
            return 0  # idempotent

        rows_data = json.loads(batch.rows_json or "[]")
        valid_rows = [r for r in rows_data if r.get("is_valid")]
        if not valid_rows:
            raise LeadServiceError("No valid rows to import")

        repo = LeadRepository(session)
        activity_repo = ActivityRepository(session)
        created_count = 0

        for row_data in valid_rows:
            email = row_data.get("email", "")
            with session.no_autoflush:
                existing = list(repo.list(tenant_id=tenant_id, search=email, limit=1))
            if existing:
                continue

            lead = Lead(
                tenant_id=tenant_id,
                email=email,
                first_name=row_data.get("first_name", ""),
                last_name=row_data.get("last_name", ""),
                title=row_data.get("title", ""),
                phone=row_data.get("phone", ""),
                website=row_data.get("website", ""),
                industry=row_data.get("industry", ""),
                source="import",
                status="pending_review",
                import_batch_id=batch_id,
            )
            repo.add(lead, tenant_id=tenant_id)
            session.flush()
            activity_repo.add(
                Activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    action="imported",
                    description=f"Imported from {batch.filename}",
                ),
                tenant_id=tenant_id,
            )
            session.flush()
            created_count += 1

        now = datetime.now(UTC)
        batch.status = "completed"
        batch.completed_at = now
        session.commit()

    return created_count


def _is_dup(app: Flask, tenant_id: str, email: str) -> bool:
    from app.modules.leads.repository import LeadRepository

    with _session(app) as session:
        repo = LeadRepository(session)
        with session.no_autoflush:
            return len(list(repo.list(tenant_id=tenant_id, search=email, limit=1))) > 0


# ---------------------------------------------------------------------------
# Original import preview / confirm (kept for backward compat)
# ---------------------------------------------------------------------------


def preview_import(app: Flask, *, filename: str, content: bytes) -> ImportResult:
    """Parse a file and return preview without writing to DB."""
    return parse_import_file(filename, content)


def confirm_import(
    app: Flask,
    *,
    tenant_id: str,
    filename: str,
    content: bytes,
    batch_id: str | None = None,
) -> int:
    """Confirm an import: parse + normalize + deduplicate + persist.

    Returns the number of new leads created.
    """
    result = parse_import_file(filename, content)
    if result.valid_rows == 0:
        raise LeadServiceError("No valid rows to import")

    batch_id = batch_id or uuid.uuid4().hex
    created_count = 0

    with _session(app) as session:
        repo = LeadRepository(session)
        activity_repo = ActivityRepository(session)

        for row in result.rows:
            if not row.is_valid:
                continue

            # Deduplicate by email within tenant
            with session.no_autoflush:
                existing = list(repo.list(tenant_id=tenant_id, search=row.email, limit=1))
            if existing:
                # Mark as duplicate if same email exists
                continue

            lead = Lead(
                tenant_id=tenant_id,
                email=row.email,
                first_name=row.first_name,
                last_name=row.last_name,
                title=row.title,
                phone=row.phone,
                website=row.website,
                industry=row.industry,
                source="import",
                status="pending_review",
                import_batch_id=batch_id,
            )
            repo.add(lead, tenant_id=tenant_id)
            session.flush()  # ensure lead.id is available for activity
            activity_repo.add(
                Activity(
                    tenant_id=tenant_id,
                    lead_id=lead.id,
                    action="imported",
                    description=f"Imported from {filename}",
                ),
                tenant_id=tenant_id,
            )
            session.flush()  # flush activity before next iteration's dedup
            created_count += 1

        session.commit()

    return created_count


BATCH_SIZE_MAX = 1000


# ---------------------------------------------------------------------------
# Lead review (V2-03-006)
# ---------------------------------------------------------------------------


def review_lead(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    decision: str,
    reviewed_by: str = "",
) -> Lead:
    """Accept or reject a lead during review."""
    if decision not in ("accepted", "rejected"):
        raise LeadServiceError(f"Invalid decision: {decision!r}")

    with _session(app) as session:
        repo = LeadRepository(session)
        lead = repo.get(lead_id, tenant_id=tenant_id)
        if lead is None:
            raise LeadServiceError("Lead not found")

        status_before = lead.status
        repo.update(lead, tenant_id=tenant_id, status=decision)
        lead.reviewed_at = datetime.now(UTC)
        lead.reviewed_by = reviewed_by

        _log_activity(
            session,
            tenant_id=tenant_id,
            lead_id=lead_id,
            action=decision,  # "accepted" or "rejected"
            description=f"Lead {decision} during review",
            old_value=status_before,
            new_value=decision,
            performed_by=reviewed_by,
        )
        session.commit()
        session.refresh(lead)
        return lead


# ---------------------------------------------------------------------------
# CRM stage, notes, tags, follow-up (V2-03-007)
# ---------------------------------------------------------------------------


VALID_STAGES = ("new", "contacted", "qualified", "proposal", "negotiation", "won", "lost")


def change_stage(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    stage: str,
    performed_by: str = "",
) -> Lead:
    if stage not in VALID_STAGES:
        raise LeadServiceError(f"Invalid stage: {stage!r}")

    with _session(app) as session:
        repo = LeadRepository(session)
        lead = repo.get(lead_id, tenant_id=tenant_id)
        if lead is None:
            raise LeadServiceError("Lead not found")

        old_stage = lead.stage
        repo.update(lead, tenant_id=tenant_id, stage=stage)
        _log_activity(
            session,
            tenant_id=tenant_id,
            lead_id=lead_id,
            action="stage_changed",
            description=f"Stage changed from {old_stage} to {stage}",
            old_value=old_stage,
            new_value=stage,
            performed_by=performed_by,
        )
        session.commit()
        return lead


def add_note(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    note: str,
    performed_by: str = "",
) -> Lead:
    if not note or not note.strip():
        raise LeadServiceError("Note cannot be empty")

    with _session(app) as session:
        repo = LeadRepository(session)
        lead = repo.get(lead_id, tenant_id=tenant_id)
        if lead is None:
            raise LeadServiceError("Lead not found")

        old_notes = lead.notes
        new_notes = (old_notes + "\n---\n" + note.strip()) if old_notes else note.strip()
        repo.update(lead, tenant_id=tenant_id, notes=new_notes)
        _log_activity(
            session,
            tenant_id=tenant_id,
            lead_id=lead_id,
            action="note_added",
            description=f"Note added: {note[:80]}",
            performed_by=performed_by,
        )
        session.commit()
        return lead


def set_follow_up(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    follow_up_at: datetime | None,
    performed_by: str = "",
) -> Lead:
    with _session(app) as session:
        repo = LeadRepository(session)
        lead = repo.get(lead_id, tenant_id=tenant_id)
        if lead is None:
            raise LeadServiceError("Lead not found")

        old_value = str(lead.follow_up_at) if lead.follow_up_at else ""
        new_value = str(follow_up_at) if follow_up_at else ""
        repo.update(lead, tenant_id=tenant_id, follow_up_at=follow_up_at)
        _log_activity(
            session,
            tenant_id=tenant_id,
            lead_id=lead_id,
            action="follow_up_set",
            description=f"Follow-up set to {new_value}" if new_value else "Follow-up cleared",
            old_value=old_value,
            new_value=new_value,
            performed_by=performed_by,
        )
        session.commit()
        return lead


def add_tag(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    tag_name: str,
    tag_color: str = "#246BFD",
    performed_by: str = "",
) -> Lead:
    with _session(app) as session:
        repo = LeadRepository(session)
        tag_repo = TagRepository(session)
        lead = repo.get(lead_id, tenant_id=tenant_id)
        if lead is None:
            raise LeadServiceError("Lead not found")

        # Find or create tag
        tags = tag_repo.list(tenant_id=tenant_id)
        tag = next((t for t in tags if t.name.lower() == tag_name.lower()), None)
        if tag is None:
            tag = Tag(
                tenant_id=tenant_id,
                name=tag_name.strip()[:80],
                color=safe_tag_color(tag_color),
            )
            tag_repo.add(tag, tenant_id=tenant_id)

        # Add association if not already present
        existing = session.scalar(
            select(LeadTagAssociation).where(
                LeadTagAssociation.lead_id == lead_id,
                LeadTagAssociation.tag_id == tag.id,
            )
        )
        if existing is None:
            session.add(LeadTagAssociation(lead_id=lead_id, tag_id=tag.id))
            _log_activity(
                session,
                tenant_id=tenant_id,
                lead_id=lead_id,
                action="tagged",
                description=f"Tagged with {tag.name}",
                new_value=tag.name,
                performed_by=performed_by,
            )
        session.commit()
        return lead


def remove_tag(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
    tag_id: str,
    performed_by: str = "",
) -> Lead:
    with _session(app) as session:
        repo = LeadRepository(session)
        lead = repo.get(lead_id, tenant_id=tenant_id)
        if lead is None:
            raise LeadServiceError("Lead not found")

        assoc = session.scalar(
            select(LeadTagAssociation).where(
                LeadTagAssociation.lead_id == lead_id,
                LeadTagAssociation.tag_id == tag_id,
            )
        )
        if assoc:
            session.delete(assoc)
            _log_activity(
                session,
                tenant_id=tenant_id,
                lead_id=lead_id,
                action="untagged",
                description="Tag removed",
                performed_by=performed_by,
            )
        session.commit()
        return lead


# ---------------------------------------------------------------------------
# Activity timeline (V2-03-008)
# ---------------------------------------------------------------------------


def get_timeline(
    app: Flask,
    *,
    tenant_id: str,
    lead_id: str,
) -> Sequence[Activity]:
    with _session(app) as session:
        repo = ActivityRepository(session)
        return repo.list_for_lead(lead_id, tenant_id=tenant_id)


# ---------------------------------------------------------------------------
# Bulk-safe operations (V2-03-010)
# ---------------------------------------------------------------------------


BULK_LIMIT = 100


def bulk_change_stage(
    app: Flask,
    *,
    tenant_id: str,
    lead_ids: list[str],
    stage: str,
    performed_by: str = "",
) -> int:
    if len(lead_ids) > BULK_LIMIT:
        raise LeadServiceError(f"Bulk operation limited to {BULK_LIMIT} leads")
    if stage not in VALID_STAGES:
        raise LeadServiceError(f"Invalid stage: {stage!r}")

    count = 0
    for lid in lead_ids:
        try:
            change_stage(
                app, tenant_id=tenant_id, lead_id=lid, stage=stage, performed_by=performed_by
            )
            count += 1
        except LeadServiceError:
            continue
    _log_bulk_activity(
        app,
        tenant_id,
        lead_ids,
        action="bulk_action",
        description=f"Bulk stage change to {stage}",
        performed_by=performed_by,
    )
    return count


def bulk_delete(
    app: Flask,
    *,
    tenant_id: str,
    lead_ids: list[str],
    performed_by: str = "",
) -> int:
    if len(lead_ids) > BULK_LIMIT:
        raise LeadServiceError(f"Bulk operation limited to {BULK_LIMIT} leads")

    with _session(app) as session:
        repo = LeadRepository(session)
        count = 0
        for lid in lead_ids:
            lead = repo.get(lid, tenant_id=tenant_id)
            if lead:
                repo.delete(lead, tenant_id=tenant_id)
                count += 1
        session.commit()
    _log_bulk_activity(
        app,
        tenant_id,
        lead_ids,
        action="bulk_action",
        description=f"Bulk delete of {count} leads",
        performed_by=performed_by,
    )
    return count


def _log_bulk_activity(
    app: Flask,
    tenant_id: str,
    lead_ids: list[str],
    *,
    action: str,
    description: str,
    performed_by: str,
) -> None:
    for lid in lead_ids[:5]:  # Log for first 5 only to avoid excess
        with _session(app) as session:
            _log_activity(
                session,
                tenant_id=tenant_id,
                lead_id=lid,
                action=action,
                description=description,
                performed_by=performed_by,
            )
            session.commit()


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------


def _log_activity(
    session: Session,
    *,
    tenant_id: str,
    lead_id: str,
    action: str,
    description: str = "",
    old_value: str = "",
    new_value: str = "",
    performed_by: str = "",
) -> None:
    session.add(
        Activity(
            tenant_id=tenant_id,
            lead_id=lead_id,
            action=action,
            description=description[:500],
            old_value=str(old_value)[:500],
            new_value=str(new_value)[:500],
            performed_by=performed_by,
        )
    )
