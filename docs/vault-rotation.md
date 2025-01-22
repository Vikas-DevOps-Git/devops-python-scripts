# vault_rotation — Usage Guide

## Overview

Authenticates to HashiCorp Vault and renews leases expiring within
a configurable threshold. Supports Kubernetes auth (in-cluster),
static token (dev), and AppRole.

## Authentication Methods

### Kubernetes auth (in-cluster — production)
```bash
python -m vault_rotation.main \
  --vault-addr http://vault.vault.svc.cluster.local:8200 \
  --k8s-role bny-app-role \
  --threshold-hours 24
```

### Static token (local development)
```bash
python -m vault_rotation.main \
  --vault-addr http://localhost:8200 \
  --vault-token root \
  --dry-run
```

### AppRole
```bash
export VAULT_ROLE_ID=your-role-id
export VAULT_SECRET_ID=your-secret-id
python -m vault_rotation.main \
  --vault-addr http://vault:8200
```

## Options

| Flag | Default | Description |
|---|---|---|
| --vault-addr | http://localhost:8200 | Vault server URL |
| --k8s-role | None | Kubernetes auth role |
| --vault-token | None | Static token |
| --lease-prefixes | database/creds/ aws/creds/ pki/issue/ | Paths to scan |
| --threshold-hours | 24 | Renew if TTL below this |
| --increment-seconds | 3600 | Renewal increment |
| --dry-run | False | Preview without renewing |
| --output | text | text or json |
| --log-file | None | Write JSON report to file |

## Running as Kubernetes CronJob

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: vault-rotation
  namespace: finance
spec:
  schedule: "0 */6 * * *"  # Every 6 hours
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: vault-rotation-sa
          containers:
            - name: vault-rotation
              image: 123456789.dkr.ecr.us-east-1.amazonaws.com/vault-rotation:latest
              command:
                - python
                - -m
                - vault_rotation.main
                - --vault-addr
                - http://vault.vault.svc.cluster.local:8200
                - --k8s-role
                - bny-app-role
                - --threshold-hours
                - "24"
                - --output
                - json
          restartPolicy: OnFailure
```
