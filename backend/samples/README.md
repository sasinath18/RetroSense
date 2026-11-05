# Accuracy sample manifests

These CSV files are templates, not a validated dataset. Add your own instrument photos in this folder and edit the rows to match them.

## Analog gauges

Use `analog-manifest-template.csv`. For each image, provide:
- `min_value` and `max_value`: the dial's printed range.
- `start_angle` and `end_angle`: the image-coordinate angles corresponding to minimum and maximum. Defaults in the template are 135° and 45°; calibrate for the particular gauge and camera orientation.
- `expected_value`: a reading independently confirmed from the instrument or a trusted reference. Leave blank only when no verified reference is available.

Run from the `backend` directory:

```powershell
python evaluate_samples.py samples/analog-manifest-template.csv --output analog-report.json
```

## Digital displays

Use `digital-manifest-template.csv`. Fill in the independently verified `expected_value` for each display image.

```powershell
python evaluate_digital_samples.py samples/digital-manifest-template.csv --output digital-report.json
```

## Evaluation notes

- Do not use the model's own output as the expected value.
- Keep a mix of values across the full dial/display range.
- Include multiple lighting conditions, viewing angles, distances, glare levels and instrument models.
- Report failed detections as well as successful readings; do not silently discard failures.
- MAE, RMSE, MAPE and exact-match metrics are dataset-specific and do not certify instrument accuracy or safety.
