"""Evaluate RetroSense analog readings against a CSV of independently verified gauge values.

CSV columns: image,min_value,max_value,expected_value,unit,start_angle,end_angle
Blank expected_value rows are analysed but excluded from accuracy metrics.
Run from backend/: python evaluate_samples.py samples.csv
"""
import argparse
import csv
import json
import math
from pathlib import Path

from vision import read_analog_gauge, GaugeReadError


def calculate_metrics(errors):
    """Return MAE, RMSE and MAPE (%) for (predicted, expected) pairs."""
    if not errors:
        return {"count": 0, "mae": None, "rmse": None, "mape_percent": None}
    absolute = [abs(predicted - expected) for predicted, expected in errors]
    squared = [(predicted - expected) ** 2 for predicted, expected in errors]
    percentage = [
        abs(predicted - expected) / abs(expected) * 100
        for predicted, expected in errors
        if expected != 0
    ]
    return {
        "count": len(errors),
        "mae": round(sum(absolute) / len(absolute), 4),
        "rmse": round(math.sqrt(sum(squared) / len(squared)), 4),
        "mape_percent": round(sum(percentage) / len(percentage), 4) if percentage else None,
        "mape_excluded_zero_reference": len(errors) - len(percentage),
    }


def evaluate_manifest(manifest_path):
    manifest = Path(manifest_path)
    results = []
    measured = []
    with manifest.open(newline="", encoding="utf-8-sig") as handle:
        rows = csv.DictReader(handle)
        required = {"image", "min_value", "max_value", "expected_value"}
        if not rows.fieldnames or not required.issubset(set(rows.fieldnames)):
            raise ValueError("CSV must include: image,min_value,max_value,expected_value")

        for line_number, row in enumerate(rows, start=2):
            image_path = Path(row["image"])
            if not image_path.is_absolute():
                image_path = manifest.parent / image_path
            item = {"row": line_number, "image": str(image_path)}
            try:
                if not image_path.is_file():
                    raise ValueError("Image file not found")
                raw = image_path.read_bytes()
                result = read_analog_gauge(
                    raw,
                    float(row["min_value"]),
                    float(row["max_value"]),
                    float(row.get("start_angle") or 135),
                    float(row.get("end_angle") or 45),
                )
                item.update({
                    "predicted_value": result["value"],
                    "unit": row.get("unit") or "",
                    "confidence": result["confidence"],
                })
                expected_text = (row.get("expected_value") or "").strip()
                if expected_text:
                    expected = float(expected_text)
                    error = result["value"] - expected
                    item.update({
                        "expected_value": expected,
                        "absolute_error": round(abs(error), 4),
                    })
                    measured.append((result["value"], expected))
                else:
                    item["validation"] = "ground truth not supplied; excluded from metrics"
            except (GaugeReadError, ValueError, OSError) as exc:
                item["error"] = str(exc)
            results.append(item)

    return {
        "manifest": str(manifest),
        "sample_count": len(results),
        "accuracy_metrics": calculate_metrics(measured),
        "results": results,
        "warning": "Metrics are meaningful only when expected_value is independently verified and all samples use correctly calibrated dial ranges and angles.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", help="CSV file describing gauge images and reference values")
    parser.add_argument("--output", help="Optional JSON report path")
    args = parser.parse_args()
    report = evaluate_manifest(args.manifest)
    rendered = json.dumps(report, indent=2)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
