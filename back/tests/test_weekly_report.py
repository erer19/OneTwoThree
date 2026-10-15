from datetime import datetime, timezone

import pytest

from app.models import Meeting, Participant, User
from app.reports.weekly import build_weekly_report, parse_iso_week
from tests.conftest import TestingSession


def test_parse_iso_week():
    start_curr, end_curr, start_prev, end_prev = parse_iso_week("2026-W40")
    # 2026-W40 Monday is 2026-09-28
    assert start_curr == datetime(2026, 9, 28, 0, 0, 0, tzinfo=timezone.utc)
    assert end_curr == datetime(2026, 10, 5, 0, 0, 0, tzinfo=timezone.utc)
    assert start_prev == datetime(2026, 9, 21, 0, 0, 0, tzinfo=timezone.utc)
    assert end_prev == datetime(2026, 9, 28, 0, 0, 0, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="Invalid ISO week format"):
        parse_iso_week("invalid-week")

    with pytest.raises(ValueError, match="Invalid week number"):
        parse_iso_week("2026-W60")


def test_build_weekly_report_empty():
    with TestingSession() as db:
        csv_bytes = build_weekly_report("2026-W40", db=db)
        text = csv_bytes.decode("utf-8")
        assert "ISO Week,2026-W40" in text
        assert "Meetings Count,0" in text
        assert "Total Duration (hours),0.00" in text


def test_build_weekly_report_with_meetings():
    with TestingSession() as db:
        user = User(cognito_sub="user-1", email="user1@example.com", name="Alice")
        db.add(user)
        db.flush()

        p1 = Participant(name="Bob", email="bob@example.com")
        p2 = Participant(name="Charlie", email="charlie@example.com")
        db.add_all([p1, p2])
        db.flush()

        # Current week (2026-09-28 to 2026-10-05)
        m1 = Meeting(
            title="Team Sync",
            place="Room 101",
            starts_at=datetime(2026, 9, 29, 10, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 9, 29, 11, 30, tzinfo=timezone.utc),  # 1.5 hrs
            owner_id=user.id,
            participants=[p1, p2],
        )
        m2 = Meeting(
            title="Design Review",
            call_link="https://meet.google.com/abc",
            starts_at=datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 9, 30, 16, 0, tzinfo=timezone.utc),  # 2.0 hrs
            owner_id=user.id,
            participants=[p1],
        )

        # Previous week (2026-09-21 to 2026-09-28)
        m_prev = Meeting(
            title="Old Planning",
            place="Room 102",
            starts_at=datetime(2026, 9, 22, 10, 0, tzinfo=timezone.utc),
            ends_at=datetime(2026, 9, 22, 11, 0, tzinfo=timezone.utc),  # 1.0 hr
            owner_id=user.id,
            participants=[p2],
        )

        db.add_all([m1, m2, m_prev])
        db.commit()

        csv_bytes = build_weekly_report("2026-W40", db=db)
        text = csv_bytes.decode("utf-8")

        assert "ISO Week,2026-W40" in text
        assert "Meetings Count,2" in text
        assert "Total Duration (hours),3.50" in text
        assert "Previous Week (2026-W39) Meetings,1" in text
        assert "Previous Week Total Duration (hours),1.00" in text
        assert "Meetings Change,+1" in text
        assert "Duration Change (hours),+2.50" in text
        assert "Design Review" in text
        assert "Team Sync" in text
        assert "Bob,bob@example.com,2,3.50" in text

