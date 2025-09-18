# miTNM signature generator (Ollama)

This repo contains a tiny Python script that reads an instruction prompt and a patient report, then calls a local Ollama model (default: gpt-oss:latest) to generate a structured miTNM signature as JSON.

## Requirements
- Windows, macOS, or Linux
- Ollama installed and running locally (defaults to http://localhost:11434)
- A pulled model (default recommended: `gpt-oss:latest`)
- Python 3.9+ (no external Python packages needed)

## Quick start (Windows PowerShell)

1. Install and start Ollama, then pull a model (example: gpt-oss:latest):

```powershell
ollama run gpt-oss:latest --prompt "Say hi" | Out-Null
```

2. (Optional) Create/activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Run with the sample files (defaults to gpt-oss:latest):

```powershell
python .\generate_miTNM.py --model gpt-oss:latest --prompt-file .\prompt.txt --patient-file .\patient_example.txt
```

The script prints JSON like:

```json
{
  "miTNM_signature": { "miT": "miT2", "miN": "miN0", "miM": "miM0" },
  "confidence": 0.78,
  "rationale": "3.2 cm primary lesion without nodal or distant metastasis on PET/CT."
}
```

4. Save to a file:

```powershell
python .\generate_miTNM.py --output .\output.json
```

## Custom inputs
- Edit `prompt.txt` to tweak instructions.
- Replace `patient_example.txt` with your own report.

## Notes
- The script uses Ollama's `/api/chat` with `format: "json"` to enforce valid JSON output.
- If the model returns non-JSON, the script exits with a helpful error. Try lowering temperature or adjusting the prompt.
- You can change the endpoint with `--endpoint` if Ollama runs elsewhere.

## Batch mode (process a folder)

Place patient `.txt` files under `./patients` (examples are included). Then run:

```powershell
python .\generate_miTNM.py `
  --model gpt-oss:latest `
  --prompt-file .\prompt.txt `
  --patient-dir .\patients `
  --pattern *.txt `
  --output-dir .\outputs
```

This writes one JSON per input (e.g., `patient1_T2N0M0.txt` -> `outputs/patient1_T2N0M0.json`) and prints a short summary.

## Create an Excel overview (summary)

You can combine patient reports and their miTNM JSON outputs into a single Excel file for easy review.

Install the Excel writer dependency if needed (it's already listed in `requirements.txt`):

```powershell
pip install -r .\requirements.txt
```

Single pair (one patient and one JSON):

```powershell
python .\combine_to_excel.py --patient-file .\patient_example.txt --json-file .\output.json --output-excel .\miTNM_summary.xlsx
```

Batch mode (match JSON files by filename stem):

```powershell
python .\combine_to_excel.py `
  --patient-dir .\patients `
  --pattern *.txt `
  --json-dir .\outputs `
  --output-excel .\miTNM_summary.xlsx
```

Notes
- The sheet includes: patient_file, json_file, miT, miN, miM, confidence, rationale, and a truncated patient_text (default 500 chars).
- You can include the full patient text by adding `--max-text-chars -1`.
- If a JSON is missing, the row will show `unknown` fields and a note in the rationale.

## How this works (for clinicians) 🩺

Goal: Turn a free‑text patient report into a standardized miTNM signature.

What you provide
- A plain text report (e.g., radiology, pathology, or clinical summary). We’ve included examples in `./patients`.
- A short instruction file (`prompt.txt`) that tells the assistant what to extract (we provide a sensible default).

What the script does
1) Reads your instruction and the report text.
2) Sends both to a local “language model” (LLM) via the Ollama app on your computer. Think of the LLM as a text assistant trained to read and summarize clinical facts.
3) The assistant is given strict instructions to return only a small, structured summary with three items: tumor (miT), lymph nodes (miN), and metastasis (miM), plus a brief rationale and a confidence score.
4) The script saves that small summary as a `.json` file (a simple data format) next to the input file or into the `outputs` folder.

What the output looks like
```json
{
  "miTNM_signature": {
    "miT": "miT2",
    "miN": "miN0",
    "miM": "miM0"
  },
  "confidence": 0.78,
  "rationale": "3.2 cm primary lesion; no nodal or distant metastasis reported on PET/CT."
}
```

How “confidence” is estimated
- This is a self‑reported score (0 to 1) from the assistant indicating how certain it is based on the text.
- Higher values usually mean the report contains clear, explicit statements (e.g., “no distant metastasis on PET/CT”). Lower values indicate limited or conflicting information.
- Treat this as guidance, not a probability. If needed, we can add a simple rubric or calculate confidence from explicit evidence flags for more consistency.

Privacy and where data goes
- By default, everything runs locally on your computer using Ollama. Your text is sent to the local model, not to the internet.
- If you change the `--endpoint` setting, make sure you are comfortable with the destination.

Limitations to keep in mind
- The assistant relies entirely on what’s written in the report you provide. If something is missing, it should return `"unknown"` for that component.
- It does not look up external records or guidelines; it only interprets the text you give it.
- Clinical judgment remains essential—this tool is an assistant, not a diagnostic device.

Customizing the behavior
- Edit `prompt.txt` to change instructions (for example, prefer certain modalities, or describe how to handle ambiguous language).
- Add your own patient files under `./patients` and re‑run the batch command.
- If you want stricter outputs (e.g., evidence flags or a specific confidence rubric), we can extend the output format and compute confidence in the script deterministically.

