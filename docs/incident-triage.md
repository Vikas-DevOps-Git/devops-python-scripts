# incident_triage — Usage Guide

## Overview

Classifies incidents by keyword, routes to correct team, posts formatted
Slack alerts with severity and runbook link, and optionally triggers PagerDuty.

## Classification Rules

| Category | Keywords | Severity | Team |
|---|---|---|---|
| OOM_KILL | oom, oomkill, memory limit exceeded, evicted | P1 | platform-team |
| NODE_FAILURE | node not ready, diskpressure, memorypressure | P1 | platform-team |
| SECURITY | vault, auth failed, token expired, 403, unauthorized | P1 | security-team |
| PAYMENT_FAILURE | payment, transaction, gateway, checkout | P1 | payments-team |
| SCALING | hpa, autoscaler, scaling failed, insufficient capacity | P2 | platform-team |
| OBSERVABILITY | elasticsearch, elk, kibana, split brain | P2 | observability-team |
| CICD_FAILURE | pipeline, deploy failed, argocd, sync failed | P2 | platform-team |
| DATABASE | database, postgres, connection pool, deadlock | P2 | dba-team |
| PERFORMANCE | high latency, timeout, p99, slo breach, 5xx | P2 | platform-team |
| GENERAL | (no match) | P3 | platform-team |

## CLI Usage

```bash
# One-shot from JSON string
python -m incident_triage.main \
  --payload '{"id":"INC-001","title":"OOM kill on payment-api","environment":"production","service":"payment-api"}' \
  --slack-webhook https://hooks.slack.com/services/YOUR/WEBHOOK/URL

# From JSON file
python -m incident_triage.main \
  --payload-file incident.json \
  --slack-webhook $SLACK_WEBHOOK_URL \
  --pd-routing-key $PAGERDUTY_ROUTING_KEY

# Dry run — print Slack message without sending
python -m incident_triage.main \
  --payload '{"title":"Node not ready"}' \
  --dry-run

# JSON output
python -m incident_triage.main \
  --payload '{"title":"HPA at max"}' \
  --dry-run --output json
```

## Webhook Server Mode

```bash
# Start server on port 8080
python -m incident_triage.main --serve --port 8080

# Send test webhook
curl -X POST http://localhost:8080 \
  -H "Content-Type: application/json" \
  -d '{"id":"INC-002","title":"Vault auth failed","environment":"production","service":"payment-api"}'
```

## Environment Variables

```bash
export SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...
export PAGERDUTY_ROUTING_KEY=your-routing-key
```

## Incident Payload Schema

```json
{
  "id": "INC-001",
  "title": "OOM kill on payment-api",
  "description": "Pod payment-api-abc123 was OOM killed",
  "environment": "production",
  "service": "payment-api",
  "duration_minutes": 5,
  "body": "additional context"
}
```
