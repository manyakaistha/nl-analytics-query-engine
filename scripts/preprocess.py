#!/usr/bin/env python3
"""
Preprocessing script for the Intelligent Analytics Query Engine.

Cleans malformed data files exported from spreadsheet tools:
  - UTF-8 BOM removal
  - Carriage return (\\r) normalization
  - JSON: lines wrapped in outer quotes with doubled internal quotes
  - CSV: entire rows wrapped as a single quoted string

Reads from  data/
Writes to   data/processed/

Usage:
    uv run python scripts/preprocess.py
"""

import csv
import io
import json
import sys
from pathlib import Path


# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "data"
PROCESSED_DIR = RAW_DATA_DIR / "processed"
REQUIRED_FILES = (
    "data_dictionary.json",
    "nl_queries.json",
    "sales_data.csv",
    "targets.csv",
)


def ensure_processed_data() -> None:
    """Create generated inputs on a fresh clone, without replacing existing files."""
    missing = [name for name in REQUIRED_FILES if not (PROCESSED_DIR / name).is_file()]
    if not missing:
        return

    sources = {
        "data_dictionary.json": "data_dictionary.json",
        "nl_queries.json": "nl_queries_curated.json",
        "sales_data.csv": "sales_data.csv",
        "targets.csv": "targets.csv",
    }
    for name in missing:
        source = RAW_DATA_DIR / sources[name]
        if not source.is_file():
            raise FileNotFoundError(
                f"Missing project data/{sources[name]}; restore the source file "
                "or run `uv run python scripts/preprocess.py` after adding it."
            )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    for name in missing:
        source = RAW_DATA_DIR / sources[name]
        destination = PROCESSED_DIR / name
        if name.endswith(".json"):
            process_json_file(source, destination)
        else:
            process_csv_file(source, destination)


def _normalize_text(raw: str) -> str:
    """Strip BOM and normalize line endings to \\n."""
    if raw.startswith("\ufeff"):
        raw = raw[1:]
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    return raw


def clean_malformed_json(raw_text: str) -> dict | list:
    """
    Parse JSON that has been corrupted by spreadsheet export.

    Common pattern (from Google Sheets / Excel CSV re-export):
      - Some lines are wrapped in outer double-quotes
      - Internal double-quotes are doubled ("")
      - Structural lines ({, }, [, ]) are left unquoted
      - File may have BOM and \\r line endings

    Strategy:
      1. Normalize encoding artefacts (BOM, CRLF)
      2. For each line: if it's wrapped in outer quotes, unwrap and
         un-double internal quotes
      3. Re-join and parse as JSON
    """
    text = _normalize_text(raw_text)

    # Fast path: already valid
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Slow path: fix per-line quoting
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Detect the pattern:  "    ""key"": ""value"","
        # The line starts AND ends with a double-quote
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 2:
            inner = stripped[1:-1]            # peel outer quotes
            inner = inner.replace('""', '"')  # un-double internal quotes
            cleaned_lines.append(inner)
        else:
            cleaned_lines.append(stripped)

    cleaned_text = "\n".join(cleaned_lines)

    try:
        return json.loads(cleaned_text)
    except json.JSONDecodeError as exc:
        # Last-ditch: maybe trailing commas or minor issues. Show context.
        print(f"  [ERROR] JSON parse failed after cleaning: {exc}")
        print(f"  Preview:\n{cleaned_text[:600]}")
        raise


def process_json_file(src: Path, dst: Path) -> None:
    """Read a potentially malformed JSON file, clean it, write valid JSON."""
    print(f"  Processing JSON: {src.name}")
    raw = src.read_text(encoding="utf-8-sig")  # utf-8-sig strips BOM
    data = clean_malformed_json(raw)
    dst.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"    ✓ Wrote cleaned JSON → {dst.name}")


def clean_malformed_csv(raw_text: str) -> str:
    """
    Fix CSVs where each entire row is a single quoted string, e.g.:
        "order_id,order_date,region,..."
        "1001,2024-01-05,APAC,..."

    Also strips BOM and normalizes line endings.
    """
    text = _normalize_text(raw_text)
    lines = [l for l in text.split("\n") if l.strip()]

    if not lines:
        return text

    # Detect: if most lines are a single quoted field, unwrap them
    quoted_count = sum(
        1 for line in lines
        if line.strip().startswith('"') and line.strip().endswith('"')
    )

    if quoted_count < len(lines) * 0.7:
        # Doesn't look like the "whole row quoted" pattern — return normalized
        return "\n".join(lines) + "\n"

    cleaned: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('"') and stripped.endswith('"') and len(stripped) > 2:
            inner = stripped[1:-1]
            inner = inner.replace('""', '"')  # un-double if any
            cleaned.append(inner)
        else:
            cleaned.append(stripped)

    return "\n".join(cleaned) + "\n"


def process_csv_file(src: Path, dst: Path) -> None:
    """Read a potentially malformed CSV, clean it, write standard CSV."""
    print(f"  Processing CSV:  {src.name}")
    raw = src.read_text(encoding="utf-8-sig")  # strips BOM
    cleaned = clean_malformed_csv(raw)

    reader = csv.reader(io.StringIO(cleaned))
    rows = list(reader)
    if rows:
        print(f"    Columns: {len(rows[0])}, Rows: {len(rows) - 1} (excl. header)")
    else:
        print("    [WARN] Empty CSV")

    dst.write_text(cleaned, encoding="utf-8")
    print(f"    ✓ Wrote cleaned CSV  → {dst.name}")


def main() -> None:
    print("=" * 60)
    print("  Data Preprocessing Pipeline")
    print("=" * 60)
    print(f"  Source : {RAW_DATA_DIR}")
    print(f"  Output : {PROCESSED_DIR}")
    print()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    errors = 0

    for fname in ["data_dictionary.json", "nl_queries.json"]:
        # The raw examples contain pseudo-SQL and an incorrect AOV formula.
        # Keep them as source material, but publish the reviewed runnable set.
        source_name = "nl_queries_curated.json" if fname == "nl_queries.json" else fname
        src = RAW_DATA_DIR / source_name
        dst = PROCESSED_DIR / fname
        if src.exists():
            try:
                process_json_file(src, dst)
            except Exception as exc:
                print(f"    ✗ FAILED: {exc}")
                errors += 1
        else:
            print(f"  [SKIP] {fname} not found")

    print()

    for fname in ["sales_data.csv", "targets.csv"]:
        src = RAW_DATA_DIR / fname
        dst = PROCESSED_DIR / fname
        if src.exists():
            try:
                process_csv_file(src, dst)
            except Exception as exc:
                print(f"    ✗ FAILED: {exc}")
                errors += 1
        else:
            print(f"  [SKIP] {fname} not found")

    feedback_log = PROCESSED_DIR / "feedback_log.csv"
    if not feedback_log.exists():
        feedback_log.write_text(
            "timestamp,query,generated_sql,status,error_message,user_feedback,confidence_score\n",
            encoding="utf-8",
        )
        print(f"\n  ✓ Created empty feedback log → {feedback_log.name}")

    print()
    print("=" * 60)
    if errors:
        print(f"  ✗ Completed with {errors} error(s)")
        sys.exit(1)
    else:
        print("  ✓ Preprocessing complete — all files cleaned!")
    print("=" * 60)


if __name__ == "__main__":
    main()
