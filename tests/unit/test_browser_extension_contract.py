import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTENSION = ROOT / "browser-extension"
WEB = ROOT / "app" / "web"


def test_manifest_v3_uses_click_scoped_capture_without_persistent_page_access() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text())

    assert manifest["manifest_version"] == 3
    assert set(manifest["permissions"]) == {"activeTab", "scripting", "storage"}
    assert "content_scripts" not in manifest
    assert "host_permissions" not in manifest
    assert "<all_urls>" not in json.dumps(manifest)
    assert set(manifest["optional_host_permissions"]) == {
        "http://127.0.0.1/*",
        "http://localhost/*",
        "https://*/*",
    }


def test_popup_requires_human_review_and_reuses_official_ingestion_api() -> None:
    popup = (EXTENSION / "popup.js").read_text()
    options = (EXTENSION / "options.js").read_text()

    assert 'human_reviewed_before_submit: true' in popup
    assert 'ingestion_source: "chrome_extension"' in popup
    assert '"/api/v1/ingestions/jobs"' in popup
    assert 'Idempotency-Key' in popup
    assert 'Authorization: `Bearer ${connection.apiKey}`' in popup
    assert '/result`' in popup
    assert 'func: capturePage' in popup
    assert 'document.querySelectorAll(\'script[type="application/ld+json"]\')' in popup
    assert 'url.protocol === "http:" && !localHost' in options
    assert "console.log" not in popup
    assert "console.log" not in options


def test_popup_exposes_review_fields_before_send() -> None:
    html = (EXTENSION / "popup.html").read_text()

    for element_id in (
        "jobTitle",
        "jobCompany",
        "jobLocation",
        "jobWorkMode",
        "jobSalary",
        "jobDescription",
        "sendCapture",
    ):
        assert f'id="{element_id}"' in html


def test_extension_result_links_to_a_stable_radar_job_deep_link() -> None:
    popup = (EXTENSION / "popup.js").read_text()
    index = (WEB / "index.html").read_text()
    deep_link = (WEB / "radar_deeplink.js").read_text()

    assert '/app/#/radar/${currentResult.job_id}' in popup
    assert '/app/radar_deeplink.js' in index
    assert "loadJobDetail(jobId)" in deep_link
    assert "^#\\/radar\\/" in deep_link
