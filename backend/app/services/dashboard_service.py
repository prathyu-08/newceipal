"""
services/dashboard_service.py
---------------------------
Business logic for dashboard endpoints.

FIX 6: build_today_submissions now resolves all job titles concurrently via
        asyncio.gather instead of one blocking get_job_details() call per
        submission in a serial loop. This can cut response time by 5-20x
        when there are many unique jobs in today's submissions.

FIX 8: Removed the always-None `database_query_ms` reference. It was set in
        logging.py but never populated anywhere, causing confusing null fields
        in every log entry.
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Optional

from app.config.settings import get_settings
from app.core.response_cache import cached_response
from app.core.utils import (
    _clean_title,
    _split_ids,
    _resolve_people,
    _field_variants,
    _first_present,
    _resolve_people_candidates,
    _clean_person_name,
    _user_display_name,
    _is_active_technical_recruiter,
    _parse_date_yyyy_mm_dd,
    _parse_record_date,
    _parse_record_datetime,
    _format_time_to_submit,
    _parse_screen_date,
    _screen_text,
    _clean_job_code,
    _job_id,
    _sub_status,
    _resolve_submission_person,
    _dedupe_jobs,
)
from app.services.ceipal_service import (
    get_jobs,
    get_users,
    get_all_submissions,
    get_applicants_total_count,
    get_submissions_total_count,
    get_job_details,
    get_priority_cached,
    flush_job_detail_cache,
    start_priority_cache_loader,
    build_user_map,
    get_jobposts_screen_rows,
)

logger = logging.getLogger(__name__)
settings = get_settings()

_HIGH_PRIORITY_TTL = settings.high_priority_cache_ttl_seconds
high_priority_cache: dict[str, dict] = {}
high_priority_lock = RLock()


class RequirementItem:
    """Data class for high-priority requirement items."""

    def __init__(
        self,
        bdm: str,
        lead: str,
        recruiter: str,
        priority: str,
        submissions: int,
        submission_status: str,
        requirement: str,
        time_to_submit: str = "--",
    ):
        self.bdm = bdm
        self.lead = lead
        self.recruiter = recruiter
        self.priority = priority
        self.submissions = submissions
        self.submission_status = submission_status
        self.requirement = requirement
        self.time_to_submit = time_to_submit

    def model_dump(self) -> dict:
        return {
            "bdm": self.bdm,
            "lead": self.lead,
            "recruiter": self.recruiter,
            "priority": self.priority,
            "submissions": self.submissions,
            "submission_status": self.submission_status,
            "requirement": self.requirement,
            "time_to_submit": self.time_to_submit,
        }


class DashboardStats:
    """Data class for dashboard stats."""

    def __init__(
        self,
        active_jobs: int,
        total_recruiters: int,
        total_applicants: int,
        total_submissions: int,
    ):
        self.active_jobs = active_jobs
        self.total_recruiters = total_recruiters
        self.total_applicants = total_applicants
        self.total_submissions = total_submissions

    def model_dump(self) -> dict:
        return {
            "active_jobs": self.active_jobs,
            "total_recruiters": self.total_recruiters,
            "total_applicants": self.total_applicants,
            "total_submissions": self.total_submissions,
        }


class BdmKpiItem:
    """Data class for BDM KPI items."""

    def __init__(
        self,
        bdm_name: str,
        requirements_received: int,
        profiles_submitted: int,
        feedback_pending: int,
        interviews: int,
        closures: int,
    ):
        self.bdm_name = bdm_name
        self.requirements_received = requirements_received
        self.profiles_submitted = profiles_submitted
        self.feedback_pending = feedback_pending
        self.interviews = interviews
        self.closures = closures

    def model_dump(self) -> dict:
        return {
            "bdm_name": self.bdm_name,
            "requirements_received": self.requirements_received,
            "profiles_submitted": self.profiles_submitted,
            "feedback_pending": self.feedback_pending,
            "interviews": self.interviews,
            "closures": self.closures,
        }


class TodaySubmissionItem:
    """Data class for today's submissions."""

    def __init__(
        self,
        submission_id: str,
        submitted_on: str,
        recruiter: str,
        job_title: str,
        job_id: str,
        candidate_id: str,
        status: str,
        source: str,
        employment_type: str,
        pay_rate: str,
        tax_term: str,
    ):
        self.submission_id = submission_id
        self.submitted_on = submitted_on
        self.recruiter = recruiter
        self.job_title = job_title
        self.job_id = job_id
        self.candidate_id = candidate_id
        self.status = status
        self.source = source
        self.employment_type = employment_type
        self.pay_rate = pay_rate
        self.tax_term = tax_term

    def model_dump(self) -> dict:
        return {
            "submission_id": self.submission_id,
            "submitted_on": self.submitted_on,
            "recruiter": self.recruiter,
            "job_title": self.job_title,
            "job_id": self.job_id,
            "candidate_id": self.candidate_id,
            "status": self.status,
            "source": self.source,
            "employment_type": self.employment_type,
            "pay_rate": self.pay_rate,
            "tax_term": self.tax_term,
        }


def _resolve_bdm(job: dict, user_map: dict[str, str]) -> str:
    """Resolve BDM name from job record."""
    return _resolve_people_candidates(
        (
            _first_present(
                job,
                (
                    "sales_manager",
                    "sales manager",
                    "bdm_name",
                    "bdm",
                    "hiring_manager",
                    "hiring manager",
                ),
            ),
            _first_present(
                job,
                (
                    "recruitment_manager",
                    "recruitment_manager_id",
                    "recruitment manager",
                    "Recruitment Manager",
                    "bdm_id",
                    "hiring_manager_id",
                    "sales_manager_id",
                    "posted_by",
                    "created_by",
                ),
            ),
        ),
        user_map,
        "Unassigned BDM",
    )


def _get_high_priority_cache(cache_key: str) -> Optional[list[dict]]:
    """Get high priority requirements from cache."""
    now = time.time()
    cached = high_priority_cache.get(cache_key)
    if cached and now < cached["expires_at"]:
        logger.debug(
            "/dashboard/high-priority cache HIT key=%s results=%s",
            cache_key,
            len(cached["data"]),
        )
        return cached["data"]
    return None


def _extract_job_title(details: dict | Exception) -> str:
    """Extract job title from job details, tolerating errors."""
    if isinstance(details, Exception) or not details:
        return "Unassigned Requirement"
    title = _first_present(
        details,
        (
            "job_title",
            "job title",
            "position_title",
            "position title",
            "requirement",
            "title",
            "posting_title",
        ),
    )
    return _clean_title(str(title or "")) if title else "Unassigned Requirement"


async def build_dashboard_stats() -> dict:
    """Build dashboard statistics."""
    try:
        jobs_result, users_result, applicants_result, submissions_result = await asyncio.gather(
            asyncio.to_thread(get_jobs, max_pages=10),
            asyncio.to_thread(get_users),
            asyncio.to_thread(get_applicants_total_count),
            asyncio.to_thread(get_submissions_total_count),
        )
        jobs, _jobs_total = jobs_result
        users = users_result
        total_applicants = applicants_result
        total_submissions = submissions_result
    except RuntimeError as exc:
        raise RuntimeError(f"Failed to fetch dashboard stats: {exc}") from exc

    return DashboardStats(
        active_jobs=len(_dedupe_jobs(list(jobs))),
        total_recruiters=len(users),
        total_applicants=total_applicants,
        total_submissions=total_submissions,
    ).model_dump()


async def build_recruiting_status(today: datetime) -> dict:
    """Build recruiting status for a given date."""
    try:
        jobs_result, users_result, subs_result = await asyncio.gather(
            asyncio.to_thread(get_jobposts_screen_rows, max_pages=0),
            asyncio.to_thread(get_users),
            asyncio.to_thread(get_all_submissions, max_pages=1),
        )
        jobs, _jobs_total = jobs_result
        users = users_result
        subs, _subs_total = subs_result
    except RuntimeError as exc:
        logger.error("/dashboard/status build failed; returning fallback: %s", exc)
        return {
            "loadedAt": datetime.now().isoformat(),
            "technicalRecruitersCount": 0,
            "activeRequirementsAsOfToday": 0,
            "activeRequirementsCarriedForwardUpToYesterday": 0,
            "recruitersWorkingOnRequirementsCount": 0,
            "idleRecruitersCount": 0,
            "totalSubmissionsToday": 0,
            "recruitersWorkingOnRequirements": [],
            "idleRecruiters": [],
        }

    active_jobs = [
        row
        for row in jobs
        if _screen_text(
            row.get("job_status_text") or row.get("job_status") or row.get("status"),
            "Active",
        ).lower()
        == "active"
    ]
    technical_recruiters = [user for user in users if _is_active_technical_recruiter(user)]
    technical_recruiter_names = {
        _user_display_name(user)
        for user in technical_recruiters
        if _user_display_name(user)
    }

    today_active_jobs = [
        job
        for job in active_jobs
        if (
            _parse_screen_date(job.get("created_text"))
            or _parse_record_date(job, ("created", "created_on", "job_created"))
        )
        == today
    ]

    working_names: set[str] = set()
    for job in today_active_jobs:
        for name in _split_ids(job.get("assigned_recruiter")):
            clean_value = _clean_person_name(name)
            if clean_value in technical_recruiter_names:
                working_names.add(clean_value)

    recruiters_working = sorted(working_names)
    idle_recruiters = sorted(technical_recruiter_names - working_names)

    active_today = len(today_active_jobs)
    carried_forward = sum(
        1
        for job in active_jobs
        if (
            created := (
                _parse_screen_date(job.get("created_text"))
                or _parse_record_date(job, ("created", "created_on", "job_created"))
            )
        )
        is not None
        and created < today
    )

    submissions_today = sum(
        1
        for sub in subs
        if _parse_record_date(
            sub,
            ("submitted_on", "submitted on", "created", "created_on"),
        )
        == today
    )

    return {
        "loadedAt": datetime.now().isoformat(),
        "technicalRecruitersCount": len(technical_recruiter_names),
        "activeRequirementsAsOfToday": active_today,
        "activeRequirementsCarriedForwardUpToYesterday": carried_forward,
        "recruitersWorkingOnRequirementsCount": len(recruiters_working),
        "idleRecruitersCount": len(idle_recruiters),
        "totalSubmissionsToday": submissions_today,
        "recruitersWorkingOnRequirements": recruiters_working,
        "idleRecruiters": idle_recruiters,
    }


async def build_today_submissions(today: datetime) -> list[dict]:
    """Build list of today's submissions.

    FIX 6: Job titles are now resolved concurrently for all unique job IDs
           instead of one blocking call per submission in a serial loop.
    """
    try:
        subs_result, users_result = await asyncio.gather(
            asyncio.to_thread(get_all_submissions, max_pages=0),
            asyncio.to_thread(get_users),
        )
        subs, _subs_total = subs_result
        users = users_result
    except RuntimeError as exc:
        raise RuntimeError(f"Failed to fetch submissions: {exc}") from exc

    user_map = build_user_map(users)
    today_subs = [
        sub
        for sub in subs
        if _parse_record_date(
            sub,
            ("submitted_on", "submitted on", "submitted_date", "submission_date", "created", "created_on"),
        )
        == today
    ]

    # FIX 6: Gather all unique job titles concurrently instead of one call per submission
    unique_job_ids = list({_job_id(sub) for sub in today_subs if _job_id(sub)})
    if unique_job_ids:
        details_list = await asyncio.gather(
            *[asyncio.to_thread(get_job_details, jid) for jid in unique_job_ids],
            return_exceptions=True,
        )
        job_title_cache: dict[str, str] = {
            jid: _extract_job_title(details)
            for jid, details in zip(unique_job_ids, details_list)
        }
    else:
        job_title_cache = {}

    results: list[dict] = []
    for sub in sorted(today_subs, key=lambda item: str(item.get("submitted_on") or ""), reverse=True):
        job_id = _job_id(sub)
        recruiter = _resolve_people_candidates(
            (
                _first_present(
                    sub,
                    (
                        "submitted_by",
                        "submitted by",
                        "submitted_by_id",
                        "recruiter",
                        "recruiter_id",
                        "created_by",
                    ),
                ),
            ),
            user_map,
            "Unassigned",
        )
        results.append(
            TodaySubmissionItem(
                submission_id=str(_first_present(sub, ("submission_id", "id")) or ""),
                submitted_on=str(_first_present(sub, ("submitted_on", "submitted on")) or ""),
                recruiter=recruiter,
                job_title=job_title_cache.get(job_id, "Unassigned Requirement"),
                job_id=job_id,
                candidate_id=str(_first_present(sub, ("job_seeker_id", "candidate_id", "applicant_id")) or ""),
                status=str(_first_present(sub, ("submission_status", "status", "application_status")) or "In Progress"),
                source=str(_first_present(sub, ("source",)) or "--"),
                employment_type=str(_first_present(sub, ("employment_type", "employment type")) or "--"),
                pay_rate=str(_first_present(sub, ("pay_rate", "pay rate")) or "--"),
                tax_term=str(_first_present(sub, ("tax_term", "tax term")) or "--"),
            ).model_dump()
        )

    return results


async def build_bdm_performance(period: str) -> list[dict]:
    """Build BDM performance metrics."""
    target_date = datetime.now().date()
    if period == "yesterday":
        target_date = target_date - timedelta(days=1)

    try:
        screen_rows_result = await asyncio.to_thread(get_jobposts_screen_rows, max_pages=0)
        screen_rows, _screen_total = screen_rows_result
    except RuntimeError as exc:
        logger.warning("CEIPAL JobPosts screen fetch failed; falling back to v2 API: %s", exc)
    except Exception as exc:
        logger.warning("CEIPAL JobPosts screen fetch failed; falling back to v2 API: %s", exc)
    else:
        groups: dict[str, dict] = {}
        for row in screen_rows:
            status = _screen_text(row.get("job_status_text") or row.get("job_status"), "").lower()
            if status != "active":
                continue
            if _parse_screen_date(row.get("created_text")) != target_date:
                continue

            bdm_name = _resolve_people_candidates(
                (
                    row.get("sales_manager"),
                    row.get("hiring_manager"),
                    row.get("recruitment_manager"),
                ),
                {},
                "Unassigned BDM",
            )
            if bdm_name not in groups:
                groups[bdm_name] = {
                    "bdm_name": bdm_name,
                    "requirements_received": 0,
                    "profiles_submitted": 0,
                    "feedback_pending": 0,
                    "interviews": 0,
                    "closures": 0,
                }
            groups[bdm_name]["requirements_received"] += 1
            submissions_count = int(row.get("submissions_count") or 0)
            groups[bdm_name]["profiles_submitted"] += submissions_count
            groups[bdm_name]["feedback_pending"] += submissions_count

        return [
            BdmKpiItem(**row).model_dump()
            for row in sorted(
                groups.values(),
                key=lambda r: (
                    -r["requirements_received"],
                    -r["profiles_submitted"],
                    r["bdm_name"],
                ),
            )
        ]

    try:
        jobs_result, users_result, subs_result = await asyncio.gather(
            asyncio.to_thread(
                get_jobs,
                max_pages=0,
                stop_before_date=target_date.isoformat(),
            ),
            asyncio.to_thread(get_users),
            asyncio.to_thread(get_all_submissions, max_pages=0),
        )
        jobs, _jobs_total = jobs_result
        users = users_result
        subs, _subs_total = subs_result
    except RuntimeError as exc:
        raise RuntimeError(f"Failed to fetch BDM performance data: {exc}") from exc

    user_map = build_user_map(users)
    all_jobs = _dedupe_jobs(list(jobs))
    jobs = [
        job
        for job in all_jobs
        if _parse_record_date(job, ("created", "created_on", "modified"))
        == target_date
    ]

    bdm_by_job = {
        str(job.get("id") or "").strip(): _resolve_bdm(job, user_map)
        for job in all_jobs
        if str(job.get("id") or "").strip()
    }

    submission_job_ids = {
        _job_id(sub)
        for sub in subs
        if _parse_record_date(
            sub,
            ("submitted_on", "submitted on", "created", "created_on"),
        )
        == target_date
    }
    for job_id in sorted(submission_job_ids - set(bdm_by_job)):
        if not job_id:
            continue
        details = get_job_details(job_id)
        if details:
            bdm_by_job[job_id] = _resolve_bdm(details, user_map)

    groups: dict[str, dict] = {}

    for job in jobs:
        bdm_name = bdm_by_job.get(str(job.get("id") or "").strip(), "Unassigned BDM")
        if bdm_name not in groups:
            groups[bdm_name] = {
                "bdm_name": bdm_name,
                "requirements_received": 0,
                "profiles_submitted": 0,
                "feedback_pending": 0,
                "interviews": 0,
                "closures": 0,
            }
        groups[bdm_name]["requirements_received"] += 1

    for sub in subs:
        submitted = _parse_record_date(
            sub,
            ("submitted_on", "submitted on", "created", "created_on"),
        )
        if submitted != target_date:
            continue

        bdm_name = bdm_by_job.get(_job_id(sub), "Unassigned BDM")
        if bdm_name not in groups:
            groups[bdm_name] = {
                "bdm_name": bdm_name,
                "requirements_received": 0,
                "profiles_submitted": 0,
                "feedback_pending": 0,
                "interviews": 0,
                "closures": 0,
            }
        groups[bdm_name]["profiles_submitted"] += 1

        status = _sub_status([sub]).lower()
        if "pending" in status or "waiting" in status:
            groups[bdm_name]["feedback_pending"] += 1
        if "interview" in status:
            groups[bdm_name]["interviews"] += 1
        if any(word in status for word in ("closure", "placed", "hired", "joined")):
            groups[bdm_name]["closures"] += 1

    return [
        BdmKpiItem(**row).model_dump()
        for row in sorted(
            groups.values(),
            key=lambda r: (
                -r["requirements_received"],
                -r["profiles_submitted"],
                r["bdm_name"],
            ),
        )
    ]


def build_high_priority_requirements(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> list[dict]:
    """Build high priority requirements list."""
    p_from = _parse_date_yyyy_mm_dd(date_from)
    p_to = _parse_date_yyyy_mm_dd(date_to)

    if not p_from and not p_to:
        p_from = datetime.now().date() - timedelta(days=1)
        p_to = p_from

    cache_key = f"posted-jobs:{p_from.isoformat() if p_from else ''}:{p_to.isoformat() if p_to else ''}"
    with high_priority_lock:
        cached_result = _get_high_priority_cache(cache_key)
        if cached_result is not None:
            return cached_result

    has_filter = bool(p_from or p_to)

    try:
        screen_date_from = p_from.isoformat() if p_from else None
        screen_date_to = p_to.isoformat() if p_to else None
        screen_rows, screen_total = get_jobposts_screen_rows(
            max_pages=20 if has_filter else 50,
            date_from=screen_date_from,
            date_to=screen_date_to,
        )
    except RuntimeError as exc:
        logger.info("CEIPAL JobPosts screen source skipped; falling back to v2 API: %s", exc)
    except Exception as exc:
        logger.warning("CEIPAL JobPosts screen fetch failed; falling back to v2 API: %s", exc)
    else:
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                jobs_future = executor.submit(
                    get_jobs,
                    max_pages=0,
                    stop_before_date=p_from.isoformat() if p_from else None,
                )
                users_future = executor.submit(get_users)
                subs_future = executor.submit(get_all_submissions, max_pages=0)

                v2_jobs, _jobs_total = jobs_future.result()
                users = users_future.result()
                subs_list, _subs_total = subs_future.result()
        except RuntimeError:
            v2_jobs = []
            users = []
            subs_list = []

        user_map = build_user_map(users)
        jobs_by_code = {
            _clean_job_code(job.get("job_code")): job
            for job in v2_jobs
            if _clean_job_code(job.get("job_code"))
        }

        subs_by_job: dict[str, list[dict]] = {}
        for sub in subs_list:
            jid = _job_id(sub)
            if jid:
                subs_by_job.setdefault(jid, []).append(sub)

        results: list[dict] = []
        for row in screen_rows:
            status = _screen_text(row.get("job_status_text") or row.get("job_status"), "").lower()
            if status != "active":
                continue

            priority = _screen_text(row.get("priority_id"), "Not Set")

            if has_filter:
                created = _parse_screen_date(row.get("created_text"))
                in_range = False
                if created is not None:
                    in_range = True
                    if p_from and created < p_from:
                        in_range = False
                    if p_to and created > p_to:
                        in_range = False
                if not in_range:
                    continue

            matching_job = jobs_by_code.get(_clean_job_code(row.get("job_code_text")))
            job_id = _job_id(matching_job or row)
            job_subs = subs_by_job.get(job_id, [])

            submission_person = _resolve_submission_person(job_subs, user_map)
            created_at = _parse_record_datetime(
                matching_job or row,
                ("created", "created_on", "created_text"),
            )
            lead = _resolve_people_candidates(
                (
                    row.get("primary_recruiter"),
                    _first_present(
                        matching_job or {},
                        (
                            "primary_recruiter",
                            "primary_recruiter_id",
                            "primary recruiter",
                            "lead_recruiter",
                            "lead recruiter",
                            "lead",
                        ),
                    ),
                    submission_person,
                    row.get("assigned_recruiter"),
                ),
                user_map,
                "Unassigned",
            )
            recruiter = _resolve_people_candidates(
                (
                    row.get("assigned_recruiter"),
                    _first_present(
                        matching_job or {},
                        (
                            "assigned_recruiter",
                            "assigned recruiter",
                            "assigned_recruiter_id",
                            "assigned_to",
                            "assigned_to_id",
                            "recruiter",
                            "recruiter_id",
                            "recruiter_name",
                        ),
                    ),
                    submission_person,
                    row.get("primary_recruiter"),
                ),
                user_map,
                "Unassigned",
            )

            results.append(
                RequirementItem(
                    bdm=_resolve_people_candidates(
                        (
                            row.get("sales_manager"),
                            row.get("hiring_manager"),
                            _first_present(
                                matching_job or {},
                                (
                                    "sales_manager",
                                    "sales manager",
                                    "hiring_manager",
                                    "hiring manager",
                                    "recruitment_manager",
                                    "recruitment_manager_id",
                                ),
                            ),
                        ),
                        user_map,
                        "Unassigned BDM",
                    ),
                    lead=lead,
                    recruiter=recruiter,
                    priority=priority,
                    submissions=int(row.get("submissions_count") or 0),
                    submission_status=_sub_status(job_subs),
                    requirement=_screen_text(row.get("requirement_text"), "Untitled"),
                    time_to_submit=_format_time_to_submit(created_at, job_subs),
                ).model_dump()
            )

        priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Not Set": 4}
        results.sort(key=lambda item: (priority_order.get(item["priority"], 9), -item["submissions"]))
        logger.debug(
            "/dashboard/high-priority source=JobPosts screen_rows=%s/%s results=%s",
            len(screen_rows),
            screen_total,
            len(results),
        )
        with high_priority_lock:
            high_priority_cache[cache_key] = {
                "data": results,
                "expires_at": time.time() + _HIGH_PRIORITY_TTL,
            }
        return results

    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            if has_filter:
                jobs_future = executor.submit(get_jobs, max_pages=10)
                subs_pages = 3
            else:
                jobs_future = executor.submit(get_jobs, max_pages=2)
                subs_pages = 5
            users_future = executor.submit(get_users)
            subs_future = executor.submit(get_all_submissions, max_pages=subs_pages)

            jobs_list, jobs_total = jobs_future.result()
            users = users_future.result()
            subs_list, _subs_total = subs_future.result()
    except RuntimeError as exc:
        raise RuntimeError(f"Failed to fetch high priority requirements: {exc}") from exc

    user_map = build_user_map(users)

    subs_by_job: dict[str, list[dict]] = {}
    for sub in subs_list:
        jid = str(sub.get("job_id", "")).strip()
        if jid:
            subs_by_job.setdefault(jid, []).append(sub)

    jobs = _dedupe_jobs(list(jobs_list))

    if has_filter:
        filtered: list[dict] = []
        for j in jobs:
            cr = str(j.get("created", "")).strip()[:10]
            cd = None
            if cr:
                try:
                    cd = datetime.strptime(cr, "%Y-%m-%d").date()
                except ValueError:
                    cd = None
            in_range = cd is not None
            if cd is not None:
                if p_from and cd < p_from:
                    in_range = False
                if p_to and cd > p_to:
                    in_range = False
            if in_range:
                filtered.append(j)
        jobs = filtered

    jobs = [
        job
        for job in jobs
        if _screen_text(
            _first_present(job, ("job_status", "job status", "status")),
            "Active",
        ).lower()
        == "active"
    ]

    def process_job(job: dict) -> dict:
        job_id = str(job.get("id", "")).strip()
        recruiter_ids = _first_present(
            job,
            (
                "assigned_to",
                "assigned_to_id",
                "assigned to",
                "Assigned To",
                "assigned_recruiter",
                "assigned_recruiter_id",
                "assigned recruiter",
                "Assigned Recruiter",
                "recruiter",
                "recruiter_id",
                "recruiter_name",
                "Recruiter",
                "owner",
                "owner_id",
            ),
        )
        job_subs = subs_by_job.get(job_id, [])
        submission_person = _resolve_submission_person(job_subs, user_map)
        recruiter = _resolve_people_candidates(
            (
                recruiter_ids,
                submission_person,
                _first_present(
                    job,
                    (
                        "primary_recruiter",
                        "primary_recruiter_id",
                        "primary recruiter",
                    ),
                ),
                _first_present(
                    job,
                    (
                        "recruitment_manager",
                        "recruitment_manager_id",
                        "recruitment manager",
                    ),
                ),
            ),
            user_map,
            "Unassigned",
        )
        bdm = _resolve_bdm(job, user_map)
        lead = _resolve_people_candidates(
            (
                _first_present(
                    job,
                    (
                        "primary_recruiter",
                        "primary_recruiter_id",
                        "primary recruiter",
                        "lead_recruiter",
                        "lead recruiter",
                        "lead",
                    ),
                ),
                submission_person,
                recruiter_ids,
            ),
            user_map,
            "Unassigned",
        )

        title = _clean_title(job.get("public_job_title") or job.get("position_title") or "Untitled")
        priority = get_priority_cached(job_id)
        created_at = _parse_record_datetime(job, ("created", "created_on", "job_created"))

        return RequirementItem(
            bdm=bdm,
            lead=lead,
            recruiter=recruiter,
            priority=priority,
            submissions=len(job_subs),
            submission_status=_sub_status(job_subs),
            requirement=title,
            time_to_submit=_format_time_to_submit(created_at, job_subs),
        ).model_dump()

    with ThreadPoolExecutor(max_workers=12) as executor:
        results = list(executor.map(process_job, jobs))
    flush_job_detail_cache()

    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3, "Not Set": 4}
    results.sort(key=lambda x: (priority_order.get(x["priority"], 9), -x["submissions"]))

    logger.debug(
        "/dashboard/high-priority jobs=%s/%s subs=%s/%s filtered=%s results=%s",
        len(jobs_list),
        jobs_total,
        len(subs_list),
        _subs_total,
        has_filter,
        len(results),
    )

    with high_priority_lock:
        high_priority_cache[cache_key] = {
            "data": results,
            "expires_at": time.time() + _HIGH_PRIORITY_TTL,
        }
    return results


async def warm_dashboard_caches() -> None:
    """Pre-warm dashboard caches on startup."""
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    async def warm_all():
        return await asyncio.gather(
            _get_dashboard_stats_cached(),
            _get_recruiting_status_cached(today),
            _get_bdm_performance_cached("today"),
            _get_bdm_performance_cached("yesterday"),
            _get_high_priority_cached(today.isoformat(), today.isoformat()),
            _get_high_priority_cached(yesterday.isoformat(), yesterday.isoformat()),
            return_exceptions=True,
        )

    results = await warm_all()
    for result in results:
        if isinstance(result, Exception):
            logger.warning("Dashboard cache warm failed: %s", result)


async def _get_dashboard_stats_cached() -> dict:
    return await cached_response("dashboard:stats", settings.stats_cache_ttl_seconds if hasattr(settings, "stats_cache_ttl_seconds") else 60, build_dashboard_stats)


async def _get_recruiting_status_cached(today: datetime) -> dict:
    return await cached_response(
        f"dashboard:status:{today.isoformat()}",
        settings.status_cache_ttl_seconds,
        lambda: build_recruiting_status(today),
    )


async def _get_bdm_performance_cached(period: str) -> list[dict]:
    return await cached_response(
        f"dashboard:bdm-performance:{period}:{datetime.now().date().isoformat()}",
        settings.bdm_performance_cache_ttl_seconds,
        lambda: build_bdm_performance(period),
    )


async def _get_high_priority_cached(date_from: str, date_to: str) -> list[dict]:
    return await cached_response(
        f"dashboard:high-priority:{date_from}:{date_to}",
        _HIGH_PRIORITY_TTL,
        lambda: asyncio.to_thread(build_high_priority_requirements, date_from, date_to),
    )


def build_raw_data() -> dict:
    """Build raw data for debugging (development only)."""
    try:
        jobs, jt = get_jobs()
        users = get_users()
        subs, st = get_all_submissions()
    except RuntimeError as exc:
        raise RuntimeError(f"Failed to fetch raw data: {exc}") from exc

    return {
        "jobs_fetched": len(jobs),
        "jobs_total": jt,
        "subs_fetched": len(subs),
        "subs_total": st,
        "users": len(users),
        "sample_job": {
            k: v
            for k, v in jobs[0].items()
            if k not in ("public_job_desc", "requisition_description")
        }
        if jobs
        else {},
    }