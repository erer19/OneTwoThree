import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

from app.reports.weekly import build_weekly_report

logger = logging.getLogger("reports.builder")
logger.setLevel(logging.INFO)


def _default_previous_week() -> str:
    """Return the previous ISO week string (e.g. '2026-W40')."""
    today = datetime.now(timezone.utc)
    prev = today - timedelta(days=7)
    iso_year, iso_week, _ = prev.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def detect_trigger(event: dict[str, Any]) -> tuple[str, str | None]:
    """Detect whether the invocation was triggered by SQS, schedule, or direct call.

    Returns (trigger_name, week_if_provided).
    """
    # 1. SQS Event
    records = event.get("Records")
    if records and isinstance(records, list) and records[0].get("eventSource") == "aws:sqs":
        body_raw = records[0].get("body", "{}")
        try:
            body = json.loads(body_raw)
        except Exception:
            body = {}
        # Schedule sends {"week": null, "source": "schedule"} through SQS.
        # on-demand sends {"week": "2026-W39", "source": "sqs"}
        trigger = body.get("source", "sqs")
        return trigger, body.get("week")

    # 2. EventBridge schedule direct invocation
    if event.get("source") in ("schedule", "aws.events") or "time" in event:
        return "schedule", event.get("week")

    # 3. Direct invocation
    trigger = event.get("source", "direct")
    return trigger, event.get("week")


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    trigger, req_week = detect_trigger(event)
    week = req_week or _default_previous_week()

    # Step 7 / Submission Requirement Item 4: CloudWatch log line
    logger.info("report-builder triggered", extra={"trigger": trigger, "week": week})
    print(f"report-builder triggered: trigger={trigger} week={week}")

    # Step 7 test scenario: if week is 'raise-error', test DLQ redrive
    if week == "raise-error":
        raise RuntimeError("Intentional error for DLQ testing (week=raise-error)")

    csv_bytes = build_weekly_report(week)

    bucket = os.environ.get("REPORTS_BUCKET")
    if not bucket:
        raise ValueError("REPORTS_BUCKET environment variable is not set")

    key = f"reports/{week}.csv"

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=csv_bytes,
        ContentType="text/csv",
    )
    print(f"Successfully uploaded s3://{bucket}/{key} ({len(csv_bytes)} bytes)")

    return {"status": "ok", "trigger": trigger, "week": week, "key": key}

