"""Evaluate digital-display OCR against independently verified readings.

CSV columns: image,expected_value,unit
Blank expected_value rows are analysed but excluded from accuracy metrics.
Run from backend/: python evaluate_digital_samples.py samples/digital-manifest.csv
"""
import argparse
import csv
import json
import math
from pathlib import Path

from digital_ocr import read_digital_display, DigitalReadError
from evaluate_samples import calculate_metrics


def evaluate_manifest(manifest_path):
    manifest = Path(manifest_path)
    results = []
    measured = []
    exact_matches = 0
    verified_count = 0

    with manifest.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        required = {"image", "expected_value"}
        if not rows.fieldnames or not required.issubset(set(rows.fieldnames)):
            raise ValueError("CSV must include: image,expected_value")

        for line_number, row in enumerate(rows, start=2):
            image_path = Path(row["image"])
            if not image_path.is_absolute():
                image_path = manifest.parent / image_path
            item = {"row": line_number, "image": str(image_path)}
            try:
                if not image_path.is_file():
                    raise ValueError("Image file not found")
                result = read_digital_display(image_path.read_bytes())
                item.update({
                    "predicted_value": result["value"],
                    "recognized_text": result["raw_text"],
                    "ocr_confidence": result["confidence"],
                    "unit": row.get("unit") or "",
                })
                expected_text = (row.get("expected_value") or "").strip()
                if expected_text:
                    expected = float(expected_text)
                    if not math.isfinite(expected):
                        raise ValueError("expected_value must be a finite number")
                    measured.append((float(result["value"]), expected))
                    verified_count += 1
                    matched = math.isclose(float(result["value"]), expected,
                                           rel_tol=0.0, abs_tol=1e-9)
                    exact_matches += int(matched)
                    item.update({
                        "expected_value": expected,
                        "absolute_error": round(abs(float(result["value"]) - expected), 4),
                        "exact_match": matched,
                    })
                else:
                    item["validation"] = (
                        "ground truth not supplied; excluded from accuracy metrics"
                    )
            except (DigitalReadError, ValueError, OSError) as exc:
                item["error"] = str(exc)
            results.append(item)

    metrics = calculate_metrics(measured)
    metrics["exact_match_percent"] = (
        round(exact_matches / verified_count * 100, 4)
        if verified_count else None
    )
    return {
        "manifest": str(manifest),
        "sample_count": len(results),
        "accuracy_metrics": metrics,
        "results": results,
        "warning": (
            "Metrics are meaningful only when expected_value is independently verified "
            "and images show the intended display clearly. OCR confidence is not "
            "measurement accuracy."
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="CSV describing digital display images and reference values")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()
    report = evaluate_manifest(args.manifest)
    rendered = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
