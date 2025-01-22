# eks_health_check — Usage Guide

## Overview

Runs health checks against a Kubernetes cluster and reports:
- Node readiness and resource availability
- Deployment replica availability
- OOM events in the last N minutes
- HPA capacity status (alerts when at max)
- Container restart counts above threshold
- Pods stuck in Pending state

## Installation

```bash
pip install -r requirements.txt
pip install -e .
```

## Usage

```bash
# Basic health check — text output
python -m eks_health_check.main --namespace finance

# JSON output for monitoring integration
python -m eks_health_check.main --namespace finance --output json

# Custom restart threshold
python -m eks_health_check.main --namespace finance --restart-threshold 3

# Longer OOM lookback window
python -m eks_health_check.main --namespace finance --lookback-minutes 120

# Use specific kubeconfig
KUBECONFIG=/path/to/kubeconfig python -m eks_health_check.main --namespace finance

# As entry point (after pip install -e .)
eks-health-check --namespace finance
```

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | HEALTHY — all checks passed |
| 1 | DEGRADED — one or more issues detected |

## Example Output (text)

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
    - payment-api-abc123/payment-api: 6 restarts (last: OOMKilled)
```

## CI/CD Integration

```yaml
# GitHub Actions health gate
- name: EKS Health Check
  run: |
    python -m eks_health_check.main --namespace finance
  # Exits 1 if DEGRADED — blocks pipeline
```
