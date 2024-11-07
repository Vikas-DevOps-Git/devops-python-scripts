#!/usr/bin/env python3
"""
incident_triage/main.py — Incident triage dispatcher CLI and webhook server

Classifies incident by keyword, posts formatted Slack message with
severity, runbook link, and team routing. Optionally triggers PagerDuty.

Usage:
    # One-shot from JSON string
    python -m incident_triage.main \\
      --payload '{"id":"INC-001","title":"OOM kill on payment-api","environment":"production"}' \\
      --slack-webhook https://hooks.slack.com/...

    # Dry run — print Slack message without sending
    python -m incident_triage.main \\
      --payload '{"title":"Node not ready"}' \\
      --dry-run

    # Persistent webhook server (receives PagerDuty or Alertmanager webhooks)
    python -m incident_triage.main --serve --port 8080

Exit codes:
    0 — triaged successfully
    1 — notification failed or invalid payload
"""
import argparse
import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional

from incident_triage.classifier import classify
from incident_triage.notifier import build_slack_message, post_slack, trigger_pagerduty

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [incident_triage] %(message)s"
)
log = logging.getLogger(__name__)


def process_incident(payload_str: str,
                     slack_webhook: Optional[str] = None,
                     pd_routing_key: Optional[str] = None,
                     dry_run: bool = False) -> dict:
    """
    Parse payload, classify incident, send notifications.
    Returns result dict.
    """
    try:
        incident = json.loads(payload_str)
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON payload: {e}")
        return {"status": "error", "error": str(e)}

    title = incident.get("title", "")
    description = incident.get("description", "")
    body = incident.get("body", "")

    classification = classify(title, description, body)
    log.info(
        f"Classified: id={incident.get('id','N/A')} "
        f"severity={classification.severity} "
        f"category={classification.category} "
        f"team={classification.team}"
    )

    slack_message = build_slack_message(incident, classification)
    slack_sent = False
    pd_triggered = False

    if dry_run:
        log.info("[DRY RUN] Slack message:")
        print(json.dumps(slack_message, indent=2))
    else:
        if slack_webhook:
            slack_sent = post_slack(slack_webhook, slack_message)
        if pd_routing_key:
            pd_triggered = trigger_pagerduty(
                pd_routing_key, incident, classification,
                dedup_key=incident.get("id")
            )

    result = {
        "incident_id": incident.get("id", "N/A"),
        "title": title,
        "severity": classification.severity,
        "category": classification.category,
        "team": classification.team,
        "runbook": classification.runbook_url,
        "matched_keyword": classification.matched_keyword,
        "slack_sent": slack_sent,
        "pagerduty_triggered": pd_triggered,
        "dry_run": dry_run,
        "status": "success",
    }

    return result


class WebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for incoming PagerDuty / Alertmanager webhooks."""
    slack_webhook = None
    pd_routing_key = None

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = self.rfile.read(length).decode("utf-8")
        result = process_incident(
            payload,
            self.slack_webhook,
            self.pd_routing_key,
        )
        self.send_response(200 if result["status"] == "success" else 400)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode())

    def log_message(self, fmt, *args):
        log.info(f"HTTP {args[1]} {args[0]}")


def main():
    parser = argparse.ArgumentParser(
        description="Incident Triage Dispatcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--payload",
                        default=None,
                        help="JSON incident payload string")
    parser.add_argument("--payload-file",
                        default=None,
                        help="Path to JSON file containing incident payload")
    parser.add_argument("--slack-webhook",
                        default=os.environ.get("SLACK_WEBHOOK_URL"),
                        help="Slack incoming webhook URL")
    parser.add_argument("--pd-routing-key",
                        default=os.environ.get("PAGERDUTY_ROUTING_KEY"),
                        help="PagerDuty Events API v2 routing key")
    parser.add_argument("--serve",
                        action="store_true",
                        help="Run as persistent HTTP webhook server")
    parser.add_argument("--port",
                        type=int, default=8080,
                        help="Webhook server port (default: 8080)")
    parser.add_argument("--dry-run",
                        action="store_true",
                        help="Print Slack message without sending")
    parser.add_argument("--output", default="text", choices=["text", "json"],
                        help="Output format for CLI mode")
    args = parser.parse_args()

    if args.serve:
        WebhookHandler.slack_webhook = args.slack_webhook
        WebhookHandler.pd_routing_key = args.pd_routing_key
        server = HTTPServer(("0.0.0.0", args.port), WebhookHandler)
        log.info(f"Webhook server listening on port {args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            log.info("Shutting down webhook server")
        return

    payload_str = None
    if args.payload:
        payload_str = args.payload
    elif args.payload_file:
        with open(args.payload_file) as f:
            payload_str = f.read()
    else:
        parser.print_help()
        sys.exit(1)

    result = process_incident(
        payload_str,
        args.slack_webhook,
        args.pd_routing_key,
        args.dry_run,
    )

    if args.output == "json":
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*55}")
        print(f"  Incident Triage Result")
        print(f"{'='*55}")
        for k, v in result.items():
            print(f"  {k:<25}: {v}")
        print(f"{'='*55}\n")

    sys.exit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
