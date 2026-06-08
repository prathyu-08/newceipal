"""
core/utils.py
-------------
Generic utility functions shared across the application.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Optional


def _field_variants(key: str) -> set[str]:
    """Generate normalized variants of a field name for flexible matching."""
    text = key.strip().lower()
    compact = "".join(ch for ch in text if ch.isalnum())
    snake = "_".join(part for part in text.replace("/", " ").split() if part)
    return {text, compact, snake}


def _first_present(source: dict, keys: tuple[str, ...]) -> Any:
    """Find first non-empty value from a list of possible keys."""
    normalized: dict[str, Any] = {}
    for raw_key, value in source.items():
        for variant in _field_variants(str(raw_key)):
            normalized.setdefault(variant, value)

    for key in keys:
        for variant in _field_variants(key):
            value = normalized.get(variant)
            if value not in (None, ""):
                return value
        value = source.get(key)
        if value not in (None, ""):
            return value
    return None


def _clean_person_name(value: Any) -> str:
    """Normalize a person name string."""
    return " ".join(str(value or "").split())


def _user_display_name(user: dict) -> str:
    """Extract display name from user record."""
    name = (
        user.get("display_name")
        or user.get("name")
        or user.get("consultant_name")
        or user.get("full_name")
        or ""
    )
    if not name:
        first = user.get("first_name", "")
        last = user.get("last_name", "")
        name = f"{first} {last}".strip()
    if not name:
        name = user.get("email_id") or user.get("email") or "Unknown"
    return _clean_person_name(name)


def _split_ids(value: Any) -> list[str]:
    """Split a value into a list of IDs."""
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).replace(";", ",").replace("|", ",").split(",")
    return [str(item).strip() for item in raw if str(item).strip()]


def _resolve_people(value: Any, user_map: dict[str, str], fallback: str) -> str:
    """Resolve person IDs to names using user map."""
    if str(value or "").strip() in {"", "0", "N/A", "None", "none", "null"}:
        return fallback

    ids = _split_ids(value)
    if not ids:
        text = str(value or "").strip()
        return text or fallback

    names = [user_map.get(person_id, person_id) for person_id in ids]
    names = [name for name in names if name and name.lower() not in {"none", "null"}]
    if not names:
        text = str(value or "").strip()
        return text or fallback
    return ", ".join(dict.fromkeys(names))


def _looks_like_unresolved_id(value: Any) -> bool:
    """Check if value looks like an unresolved ID (email, hash, etc.)."""
    text = str(value or "").strip()
    if not text or " " in text or "@" in text:
        return False
    if text.isdigit():
        return True
    if len(text) < 16:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_+=/-]+", text))


def _has_unresolved_id(value: str, fallback: str) -> bool:
    """Check if value contains unresolved IDs."""
    if not value or value == fallback:
        return False
    return any(_looks_like_unresolved_id(part) for part in _split_ids(value))


def _resolve_people_candidates(
    candidates: tuple[Any, ...],
    user_map: dict[str, str],
    fallback: str,
) -> str:
    """Try multiple candidates and return first resolved name."""
    unresolved = ""
    for candidate in candidates:
        resolved = _resolve_people(candidate, user_map, fallback)
        if resolved == fallback:
            continue
        if _has_unresolved_id(resolved, fallback):
            unresolved = unresolved or resolved
            continue
        return resolved
    return unresolved or fallback


def _clean_title(t: Any) -> str:
    """Clean job title by removing prefix noise."""
    if not t:
        return "Untitled"
    if " - " in t:
        after = t.split(" - ", 1)[1]
        pos = after.find("_")
        if pos != -1:
            r = after[pos + 1 :].strip()
            if r:
                return r
    return t


def _parse_date_yyyy_mm_dd(value: Any) -> Optional[datetime]:
    """Parse YYYY-MM-DD date string."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_record_date(record: dict, keys: tuple[str, ...]) -> Optional[date]:
    """Parse date from record using multiple possible keys."""
    for key in keys:
        value = _first_present(record, (key,))
        if not value:
            continue
        text = str(value).strip()[:10]
        for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _parse_record_datetime(record: dict, keys: tuple[str, ...]) -> Optional[datetime]:
    """Parse datetime from record using multiple possible keys."""
    for key in keys:
        value = _first_present(record, (key,))
        if not value:
            continue
        text = str(value).strip()
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%y %H:%M:%S",
            "%m/%d/%Y",
            "%m/%d/%y",
        ):
            try:
                return datetime.strptime(text[: len(datetime.now().strftime(fmt))], fmt)
            except ValueError:
                continue
    return None


def _parse_screen_date(value: Any) -> Optional[datetime]:
    """Parse date from screen format (MM/DD/YY HH:MM:SS)."""
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%m/%d/%y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _screen_text(value: Any, fallback: str) -> str:
    """Clean screen text with fallback."""
    text = " ".join(str(value or "").split())
    if text and text not in {"0", "N/A", "None", "null"}:
        return text
    return fallback


def _clean_job_code(value: Any) -> str:
    """Clean job code for matching."""
    return " ".join(str(value or "").upper().replace(" -", " ").replace("-", " ").split())


def _job_id(record: dict) -> str:
    """Extract job ID from record."""
    return str(
        _first_present(record, ("job_id", "job id", "requirement_id", "id")) or ""
    ).strip()


def _sub_status(subs: list[dict]) -> str:
    """Get submission status from list."""
    if not subs:
        return "Pending"

    s = sorted(subs, key=lambda x: x.get("submitted_on", ""), reverse=True)
    latest = s[0]
    st = str(
        _first_present(
            latest,
            (
                "status",
                "submission_status",
                "submission status",
                "application_status",
                "application status",
                "candidate_status",
            ),
        )
        or ""
    ).strip()
    return st or "In Progress"


def _resolve_submission_person(subs: list[dict], user_map: dict[str, str]) -> str:
    """Extract recruiter from submissions."""
    candidates: list[Any] = []
    for sub in subs:
        candidates.append(
            _first_present(
                sub,
                (
                    "recruiter",
                    "recruiter_id",
                    "recruiter_name",
                    "submitted_by",
                    "submitted by",
                    "submitted_by_id",
                    "created_by",
                    "created_by_id",
                    "owner",
                    "owner_id",
                    "assigned_to",
                    "assigned_to_id",
                    "submission_owner",
                    "submission_owner_id",
                ),
            )
        )
    return _resolve_people_candidates(tuple(candidates), user_map, "Unassigned")


def _dedupe_jobs(jobs: list[dict]) -> list[dict]:
    """Remove duplicate jobs by ID."""
    seen: set[str] = set()
    unique: list[dict] = []
    for job in jobs:
        key = str(job.get("id") or job.get("job_code") or "").strip()
        if not key:
            key = str(
                job.get("public_job_title") or job.get("position_title") or job
            ).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def _is_active_technical_recruiter(user: dict) -> bool:
    """Check if user is an active technical recruiter."""
    return (
        str(user.get("status") or "").strip().lower() == "active"
        and str(user.get("role") or "").strip().lower() == "technical recruiter"
    )


def _format_time_to_submit(start: Optional[datetime], submissions: list[dict]) -> str:
    """Calculate time from job creation to first submission."""
    if not start or not submissions:
        return "--"

    submitted_values = [
        _parse_record_datetime(
            sub,
            ("submitted_on", "submitted on", "submitted_date", "created", "created_on"),
        )
        for sub in submissions
    ]
    submitted_values = [value for value in submitted_values if value and value >= start]
    if not submitted_values:
        return "--"

    delta = min(submitted_values) - start
    total_minutes = max(0, int(delta.total_seconds() // 60))
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)

    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"