from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_status_records_localhost_baseline_and_pending_gates() -> None:
    status = (ROOT / "docs" / "production-status.md").read_text()

    assert "f831c7250820e8afd9c250cc69d5a98fa8cbb77c" in status
    assert "20260901_0007 (head)" in status
    assert "BACKUP_VERIFY_OK" in status
    assert "BACKUP_OK" in status
    assert "127.0.0.1:8010" in status
    assert "127.0.0.1:5432" in status
    assert "Real post-cutoff dual-write burn-in remains unconfirmed" in status
    assert "No public Job Radar hostname" in status
    assert "Telegram production delivery remains disabled/unconfirmed" in status
