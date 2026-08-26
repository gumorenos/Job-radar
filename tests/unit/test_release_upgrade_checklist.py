from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_upgrade_checklist_requires_verified_backup_before_migrations() -> None:
    checklist = (ROOT / "docs" / "release-upgrade-checklist.md").read_text()

    assert "BACKUP_VERIFY_OK" in checklist
    assert "BACKUP_OK" in checklist
    assert "before changing `JOB_RADAR_IMAGE` or running migrations" in checklist
    assert "Do not remove the existing OpenClaw -> Notion path" in checklist
    assert "Do not downgrade Alembic automatically" in checklist
