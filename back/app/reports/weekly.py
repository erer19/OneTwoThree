import csv
import io
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import SessionLocal
from app.models import Meeting


def parse_iso_week(week: str) -> tuple[datetime, datetime, datetime, datetime]:
    """Parse an ISO week string like '2026-W40'.

    Returns (current_week_start, current_week_end, prev_week_start, prev_week_end) as UTC datetimes.
    """
    match = re.match(r"^(\d{4})-W(\d{1,2})$", week.strip())
    if not match:
        raise ValueError(f"Invalid ISO week format: {week!r}. Expected format: 'YYYY-Www', e.g. '2026-W40'")
    year = int(match.group(1))
    week_num = int(match.group(2))
    if not 1 <= week_num <= 53:
        raise ValueError(f"Invalid week number: {week_num}. Must be between 1 and 53")

    # Day 1 of ISO week is Monday
    start_curr = datetime.fromisocalendar(year, week_num, 1).replace(tzinfo=timezone.utc)
    end_curr = start_curr + timedelta(days=7)

    start_prev = start_curr - timedelta(days=7)
    end_prev = start_curr
    return start_curr, end_curr, start_prev, end_prev


def _meeting_duration_hours(meeting: Meeting) -> float:
    if meeting.ends_at and meeting.starts_at and meeting.ends_at > meeting.starts_at:
        return (meeting.ends_at - meeting.starts_at).total_seconds() / 3600.0
    return 0.0


def build_weekly_report(week: str, db: Session | None = None) -> bytes:
    """Query the meetings of one ISO week (e.g. '2026-W40') and return the CSV."""
    start_curr, end_curr, start_prev, end_prev = parse_iso_week(week)

    def _generate(session: Session) -> bytes:
        # 1. Fetch current week's meetings
        curr_stmt = (
            select(Meeting)
            .options(selectinload(Meeting.participants))
            .where(Meeting.starts_at >= start_curr, Meeting.starts_at < end_curr)
            .order_by(Meeting.starts_at)
        )
        curr_meetings = list(session.scalars(curr_stmt).all())

        # 2. Fetch previous week's meetings
        prev_stmt = (
            select(Meeting)
            .where(Meeting.starts_at >= start_prev, Meeting.starts_at < end_prev)
        )
        prev_meetings = list(session.scalars(prev_stmt).all())

        # Metrics
        curr_count = len(curr_meetings)
        curr_duration = sum(_meeting_duration_hours(m) for m in curr_meetings)

        prev_count = len(prev_meetings)
        prev_duration = sum(_meeting_duration_hours(m) for m in prev_meetings)

        count_change = curr_count - prev_count
        duration_change = curr_duration - prev_duration

        # Top 5 longest meetings
        longest_meetings = sorted(
            curr_meetings,
            key=lambda m: (_meeting_duration_hours(m), m.starts_at),
            reverse=True,
        )[:5]

        # Per-participant breakdown
        participant_stats: dict[str, dict[str, object]] = {}
        for m in curr_meetings:
            dur = _meeting_duration_hours(m)
            for p in m.participants:
                key = str(p.id)
                if key not in participant_stats:
                    participant_stats[key] = {
                        "name": p.name,
                        "email": p.email,
                        "count": 0,
                        "duration": 0.0,
                    }
                participant_stats[key]["count"] = int(participant_stats[key]["count"]) + 1
                participant_stats[key]["duration"] = float(participant_stats[key]["duration"]) + dur

        # Generate CSV
        output = io.StringIO()
        writer = csv.writer(output)

        # Section 1: Summary KPI
        writer.writerow(["METRIC", "VALUE"])
        writer.writerow(["ISO Week", week])
        writer.writerow(["Period Start (UTC)", start_curr.strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(["Period End (UTC)", end_curr.strftime("%Y-%m-%d %H:%M:%S")])
        writer.writerow(["Meetings Count", curr_count])
        writer.writerow(["Total Duration (hours)", f"{curr_duration:.2f}"])
        prev_week_label = f"{start_prev.isocalendar().year}-W{start_prev.isocalendar().week:02d}"
        writer.writerow([f"Previous Week ({prev_week_label}) Meetings", prev_count])
        writer.writerow(["Previous Week Total Duration (hours)", f"{prev_duration:.2f}"])
        writer.writerow(["Meetings Change", f"{count_change:+d}"])
        writer.writerow(["Duration Change (hours)", f"{duration_change:+.2f}"])
        writer.writerow([])

        # Section 2: Top 5 Longest Meetings
        writer.writerow(["TOP 5 LONGEST MEETINGS"])
        writer.writerow([
            "Title",
            "Start Time (UTC)",
            "End Time (UTC)",
            "Duration (hours)",
            "Participants Count",
            "Place / Call Link",
        ])
        for m in longest_meetings:
            dur = _meeting_duration_hours(m)
            location = m.call_link or m.place or ""
            writer.writerow([
                m.title,
                m.starts_at.strftime("%Y-%m-%d %H:%M:%S") if m.starts_at else "",
                m.ends_at.strftime("%Y-%m-%d %H:%M:%S") if m.ends_at else "",
                f"{dur:.2f}",
                len(m.participants),
                location,
            ])
        writer.writerow([])

        # Section 3: Participants Breakdown
        writer.writerow(["PARTICIPANTS SUMMARY"])
        writer.writerow(["Participant Name", "Email", "Meetings Count", "Total Hours"])
        for stats in sorted(participant_stats.values(), key=lambda s: str(s["name"])):
            writer.writerow([
                stats["name"],
                stats["email"],
                stats["count"],
                f"{float(stats['duration']):.2f}",
            ])

        return output.getvalue().encode("utf-8")

    if db is not None:
        return _generate(db)

    with SessionLocal() as session:
        return _generate(session)

