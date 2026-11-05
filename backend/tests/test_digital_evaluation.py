import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import evaluate_digital_samples as evaluator


def test_digital_manifest_reports_error_metrics_and_exact_matches(monkeypatch, tmp_path):
    sample = tmp_path / "display.png"
    sample.write_bytes(b"sample-placeholder")
    manifest = tmp_path / "manifest.csv"
    manifest.write_text(
        "image,expected_value,unit\n"
        "display.png,72.5,C\n"
        "display.png,,C\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        evaluator,
        "read_digital_display",
        lambda image: {
            "value": 72.5,
            "raw_text": "72.5",
            "confidence": 93.0,
        },
    )

    report = evaluator.evaluate_manifest(manifest)

    assert report["sample_count"] == 2
    metrics = report["accuracy_metrics"]
    assert metrics["count"] == 1
    assert metrics["mae"] == 0
    assert metrics["rmse"] == 0
    assert metrics["exact_match_percent"] == 100
    assert report["results"][1]["validation"].startswith("ground truth not supplied")


def test_digital_manifest_rejects_missing_required_columns(tmp_path):
    manifest = tmp_path / "bad.csv"
    manifest.write_text("file,reading\n", encoding="utf-8")
    try:
        evaluator.evaluate_manifest(manifest)
    except ValueError as exc:
        assert "image,expected_value" in str(exc)
    else:
        raise AssertionError("Expected invalid manifest to be rejected")
