"""
rotator.py — lease rotation orchestration logic
Scans lease paths, identifies expiring leases, renews or alerts.
"""
import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)


class LeaseRotator:
    """
    Orchestrates lease renewal across multiple Vault paths.
    """

    def __init__(self, vault_client, threshold_hours: int = 24,
                 increment_seconds: int = 3600, dry_run: bool = False):
        self.client = vault_client
        self.threshold_seconds = threshold_hours * 3600
        self.increment = increment_seconds
        self.dry_run = dry_run
        self.results = []

    def process_path(self, prefix: str) -> dict:
        """
        Scan all leases under prefix and renew those below threshold.
        Returns summary dict for this path.
        """
        leases = self.client.list_leases(prefix)
        log.info(f"Found {len(leases)} leases under '{prefix}'")

        renewed = 0
        skipped = 0
        failed = 0
        path_results = []

        for lease_id in leases:
            ttl = self.client.lookup_lease_ttl(lease_id)

            if ttl > self.threshold_seconds:
                log.debug(f"Lease {lease_id} TTL={ttl}s — above threshold, skipping")
                skipped += 1
                path_results.append({
                    "lease_id": lease_id,
                    "ttl": ttl,
                    "action": "skipped",
                })
                continue

            log.info(f"Lease {lease_id} TTL={ttl}s — below threshold, renewing")

            if self.dry_run:
                log.info(f"[DRY RUN] Would renew {lease_id}")
                path_results.append({
                    "lease_id": lease_id,
                    "ttl": ttl,
                    "action": "dry_run",
                })
                continue

            result = self.client.renew_lease(lease_id, self.increment)
            path_results.append({
                "lease_id": lease_id,
                "ttl_before": ttl,
                "new_ttl": result.get("new_ttl"),
                "action": result["status"],
            })

            if result["status"] == "renewed":
                renewed += 1
            else:
                failed += 1

        return {
            "prefix": prefix,
            "total": len(leases),
            "renewed": renewed,
            "skipped": skipped,
            "failed": failed,
            "leases": path_results,
        }

    def run(self, prefixes: list) -> dict:
        """
        Run rotation across all provided prefixes.
        Returns full rotation report.
        """
        log.info(
            f"Starting rotation — paths={len(prefixes)}, "
            f"threshold={self.threshold_seconds//3600}h, "
            f"dry_run={self.dry_run}"
        )

        # Renew self token first
        self.client.renew_self_token(increment=self.increment)

        path_reports = []
        total_renewed = 0
        total_failed = 0
        total_skipped = 0

        for prefix in prefixes:
            path_report = self.process_path(prefix)
            path_reports.append(path_report)
            total_renewed += path_report["renewed"]
            total_failed += path_report["failed"]
            total_skipped += path_report["skipped"]

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": self.dry_run,
            "paths_scanned": len(prefixes),
            "total_renewed": total_renewed,
            "total_failed": total_failed,
            "total_skipped": total_skipped,
            "status": "failed" if total_failed > 0 else "success",
            "path_reports": path_reports,
        }

        log.info(
            f"Rotation complete — renewed={total_renewed}, "
            f"skipped={total_skipped}, failed={total_failed}"
        )

        return report
