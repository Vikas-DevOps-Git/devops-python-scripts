"""
notifier.py — Slack and PagerDuty notification helpers
"""
import json
import logging
import urllib.request
import urllib.error
from typing import Optional

log = logging.getLogger(__name__)

SEVERITY_EMOJI = {"P1": "🔴", "P2": "🟠", "P3": "🟡", "P4": "🟢"}
SEVERITY_COLOR = {"P1": "#FF0000", "P2": "#FF6600", "P3": "#FFCC00", "P4": "#00CC00"}


def build_slack_message(incident: dict, classification) -> dict:
    """
    Build Slack Block Kit message for an incident.
    """
    emoji = SEVERITY_EMOJI.get(classification.severity, "⚪")
    color = SEVERITY_COLOR.get(classification.severity, "#808080")
    title = incident.get("title", "Unknown incident")
    inc_id = incident.get("id", "N/A")
    env = incident.get("environment", "production")
    service = incident.get("service", "unknown")
    duration = incident.get("duration_minutes")
    description = incident.get("description", "")

    fields = [
        {"type": "mrkdwn", "text": f"*Incident ID:*\n{inc_id}"},
        {"type": "mrkdwn", "text": f"*Severity:*\n{emoji} {classification.severity}"},
        {"type": "mrkdwn", "text": f"*Category:*\n{classification.category}"},
        {"type": "mrkdwn", "text": f"*Environment:*\n{env}"},
        {"type": "mrkdwn", "text": f"*Service:*\n{service}"},
        {"type": "mrkdwn", "text": f"*Assigned Team:*\n@{classification.team}"},
    ]

    if duration:
        fields.append({"type": "mrkdwn", "text": f"*Duration:*\n{duration} min"})

    if classification.matched_keyword:
        fields.append({
            "type": "mrkdwn",
            "text": f"*Matched keyword:*\n`{classification.matched_keyword}`"
        })

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} {classification.severity} — {classification.category}"
            }
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{title}*"}
        },
    ]

    if description:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": description[:500]}
        })

    blocks.extend([
        {"type": "section", "fields": fields},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"📖 *Runbook:* <{classification.runbook_url}|View Runbook>"
            }
        },
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": "Auto-triaged by incident_triage — BNY Platform Engineering"
            }]
        }
    ])

    return {"blocks": blocks, "attachments": [{"color": color, "blocks": []}]}


def post_slack(webhook_url: str, message: dict, timeout: int = 10) -> bool:
    """Post message to Slack webhook URL."""
    data = json.dumps(message).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            if resp.status == 200 and body == "ok":
                log.info("Slack notification sent successfully")
                return True
            log.warning(f"Slack responded {resp.status}: {body}")
            return False
    except urllib.error.URLError as e:
        log.error(f"Slack webhook failed: {e}")
        return False


def trigger_pagerduty(routing_key: str, incident: dict,
                      classification, dedup_key: str = None) -> bool:
    """
    Trigger a PagerDuty alert via Events API v2.
    """
    payload = {
        "routing_key": routing_key,
        "event_action": "trigger",
        "dedup_key": dedup_key or incident.get("id", ""),
        "payload": {
            "summary": incident.get("title", "Unknown incident"),
            "severity": classification.severity.lower().replace("p", "")
                        if classification.severity.startswith("P") else "error",
            "source": incident.get("service", "kubernetes-platform"),
            "component": incident.get("service", "unknown"),
            "group": incident.get("environment", "production"),
            "class": classification.category,
            "custom_details": {
                "environment": incident.get("environment", "production"),
                "category": classification.category,
                "team": classification.team,
                "runbook": classification.runbook_url,
            }
        },
        "links": [
            {
                "href": classification.runbook_url,
                "text": "Runbook"
            }
        ]
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://events.pagerduty.com/v2/enqueue",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode())
            if body.get("status") == "success":
                log.info(f"PagerDuty event triggered — dedup_key={dedup_key}")
                return True
            log.warning(f"PagerDuty responded: {body}")
            return False
    except Exception as e:
        log.error(f"PagerDuty trigger failed: {e}")
        return False
