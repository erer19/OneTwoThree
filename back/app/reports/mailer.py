import logging
import os
import urllib.parse
from email.message import EmailMessage
from typing import Any

import boto3

logger = logging.getLogger("reports.mailer")
logger.setLevel(logging.INFO)


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    # CloudWatch log line for trigger=s3 (Item 4 in submission requirements)
    logger.info("report-mailer triggered", extra={"trigger": "s3"})
    print("report-mailer triggered: trigger=s3")

    records = event.get("Records", [])
    if not records:
        print("No S3 records found in event")
        return {"status": "no_records"}

    s3_info = records[0].get("s3", {})
    bucket = s3_info.get("bucket", {}).get("name")
    raw_key = s3_info.get("object", {}).get("key", "")
    key = urllib.parse.unquote_plus(raw_key)

    if not bucket or not key:
        raise ValueError(f"Missing bucket ({bucket}) or key ({key}) in event")

    print(f"Processing report file from S3: s3://{bucket}/{key}")

    s3 = boto3.client("s3")
    resp = s3.get_object(Bucket=bucket, Key=key)
    csv_content = resp["Body"].read()

    filename = os.path.basename(key)
    week_name = filename.removesuffix(".csv")

    sender = os.environ.get("SENDER_EMAIL", "reaperkryt@gmail.com")
    recipients_raw = os.environ.get("RECIPIENT_EMAIL", "reaperkryt@gmail.com")
    recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    # Build Email with attachment
    msg = EmailMessage()
    msg["Subject"] = f"Weekly Meetings Report — {week_name}"
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"Hello,\n\nPlease find attached the weekly meetings report for {week_name}.\n\n"
        f"File: {filename}\n"
        f"Generated automatically by AWS EventBridge, SQS, S3 and Lambda.\n"
    )

    msg.add_attachment(
        csv_content,
        maintype="text",
        subtype="csv",
        filename=filename,
    )

    ses = boto3.client("sesv2", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    ses.send_email(
        FromEmailAddress=sender,
        Destination={"ToAddresses": recipients},
        Content={"Raw": {"Data": msg.as_bytes()}},
    )

    print(f"Successfully sent report {filename} to {recipients} from {sender}")
    return {"status": "sent", "file": filename, "recipients": recipients}

