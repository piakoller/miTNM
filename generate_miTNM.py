#!/usr/bin/env python3
"""
Generate miTNM signatures from patient data using a local Ollama model.

This script automatically processes all patient files in the 'patients/' directory
and saves the results to the 'outputs/' directory. Patient file paths are hardcoded
in the script - no need to specify them as command-line arguments.

Hardcoded paths:
- Patient files: patients/*.txt
- Output files: outputs/*.json

Requires: Ollama running locally (http://localhost:11434) and `requests`.
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
    # Try different encodings to handle various file formats
    encodings = ['utf-8', 'windows-1252', 'iso-8859-1', 'cp1252']
    
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding).strip()
        except UnicodeDecodeError:
            continue
        except FileNotFoundError:
            sys.exit(f"Error: file not found: {path}")
        except Exception as e:
            sys.exit(f"Error reading {path}: {e}")
    
    # If all encodings fail
    sys.exit(f"Error: Could not decode {path} with any supported encoding: {encodings}")


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
        # Remove format=json constraint as gpt-oss:latest doesn't support it properly
        # "format": "json",
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
    # Without format=json, content may contain JSON within text
    try:
        content = data.get("message", {}).get("content", "").strip()
        
        # Try to parse as direct JSON first
        try:
            parsed = json.loads(content) if content else {}
        except json.JSONDecodeError:
            # If that fails, try to extract JSON from within the text
            import re
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                parsed = json.loads(json_str)
            else:
                # Fallback: if no JSON found, return empty dict
                parsed = {}
                
    except json.JSONDecodeError as e:
        # Final fallback: if all parsing fails
        text = data.get("message", {}).get("content", "")
        hint = text[:400].replace("\n", " ")
        print(f"Warning: Model did not return valid JSON. Using fallback values.")
        print(f"First 400 chars: {hint}")
        parsed = {}
        
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


def normalize_output(obj: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    # Ensure required keys exist
    sig = obj.get("miTNM_signature") or {}
    miT = str(sig.get("miT", "unknown")).strip() or "unknown"
    miN = str(sig.get("miN", "unknown")).strip() or "unknown"
    miM = str(sig.get("miM", "unknown")).strip() or "unknown"
    conf = obj.get("confidence")
    try:
        confidence = float(conf) if conf is not None else 0.0
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))
    except Exception:
        confidence = 0.0
    rationale = str(obj.get("rationale", "")).strip()
    return {
        "miTNM_signature": {"miT": miT, "miN": miN, "miM": miM},
        "confidence": confidence,
        "rationale": rationale,
        "model_used": model_name,
    }


def parse_args(argv: List[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate miTNM signature using Ollama")
    p.add_argument("--model", default="gpt-oss:latest", help="Ollama model name (e.g., gpt-oss:latest, llama3.1)")
    p.add_argument("--prompt-file", default="prompt.txt", help="Path to instruction prompt text file")
    p.add_argument("--endpoint", default="http://localhost:11434", help="Ollama endpoint base URL")
    p.add_argument("--temperature", type=float, default=0.1, help="Sampling temperature")
    p.add_argument("--timeout", type=int, default=120, help="HTTP timeout in seconds")
    # Note: patient file paths are now hardcoded in the script
    return p.parse_args(argv)


def main(argv: List[str]) -> int:
    args = parse_args(argv)

    # Hardcoded paths - modify these as needed
    PATIENT_DIR = Path("PSMA-anonym/PSMA-anonym")
    OUTPUT_DIR = Path("outputs")
    FILE_PATTERN = "*.txt"
    
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
        return normalize_output(raw, args.model)

    # Check if patient directory exists
    if not PATIENT_DIR.is_dir():
        sys.exit(f"Error: Patient directory not found: {PATIENT_DIR}")

    # Find all patient files
    files = sorted(PATIENT_DIR.glob(FILE_PATTERN))
    if not files:
        sys.exit(f"No files matched pattern '{FILE_PATTERN}' in {PATIENT_DIR}")

    print(f"Found {len(files)} patient files in {PATIENT_DIR}")
    
    # Create output directory if it doesn't exist
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    processed = 0
    failures: List[str] = []
    
    for fp in files:
        print(f"Processing: {fp.name}")
        try:
            patient_text = read_text_file(fp)
        except Exception as e:
            failures.append(f"{fp.name}: read error: {e}")
            continue
        try:
            result = generate_for_text(patient_text)
            out_json = json.dumps(result, ensure_ascii=False, indent=2)
            target = OUTPUT_DIR / (fp.stem + ".json")
            target.write_text(out_json + "\n", encoding="utf-8")
            print(f"Saved: {target}")
            processed += 1
        except SystemExit as e:
            # call_ollama_json may sys.exit on API errors; capture per-file
            failures.append(f"{fp.name}: {e}")
        except Exception as e:
            failures.append(f"{fp.name}: {e}")

    # Summary
    print(f"\nDone. Processed {processed}/{len(files)} files.")
    if failures:
        print("Failures:")
        for f in failures:
            print(f" - {f}")
    return 0 if processed > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
