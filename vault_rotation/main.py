#!/usr/bin/env python3
"""
vault_rotation/main.py — Vault lease renewal orchestrator CLI

Authenticates to Vault via Kubernetes auth (in-cluster) or token,
scans configured lease paths, and renews leases expiring within threshold.

Usage:
    # Dry run — show what would be renewed
    python -m vault_rotation.main --vault-addr http://vault:8200 --dry-run

    # Kubernetes auth (in-cluster)
    python -m vault_rotation.main --vault-addr http://vault:8200 --k8s-role bny-app-role

    # Token auth (local dev)
    python -m vault_rotation.main --vault-addr http://localhost:8200 --vault-token root

    # Multiple lease paths
    python -m vault_rotation.main --lease-prefixes finance/ payments/ notifications/

Exit codes:
    0 — all renewals succeeded
    1 — one or more renewals failed
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path

from vault_rotation.client import VaultClient
from vault_rotation.rotator import LeaseRotator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [vault_rotation] %(message)s"
)
log = logging.getLogger(__name__)

DEFAULT_LEASE_PREFIXES = [
    "database/creds/",
    "aws/creds/",
    "pki/issue/",
]


def setup_logging(log_file: str = None):
    """Configure file logging if path provided."""
    if not log_file:
        return
    fh = logging.FileHandler(log_file)
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [vault_rotation] %(message)s"
    ))
    logging.getLogger().addHandler(fh)
    log.info(f"Logging to file: {log_file}")


def authenticate(vault_client: VaultClient, args) -> bool:
    """Authenticate to Vault using configured method."""
    try:
        if args.k8s_role:
            jwt_path = args.k8s_jwt_path or "/var/run/secrets/kubernetes.io/serviceaccount/token"
            vault_client.auth_kubernetes(args.k8s_role, jwt_path)
        elif args.vault_token:
            vault_client.auth_token(args.vault_token)
        elif os.environ.get("VAULT_TOKEN"):
            vault_client.auth_token(os.environ["VAULT_TOKEN"])
        elif args.approle_role_id and args.approle_secret_id:
            vault_client.auth_approle(args.approle_role_id, args.approle_secret_id)
        else:
            log.error("No authentication method provided")
            return False

        if not vault_client.is_authenticated():
            log.error("Vault authentication failed")
            return False

        log.info("Vault authentication successful")
        return True

    except Exception as e:
        log.error(f"Authentication error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Vault Lease Renewal Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # Vault connection
    parser.add_argument("--vault-addr",
                        default=os.environ.get("VAULT_ADDR", "http://localhost:8200"),
                        help="Vault server address")
    parser.add_argument("--vault-namespace",
                        default=os.environ.get("VAULT_NAMESPACE", ""),
                        help="Vault enterprise namespace")

    # Auth methods
    parser.add_argument("--vault-token",
                        default=None,
                        help="Static Vault token (dev only)")
    parser.add_argument("--k8s-role",
                        default=None,
                        help="Vault Kubernetes auth role name")
    parser.add_argument("--k8s-jwt-path",
                        default=None,
                        help="Path to Kubernetes ServiceAccount JWT")
    parser.add_argument("--approle-role-id",
                        default=os.environ.get("VAULT_ROLE_ID"),
                        help="AppRole role_id")
    parser.add_argument("--approle-secret-id",
                        default=os.environ.get("VAULT_SECRET_ID"),
                        help="AppRole secret_id")

    # Rotation config
    parser.add_argument("--lease-prefixes",
                        nargs="+",
                        default=DEFAULT_LEASE_PREFIXES,
                        help="Vault lease path prefixes to scan")
    parser.add_argument("--threshold-hours",
                        type=int, default=24,
                        help="Renew leases expiring within N hours (default: 24)")
    parser.add_argument("--increment-seconds",
                        type=int, default=3600,
                        help="Lease renewal increment in seconds (default: 3600)")
    parser.add_argument("--dry-run",
                        action="store_true",
                        help="Show what would be renewed without making changes")

    # Output
    parser.add_argument("--output", default="text", choices=["text", "json"],
                        help="Output format (default: text)")
    parser.add_argument("--log-file",
                        default=None,
                        help="Write rotation log to file")
    args = parser.parse_args()

    setup_logging(args.log_file)

    # Connect to Vault
    vault_client = VaultClient(args.vault_addr, args.vault_namespace)

    if not authenticate(vault_client, args):
        sys.exit(1)

    # Run rotation
    rotator = LeaseRotator(
        vault_client=vault_client,
        threshold_hours=args.threshold_hours,
        increment_seconds=args.increment_seconds,
        dry_run=args.dry_run,
    )

    report = rotator.run(args.lease_prefixes)

    # Output
    if args.output == "json":
        print(json.dumps(report, indent=2))
    else:
        print(f"\n{'='*55}")
        print(f"  Vault Rotation Report — {report['timestamp']}")
        print(f"{'='*55}")
        print(f"  Dry run          : {report['dry_run']}")
        print(f"  Paths scanned    : {report['paths_scanned']}")
        print(f"  Leases renewed   : {report['total_renewed']}")
        print(f"  Leases skipped   : {report['total_skipped']}")
        print(f"  Failures         : {report['total_failed']}")
        print(f"  Status           : {report['status'].upper()}")
        print(f"{'='*55}\n")

    if args.log_file:
        import json as _json
        log_path = Path(args.log_file).with_suffix(".json")
        log_path.write_text(_json.dumps(report, indent=2))
        log.info(f"JSON report written to {log_path}")

    sys.exit(0 if report["status"] == "success" else 1)


if __name__ == "__main__":
    main()
