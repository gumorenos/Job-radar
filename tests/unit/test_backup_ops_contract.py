from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_backup_creates_checksum_and_runs_restore_verification() -> None:
    script = (ROOT / "ops" / "backup.sh").read_text()

    assert "sha256sum" in script
    assert ".dump.sha256" in script
    assert "ops/verify_backup.sh" in script
    assert "Retention days must be a non-negative integer." in script
    assert "BACKUP_OK" in script


def test_backup_verifier_restores_into_disposable_database() -> None:
    script = (ROOT / "ops" / "verify_backup.sh").read_text()

    assert "sha256sum --check --status" in script
    assert "createdb" in script
    assert "pg_restore --exit-on-error" in script
    assert "dropdb" in script
    assert "SELECT version_num FROM alembic_version" in script
    assert "candidate_profiles" in script
    assert "ingestion_events" in script
    assert "job_postings" in script
    assert "match_analyses" in script
    assert "BACKUP_VERIFY_OK" in script
