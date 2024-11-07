"""
Unit tests for vault_rotation.rotator
Uses mock VaultClient — no Vault server required.
"""
import pytest
from unittest.mock import MagicMock, call
from vault_rotation.rotator import LeaseRotator


def make_mock_client(leases=None, ttl_map=None, renew_success=True):
    """Create a mock VaultClient."""
    client = MagicMock()
    client.list_leases.return_value = leases or []
    client.lookup_lease_ttl.side_effect = lambda lid: (ttl_map or {}).get(lid, 99999)
    client.renew_lease.return_value = {
        "lease_id": "test",
        "status": "renewed" if renew_success else "failed",
        "new_ttl": 3600,
    }
    client.renew_self_token.return_value = 3600
    return client


class TestLeaseRotator:
    def test_renews_expiring_leases(self):
        leases = ["database/creds/lease-1", "database/creds/lease-2"]
        ttls = {"database/creds/lease-1": 1800, "database/creds/lease-2": 90000}
        client = make_mock_client(leases=leases, ttl_map=ttls)

        rotator = LeaseRotator(client, threshold_hours=24)
        report = rotator.run(["database/creds/"])

        # Only lease-1 should be renewed (TTL 1800 < 24h threshold)
        assert report["total_renewed"] == 1
        assert report["total_skipped"] == 1

    def test_dry_run_does_not_renew(self):
        leases = ["database/creds/lease-1"]
        ttls = {"database/creds/lease-1": 100}
        client = make_mock_client(leases=leases, ttl_map=ttls)

        rotator = LeaseRotator(client, threshold_hours=24, dry_run=True)
        report = rotator.run(["database/creds/"])

        client.renew_lease.assert_not_called()
        assert report["total_renewed"] == 0

    def test_failed_renewal_tracked(self):
        leases = ["database/creds/lease-bad"]
        ttls = {"database/creds/lease-bad": 100}
        client = make_mock_client(leases=leases, ttl_map=ttls, renew_success=False)

        rotator = LeaseRotator(client, threshold_hours=24)
        report = rotator.run(["database/creds/"])

        assert report["total_failed"] == 1
        assert report["status"] == "failed"

    def test_empty_prefix_returns_zero(self):
        client = make_mock_client(leases=[])
        rotator = LeaseRotator(client)
        report = rotator.run(["empty/path/"])

        assert report["total_renewed"] == 0
        assert report["total_skipped"] == 0

    def test_multiple_prefixes_scanned(self):
        client = make_mock_client(leases=[])
        rotator = LeaseRotator(client)
        report = rotator.run(["path1/", "path2/", "path3/"])

        assert report["paths_scanned"] == 3
        assert client.list_leases.call_count == 3

    def test_self_token_renewed_before_leases(self):
        client = make_mock_client()
        rotator = LeaseRotator(client)
        rotator.run(["database/"])

        client.renew_self_token.assert_called_once()
