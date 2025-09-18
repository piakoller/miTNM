#!/usr/bin/env python3
"""
Combine patient text files and their generated miTNM JSON outputs into a two-column CSV.

CSV format:
- Column 1: patient_data (raw text)
- Column 2: output_json (the entire JSON string from the model)

Usage (Windows PowerShell):

# Single pair
python .\combine_to_csv.py --patient-file .\patient_example.txt --json-file .\output.json --output-csv .\miTNM_summary.csv

# Batch by folder (assumes JSON next to each patient .txt or in --json-dir/./outputs)
python .\combine_to_csv.py --patient-dir .\patients --pattern *.txt --json-dir .\outputs --output-csv .\miTNM_summary.csv

No external dependencies required (uses Python stdlib).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import List, Optional


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    except Exception as e:
        return f"<read error: {e}>"


def read_json_str(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return json.dumps({"error": "JSON missing"}, ensure_ascii=False)
    try:
        raw = path.read_text(encoding="utf-8")
        # Validate JSON and re-dump to ensure normalized JSON
        obj = json.loads(raw)
        return json.dumps(obj, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"JSON parse error: {e}"}, ensure_ascii=False)


def write_csv(rows: List[List[str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Use newline='' to avoid extra blank lines on Windows
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["patient_data", "output_json"])  # header
        for row in rows:
            writer.writerow(row)


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Combine patient texts and miTNM JSON outputs into a 2-column CSV")
    # Single pair
    p.add_argument("--patient-file", help="Path to a single patient .txt file")
    p.add_argument("--json-file", help="Path to the matching JSON output file")
    # Batch mode
    p.add_argument("--patient-dir", help="Directory containing patient .txt files (batch mode)")
    p.add_argument("--pattern", default="*.txt", help="Glob pattern for patient files (default: *.txt)")
    p.add_argument("--json-dir", help="Directory containing JSON outputs (optional)")
    p.add_argument("--output-csv", default="miTNM_summary.csv", help="Path to write the CSV summary")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    rows: List[List[str]] = []

    if args.patient_file and args.json_file:
        pf = Path(args.patient_file)
        jf = Path(args.json_file)
        rows.append([read_text(pf), read_json_str(jf)])
    elif args.patient_dir:
        pdir = Path(args.patient_dir)
        if not pdir.is_dir():
            sys.exit(f"Error: --patient-dir not found or not a directory: {pdir}")
        jdir = Path(args.json_dir) if args.json_dir else None
        files = sorted(pdir.glob(args.pattern))
        for pf in files:
            candidates = [pf.with_suffix('.json')]
            if jdir:
                candidates.append(jdir / (pf.stem + '.json'))
            # also consider default outputs directory
            default_outputs = Path("outputs")
            if default_outputs.exists():
                candidates.append(default_outputs / (pf.stem + '.json'))
            jf = next((c for c in candidates if c and c.exists()), None)
            rows.append([read_text(pf), read_json_str(jf)])
        if not rows:
            sys.exit("No patient files found to process.")
    else:
        # Convenience default: if patient_example.txt and output.json exist
        pf = Path("patient_example.txt")
        jf = Path("output.json")
        if pf.exists() and jf.exists():
            rows.append([read_text(pf), read_json_str(jf)])
        else:
            sys.exit("Provide either --patient-file and --json-file, or --patient-dir.")

    out_path = Path(args.output_csv)
    write_csv(rows, out_path)
    print(f"Wrote CSV: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
