# devops-python-scripts

Production-grade Python automation scripts for Kubernetes platform operations,
HashiCorp Vault secret management, and incident triage. Built and used at
BNY Mellon supporting 100+ microservices on AWS EKS in a SOX-regulated environment.

[![Test](https://github.com/Vikas-DevOps-Git/devops-python-scripts/actions/workflows/test.yml/badge.svg)](https://github.com/Vikas-DevOps-Git/devops-python-scripts/actions/workflows/test.yml)

---

## Scripts

| Script | Purpose | Key Capabilities |
|---|---|---|
| `eks_health_check` | EKS cluster health reporter | Node readiness, OOM events, HPA capacity, restart counts, pending pods |
| `vault_rotation` | Vault lease renewal orchestrator | Kubernetes auth, lease scanning, threshold-based renewal, dry run |
| `incident_triage` | Incident classifier and notifier | Keyword classification, Slack Block Kit messages, PagerDuty trigger, webhook server |

---

## Quick Start

```bash
# Install
git clone https://github.com/Vikas-DevOps-Git/devops-python-scripts.git
cd devops-python-scripts
pip install -r requirements.txt
pip install -e .

# Run all smoke tests
make smoke

# Run unit tests
make test
```

---

## eks_health_check

Reports health status of an EKS cluster — designed for CI/CD health gates
and on-call triage. Exit code 1 if DEGRADED.

```bash
# Text report
python -m eks_health_check.main --namespace finance

# JSON output for monitoring integration
python -m eks_health_check.main --namespace finance --output json | jq .summary

# Custom restart threshold
python -m eks_health_check.main --namespace finance --restart-threshold 3
```

**Example output:**
```
=======================================================
  EKS Health Report — 2025-04-16T10:30:00+00:00
=======================================================
  Namespace          : finance
  Nodes              : 5 total, 0 unhealthy
  Deployments        : 4 total, 0 unhealthy
  OOM Events (last hr): 0
  HPAs at max        : 0
  Restart alerts     : 1
  Pending pods       : 0
  Overall status     : DEGRADED
=======================================================

  Restart Alerts:
    - payment-api-abc123/app: 6 restarts (last: OOMKilled)
```

**What it checks:**
- Node Ready condition across all nodes
- Deployment readyReplicas vs desiredReplicas
- OOM events in the last 60 minutes (configurable)
- HPA currentReplicas vs maxReplicas — alerts when at max
- Container restart counts above threshold (default: 5)
- Pods stuck in Pending phase with condition details

---

## vault_rotation

Renews Vault leases expiring within a configurable threshold.
Supports Kubernetes ServiceAccount JWT auth (in-cluster),
static token (dev), and AppRole.

```bash
# Dry run — see what would be renewed
python -m vault_rotation.main \
  --vault-addr http://localhost:8200 \
  --vault-token root \
  --threshold-hours 24 \
  --dry-run

# Production — Kubernetes auth
python -m vault_rotation.main \
  --vault-addr http://vault.vault.svc.cluster.local:8200 \
  --k8s-role bny-app-role \
  --lease-prefixes database/creds/ aws/creds/ pki/issue/ \
  --threshold-hours 24

# Multiple paths, JSON output, log to file
python -m vault_rotation.main \
  --lease-prefixes finance/ payments/ notifications/ \
  --output json \
  --log-file /var/log/vault-rotation.log
```

**Rotation report:**
```
=======================================================
  Vault Rotation Report — 2025-04-16T10:30:00+00:00
=======================================================
  Dry run          : False
  Paths scanned    : 3
  Leases renewed   : 47
  Leases skipped   : 5
  Failures         : 0
  Status           : SUCCESS
=======================================================
```

---

## incident_triage

Classifies incidents by keyword, routes to the correct team, and sends
formatted Slack messages with severity and runbook links.
Runs as CLI one-shot or persistent HTTP webhook server.

```bash
# One-shot — OOM incident
python -m incident_triage.main \
  --payload '{"id":"INC-001","title":"OOM kill on payment-api","environment":"production"}' \
  --slack-webhook $SLACK_WEBHOOK_URL

# Dry run — preview Slack message
python -m incident_triage.main \
  --payload '{"title":"Node not ready on node-3"}' \
  --dry-run

# Webhook server — receives Alertmanager/PagerDuty webhooks
python -m incident_triage.main --serve --port 8080
```

**Classification categories:**

| Severity | Categories |
|---|---|
| P1 | OOM_KILL, NODE_FAILURE, SECURITY, PAYMENT_FAILURE |
| P2 | SCALING, OBSERVABILITY, CICD_FAILURE, DATABASE, PERFORMANCE |
| P3 | GENERAL (no keyword match) |

---

## Project Structure

```
devops-python-scripts/
├── eks_health_check/
│   ├── __init__.py
│   ├── checker.py          # Core check logic — dependency-injected for testability
│   └── main.py             # CLI entry point
├── vault_rotation/
│   ├── __init__.py
│   ├── client.py           # Vault auth and lease operations
│   ├── rotator.py          # Rotation orchestration logic
│   └── main.py             # CLI entry point
├── incident_triage/
│   ├── __init__.py
│   ├── classifier.py       # Keyword-based incident classifier
│   ├── notifier.py         # Slack Block Kit and PagerDuty helpers
│   └── main.py             # CLI + webhook server entry point
├── tests/
│   └── unit/
│       ├── test_eks_health_check.py
│       ├── test_incident_classifier.py
│       └── test_vault_rotator.py
├── docs/
│   ├── eks-health-check.md
│   ├── vault-rotation.md
│   └── incident-triage.md
├── .github/workflows/
│   ├── test.yml            # Test matrix Python 3.9, 3.10, 3.11
│   └── security.yml        # Trivy + pip-audit
├── requirements.txt
├── requirements-dev.txt
├── setup.py
├── Makefile
└── .env.example
```

---

## Running Tests

```bash
# All unit tests with coverage
make test

# Lint
make lint

# Format
make format

# Smoke tests (no cluster or Vault needed)
make smoke
```

---

## CI/CD Pipeline

| Trigger | Workflow | Stages |
|---|---|---|
| Push / PR to main | test.yml | pytest (3.9, 3.10, 3.11) → coverage → flake8 → black → smoke tests |
| Push to main / weekly | security.yml | Trivy filesystem scan → pip-audit CVE check |

---

## Design Principles

**Dependency injection for testability**
eks_health_check.checker.EKSHealthChecker accepts API client objects as constructor
arguments — mock clients can be injected in tests without patching globals.

**Separation of concerns**
Each script is split into logic module (checker.py, rotator.py, classifier.py)
and CLI entry point (main.py) — logic can be imported without triggering CLI parsing.

**Exit code contracts**
All scripts exit 0 on success and 1 on any error or degraded state —
designed for CI/CD health gate integration.

**Dry run everywhere**
All scripts support --dry-run to preview actions without making changes —
safe to test in production read-only mode.

---

## Author

Vikas Dhamija — Senior DevOps Engineer | VP Platform Engineering, BNY Mellon
GitHub: https://github.com/Vikas-DevOps-Git
