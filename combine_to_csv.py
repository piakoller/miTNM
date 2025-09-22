#!/usr/bin/env python3
"""
Combine patient text files and their generated miTNM JSON outputs into a CSV.

Default output (clear overview - 5 columns):
1) patient_id_age_sex   (e.g., "P001 | 67 | Male")
2) impression           (from the patient text)
3) clinical_summary     (from the patient text)
4) miTNM_signature      (formatted: "miT1 | miN0 | miM0")
5) rationale            (from the JSON)

Optional: --two-columns keeps the original simple layout with just patient_data and output_json.

Usage (Windows PowerShell):

# Single pair (clear overview)
py -3 .\combine_to_csv.py --patient-file .\patient_example.txt --json-file .\output.json --output-csv .\miTNM_summary.csv

# Batch by folder (clear overview)
py -3 .\combine_to_csv.py --patient-dir .\patients --pattern *.txt --json-dir .\outputs --output-csv .\miTNM_summary.csv

# Old format (two columns)
py -3 .\combine_to_csv.py --patient-dir .\patients --json-dir .\outputs --two-columns --output-csv .\miTNM_summary.csv

No external dependencies required (uses Python stdlib).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
import re
from typing import List, Optional, Tuple


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


def parse_json_fields(path: Optional[Path]) -> Tuple[str, str, str, float, str]:
    """Return normalized fields from miTNM JSON: (miT, miN, miM, confidence, rationale)."""
    if not path or not path.exists():
        return ("unknown", "unknown", "unknown", 0.0, "JSON missing")
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return ("unknown", "unknown", "unknown", 0.0, f"JSON parse error: {e}")
    sig = obj.get("miTNM_signature") or {}
    miT = str(sig.get("miT", "unknown") or "unknown").strip()
    miN = str(sig.get("miN", "unknown") or "unknown").strip()
    miM = str(sig.get("miM", "unknown") or "unknown").strip()
    try:
        conf = float(obj.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, conf))
    except Exception:
        confidence = 0.0
    rationale = str(obj.get("rationale", "")).strip()
    return (miT, miN, miM, confidence, rationale)


def write_csv(rows: List[List[str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Use newline='' to avoid extra blank lines on Windows
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["patient_data", "output_json"])  # header
        for row in rows:
            writer.writerow(row)


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Combine patient texts and miTNM JSON outputs into a CSV (clear overview by default)")
    # Single pair
    p.add_argument("--patient-file", help="Path to a single patient .txt file")
    p.add_argument("--json-file", help="Path to the matching JSON output file")
    # Batch mode
    p.add_argument("--patient-dir", help="Directory containing patient .txt files (batch mode)")
    p.add_argument("--pattern", default="*.txt", help="Glob pattern for patient files (default: *.txt)")
    p.add_argument("--json-dir", help="Directory containing JSON outputs (optional)")
    p.add_argument("--output-csv", default="miTNM_summary.csv", help="Path to write the CSV summary")
    p.add_argument("--two-columns", action="store_true", help="Write the legacy two-column CSV (patient_data, output_json)")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    rows: List[List[str]] = []

    def to_two_col(pf: Path, jf: Optional[Path]) -> List[str]:
        return [read_text(pf), read_json_str(jf)]

    def parse_patient_overview(text: str) -> Tuple[str, str, str, str, str]:
        """Extract patient overview fields: id_age_sex, impression, clinical_summary, signature (placeholder), rationale (placeholder)."""
        pid = age = sex = ""
        clinical_lines: List[str] = []
        impression_lines: List[str] = []
        section = "header"
        for raw in text.splitlines():
            line = raw.strip()
            low = line.lower()
            if low == "clinical summary:" or low == "clinical summary":
                section = "clinical"
                continue
            if low == "impression:" or low == "impression":
                section = "impression"
                continue
            if section == "header":
                m = re.match(r"^patient id:\s*(.+)$", line, re.IGNORECASE)
                if m:
                    pid = m.group(1).strip()
                    continue
                m = re.match(r"^age:\s*(.+)$", line, re.IGNORECASE)
                if m:
                    age = m.group(1).strip()
                    continue
                m = re.match(r"^sex:\s*(.+)$", line, re.IGNORECASE)
                if m:
                    sex = m.group(1).strip()
                    continue
            elif section == "clinical":
                clinical_lines.append(raw)
            elif section == "impression":
                impression_lines.append(raw)
        id_age_sex = " | ".join([x for x in [pid, age, sex] if x])
        clinical_txt = "\n".join(clinical_lines).strip()
        impression_txt = "\n".join(impression_lines).strip()
        return (id_age_sex, impression_txt, clinical_txt, "", "")

    def to_overview_row(pf: Path, jf: Optional[Path]) -> List[str]:
        text = read_text(pf)
        id_age_sex, impression, clinical, _, _ = parse_patient_overview(text)
        miT, miN, miM, _conf, rationale = parse_json_fields(jf)
        signature_disp = " | ".join([miT, miN, miM])
        return [id_age_sex, impression, clinical, signature_disp, rationale]

    if args.patient_file and args.json_file:
        pf = Path(args.patient_file)
        jf = Path(args.json_file)
        rows.append(to_two_col(pf, jf) if args.two_columns else to_overview_row(pf, jf))
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
            rows.append(to_two_col(pf, jf) if args.two_columns else to_overview_row(pf, jf))
        if not rows:
            sys.exit("No patient files found to process.")
    else:
        # Convenience default: if patient_example.txt and output.json exist
        pf = Path("patient_example.txt")
        jf = Path("output.json")
        if pf.exists() and jf.exists():
            rows.append(to_two_col(pf, jf) if args.two_columns else to_overview_row(pf, jf))
        else:
            sys.exit("Provide either --patient-file and --json-file, or --patient-dir.")

    out_path = Path(args.output_csv)
    if args.two_columns:
        write_csv(rows, out_path)
    else:
        header = [
            "patient_id_age_sex",
            "impression",
            "clinical_summary",
            "miTNM_signature",
            "rationale",
        ]
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
    print(f"Wrote CSV: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
