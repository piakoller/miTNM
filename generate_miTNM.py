#!/usr/bin/env python3
"""
Generate a miTNM signature from patient data using a local Ollama model.

Reads an instruction prompt and a patient text file, calls Ollama's chat API
with JSON formatting, and prints/saves a structured miTNM signature.

Requires: Ollama running locally (http://localhost:11434).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import urllib.request
import urllib.error


def read_text_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        sys.exit(f"Error: file not found: {path}")
    except Exception as e:
        sys.exit(f"Error reading {path}: {e}")


def call_ollama_json(
    *,
    model: str,
    messages: List[Dict[str, str]],
    endpoint: str,
    temperature: float,
    timeout: int,
) -> Dict[str, Any]:
    url = endpoint.rstrip("/") + "/api/chat"
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "format": "json",
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }
    data: Dict[str, Any]
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            body = resp.read().decode("utf-8", errors="replace")
        if status != 200:
            # Try to show Ollama's error message if present
            try:
                err = json.loads(body)
            except Exception:
                err = body
            sys.exit(f"Ollama HTTP {status}: {err}")
        try:
            data = json.loads(body)
        except Exception as e:
            sys.exit(f"Error parsing Ollama response as JSON: {e}\nBody start: {body[:400]}")
    except urllib.error.URLError as e:
        sys.exit(
            "Error: Could not connect to Ollama. Is it running on "
            f"{endpoint}? Install/start Ollama and pull the model first. Details: {e}"
        )
    except Exception as e:
        sys.exit(f"Error calling Ollama: {e}")
    # With format=json, `message.content` should be a JSON string
    try:
        content = data.get("message", {}).get("content", "").strip()
        parsed = json.loads(content) if content else {}
    except json.JSONDecodeError as e:
        # Fallback: if the model didn't obey JSON, try to extract fenced JSON
        text = data.get("message", {}).get("content", "")
        hint = text[:400].replace("\n", " ")
        sys.exit(
            "Model did not return valid JSON. "
            f"First 400 chars: {hint}\nDetails: {e}"
        )
    return parsed if isinstance(parsed, dict) else {"result": parsed}


def build_system_prompt() -> str:
    return (
        "You are a clinical NLP assistant. Read the patient report and assign an "
        "miTNM signature. Output ONLY valid JSON with this schema: "
        "{\n"
        "  \"miTNM_signature\": {\n"
        "    \"miT\": \"string\",  // tumor (e.g., miT0, miT1, miT2, miT3, miT4, miTX, unknown)\n"
        "    \"miN\": \"string\",  // nodes (e.g., miN0, miN1, miN2, miNX, unknown)\n"
        "    \"miM\": \"string\"   // metastasis (e.g., miM0, miM1, miMX, unknown)\n"
        "  },\n"
        "  \"confidence\": 0.0,       // 0.0 to 1.0\n"
        "  \"rationale\": \"string\" // brief justification using patient evidence\n"
        "}\n"
        "Rules: If evidence is insufficient, use 'unknown' (not guessed). "
        "Be concise and evidence-based. Do not include any text outside JSON."
    )


def compose_user_message(instruction: str, patient_text: str) -> str:
    return (
        "Task Instruction:\n" + instruction.strip() + "\n\n" +
        "Patient Data (between <<< >>>):\n" +
        "<<<\n" + patient_text.strip() + "\n>>>\n"
    )


def normalize_output(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure required keys exist
    sig = obj.get("miTNM_signature") or {}
    miT = str(sig.get("miT", "unknown")).strip() or "unknown"
    miN = str(sig.get("miN", "unknown")).strip() or "unknown"
    miM = str(sig.get("miM", "unknown")).strip() or "unknown"
    conf = obj.get("confidence")
    try:
        confidence = float(conf)
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))
    except Exception:
        confidence = 0.0
    rationale = str(obj.get("rationale", "")).strip()
    return {
        "miTNM_signature": {"miT": miT, "miN": miN, "miM": miM},
        "confidence": confidence,
        "rationale": rationale,
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate miTNM signature using Ollama")
    p.add_argument("--model", default="gpt-oss:latest", help="Ollama model name (e.g., gpt-oss:latest)")
    p.add_argument("--prompt-file", default="prompt.txt", help="Path to instruction prompt text file")
    # Single-file mode
    p.add_argument("--patient-file", default=None, help="Path to a single patient data text file")
    # Batch mode
    p.add_argument("--patient-dir", help="Directory containing patient text files (batch mode)")
    p.add_argument("--pattern", default="*.txt", help="Glob pattern for patient files in --patient-dir (default: *.txt)")
    p.add_argument("--endpoint", default="http://localhost:11434", help="Ollama endpoint base URL")
    p.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    p.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds")
    # Outputs
    p.add_argument("--output", help="(Single-file mode) Path to write JSON output; prints to stdout if omitted")
    p.add_argument("--output-dir", help="(Batch mode) Directory to write JSON outputs; defaults to alongside each input file")
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    prompt_path = Path(args.prompt_file)
    instruction = read_text_file(prompt_path)
    system_prompt = build_system_prompt()

    def generate_for_text(patient_text: str) -> Dict[str, Any]:
        user_msg = compose_user_message(instruction, patient_text)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ]
        raw = call_ollama_json(
            model=args.model,
            messages=messages,
            endpoint=args.endpoint,
            temperature=args.temperature,
            timeout=args.timeout,
        )
        return normalize_output(raw)

    # Batch mode
    if args.patient_dir:
        patient_dir = Path(args.patient_dir)
        if not patient_dir.is_dir():
            sys.exit(f"Error: --patient-dir not found or not a directory: {patient_dir}")

        files = sorted(patient_dir.glob(args.pattern))
        if not files:
            sys.exit(f"No files matched pattern '{args.pattern}' in {patient_dir}")

        out_dir = Path(args.output_dir) if args.output_dir else None
        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)

        processed = 0
        failures: List[str] = []
        for fp in files:
            try:
                patient_text = fp.read_text(encoding="utf-8").strip()
            except Exception as e:
                failures.append(f"{fp.name}: read error: {e}")
                continue
            try:
                result = generate_for_text(patient_text)
                out_json = json.dumps(result, ensure_ascii=False, indent=2)
                target = (out_dir / (fp.stem + ".json")) if out_dir else fp.with_suffix(".json")
                target.write_text(out_json + "\n", encoding="utf-8")
                print(f"Saved: {target}")
                processed += 1
            except SystemExit as e:
                # call_ollama_json may sys.exit on API errors; capture per-file
                failures.append(f"{fp.name}: {e}")
            except Exception as e:
                failures.append(f"{fp.name}: {e}")

        # Summary
        print(f"Done. Processed {processed}/{len(files)} files.")
        if failures:
            print("Failures:")
            for f in failures:
                print(f" - {f}")
        return 0 if processed > 0 else 1

    # Single-file mode (default)
    if not args.patient_file:
        # Provide a default only if neither patient-dir nor patient-file is given
        default_path = Path("patient_example.txt")
        if default_path.exists():
            args.patient_file = str(default_path)
        else:
            sys.exit("Provide --patient-file or --patient-dir.")

    patient_path = Path(args.patient_file)
    patient_text = read_text_file(patient_path)

    result = generate_for_text(patient_text)
    out_json = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(out_json + "\n", encoding="utf-8")
        print(f"Saved miTNM signature to {out_path}")
    else:
        print(out_json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
