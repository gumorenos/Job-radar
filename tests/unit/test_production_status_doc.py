from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_production_status_records_localhost_baseline_and_pending_gates() -> None:
    status = (ROOT / "docs" / "production-status.md").read_text()

    assert "7659e77d38a2a61ecc352b49d2481d86d788a5e5" in status
    assert "127.0.0.1:8010" in status
    assert "127.0.0.1:5432" in status
    assert "real dual-write burn-in remains unconfirmed" in status
    assert "No public Job Radar hostname" in status
    assert "Telegram production delivery remains disabled/unconfirmed" in status
