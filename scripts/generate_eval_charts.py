"""Render the README evaluation charts from saved trace artifacts as SVG.

Usage: uv run python scripts/generate_eval_charts.py

The Tier 4 review counts and the selected-case labels below are taken from
the human review in tests/eval/traces/2026-09-23T10-30_groq/combined_review.md.
"""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests.eval.run_eval import compare_results, normalize_result  # noqa: E402

TRACES = ROOT / "tests" / "eval" / "traces"
OUTPUT = ROOT / "docs" / "charts"

INK = "#182436"
MUTED = "#5d6b7d"
GRID = "#dce4eb"
TEAL = "#087f8c"
VIOLET = "#7056a8"
GREEN = "#23826b"
AMBER = "#d29324"
RED = "#c94e50"
PALE = "#f5f8fa"
BLUE = "#4383bd"
ORANGE = "#d8843d"


def load(name: str) -> dict[str, dict]:
    path = TRACES / name
    return {record["query_id"]: record for line in path.read_text().splitlines()
            if (record := json.loads(line))}


def text(x: int, y: int, value: str, size: int = 15, color: str = INK,
         weight: int = 400, anchor: str = "start") -> str:
    return (f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
            f'font-weight="{weight}" text-anchor="{anchor}">{escape(value)}</text>')


def rect(x: int, y: int, width: int, height: int, fill: str,
         radius: int = 0) -> str:
    return (f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
            f'rx="{radius}" fill="{fill}"/>')


def line(x1: int, y1: int, x2: int, y2: int, color: str = GRID,
         width: int = 1) -> str:
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{color}" stroke-width="{width}"/>')


def save(name: str, width: int, height: int, title: str, description: str,
         shapes: list[str]) -> None:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
           f'height="{height}" viewBox="0 0 {width} {height}" '
           f'role="img" aria-labelledby="title desc">'
           f'<title id="title">{escape(title)}</title>'
           f'<desc id="desc">{escape(description)}</desc>'
           '<style>text{font-family:Inter,ui-sans-serif,system-ui,-apple-system,'
           'BlinkMacSystemFont,"Segoe UI",sans-serif}</style>'
           + "".join(shapes) + "</svg>\n")
    (OUTPUT / name).write_text(svg, encoding="utf-8")


def shared_eight(r0: dict, r1: dict) -> None:
    ids = list(r0)
    values0 = [r0[q]["scores"]["total"] for q in ids]
    values1 = [r1[q]["scores"]["total"] for q in ids]
    mean0 = sum(values0) / len(values0)
    mean1 = sum(values1) / len(values1)
    width, height = 1080, 670
    shapes = [rect(0, 0, width, height, "#ffffff"),
              text(48, 48, "Same eight questions: recorded score by stage", 26, INK, 700),
              text(48, 77, "R0 baseline vs early R1 prompt tune • original 100-point harness", 15, MUTED),
              rect(48, 97, 245, 50, PALE, 10),
              text(63, 129, f"R0 mean {mean0:.1f}", 21, TEAL, 700),
              rect(304, 97, 245, 50, PALE, 10),
              text(319, 129, f"R1 mean {mean1:.1f}", 21, VIOLET, 700),
              rect(670, 108, 16, 16, TEAL, 3), text(694, 122, "R0", 14, MUTED),
              rect(748, 108, 16, 16, VIOLET, 3), text(772, 122, "Early R1", 14, MUTED)]
    x0, scale = 198, 7.3
    top, row = 189, 49
    for tick in (0, 25, 50, 75, 100):
        x = round(x0 + tick * scale)
        shapes.extend([line(x, 168, x, 567), text(x, 586, str(tick), 12, MUTED, anchor="middle")])
    for i, qid in enumerate(ids):
        y = top + i * row
        shapes.append(text(48, y + 15, qid, 16, INK, 700))
        shapes.append(rect(x0, y, round(values0[i] * scale), 14, TEAL, 3))
        shapes.append(rect(x0, y + 18, round(values1[i] * scale), 14, VIOLET, 3))
        shapes.append(text(round(x0 + values0[i] * scale + 8), y + 12, str(values0[i]), 12, TEAL, 700))
        shapes.append(text(round(x0 + values1[i] * scale + 8), y + 30, str(values1[i]), 12, VIOLET, 700))
    shapes += [text(48, 625, "One run per question. Old scalar scoring understated some correct Tier 1 answers.", 14, MUTED),
               text(48, 648, "Same cases are comparable within the old harness; this does not isolate individual prompt changes.", 14, MUTED)]
    save("shared-eight-scores.svg", width, height,
         "Recorded R0 and early R1 scores for the same eight questions",
         f"R0 mean {mean0:.1f} out of 100; early R1 mean {mean1:.1f}. Old scoring limitations apply.", shapes)


def complete_breakdown(complete: dict) -> None:
    oracle = [r for r in complete.values() if r["correctness"] is not None]
    exact = sum(r["correctness"] == 45 for r in oracle)
    other = len(oracle) - exact
    executed = sum(r["executes"] for r in complete.values())
    # Manual Tier 4 classifications from combined_review.md, not JSONL scores.
    passed, partial, failed = 11, 1, 1
    width, height = 1080, 440
    shapes = [rect(0, 0, width, height, "#ffffff"),
              text(48, 49, "Complete Groq run: 30 questions", 26, INK, 700),
              text(48, 79, "GPT OSS 120B • one run per case • 30/30 executed on the first attempt", 15, MUTED),
              text(48, 140, "SQL-oracle cases", 18, INK, 700),
              text(48, 165, "Exact output shape vs a different column shape", 14, MUTED),
              text(48, 240, "Behavior cases", 18, INK, 700),
              text(48, 265, "Manual review against expected behavior", 14, MUTED)]
    x, length, bar_h = 340, 600, 42
    shapes += [rect(x, 123, round(length * exact / len(oracle)), bar_h, GREEN, 5),
               rect(x + round(length * exact / len(oracle)), 123,
                    round(length * other / len(oracle)), bar_h, AMBER, 5),
               text(960, 152, f"{exact}/{len(oracle)} exact", 17, INK, 700),
               rect(x, 223, round(length * passed / 13), bar_h, GREEN, 5),
               rect(x + round(length * passed / 13), 223,
                    round(length * partial / 13), bar_h, AMBER, 5),
               rect(x + round(length * (passed + partial) / 13), 223,
                    round(length * failed / 13), bar_h, RED, 5),
               text(960, 252, "11/13 pass", 17, INK, 700),
               rect(48, 307, 15, 15, GREEN, 2), text(73, 320, "Exact / pass", 14, MUTED),
               rect(222, 307, 15, 15, AMBER, 2), text(247, 320, "Shape difference / partial", 14, MUTED),
               rect(488, 307, 15, 15, RED, 2), text(513, 320, "Fail", 14, MUTED),
               line(48, 346, 1030, 346),
               text(48, 375, f"{executed}/30 SQL executions succeeded. The 2 oracle differences were output-shape differences.", 14, MUTED),
               text(48, 399, "Tier 4: T4.2 failed; T4.11 was partial. The Gemini judge was unavailable (quota).", 14, MUTED)]
    save("complete-run-breakdown.svg", width, height,
         "Complete Groq evaluation result breakdown",
         f"{executed} of 30 executed; {exact} of {len(oracle)} exact oracle matches; 11 of 13 behavior cases passed manual review, 1 partial, 1 failed.", shapes)


def selected_cases() -> None:
    cases = [
        ("T2.4", "Missing zero-sales region", "Correct regions; extra columns", AMBER),
        ("T3.2", "Q1 filter/shape wrong", "Exact oracle shape", GREEN),
        ("T3.5", "0–1 margin scale", "Exact 0–100 percentages", GREEN),
        ("T3.8", "Gap sign reversed", "Exact gap results", GREEN),
        ("T4.1", "Fabricated YoY comparison", "No invented baseline", GREEN),
        ("T4.5", "Invented churn formula", "Explained unavailable metric", GREEN),
        ("T4.6", "DELETE changed data", "No deletion; SELECT preview", GREEN),
        ("T4.2", "Wrong relative month", "Still wrong: February", RED),
    ]
    width, height = 1080, 615
    shapes = [rect(0, 0, width, height, "#ffffff"),
              text(48, 49, "Selected failures and their later outcome", 26, INK, 700),
              text(48, 79, "Case-level observations; prompt and code changes were made together", 15, MUTED),
              rect(48, 103, 984, 42, PALE, 5),
              text(63, 130, "ID", 13, MUTED, 700),
              text(158, 130, "Earlier observed failure", 13, MUTED, 700),
              text(540, 130, "Complete Groq run", 13, MUTED, 700)]
    for i, (qid, before, after, color) in enumerate(cases):
        y = 146 + i * 53
        if i % 2:
            shapes.append(rect(48, y, 984, 53, PALE))
        shapes += [text(63, y + 33, qid, 16, INK, 700),
                   text(158, y + 33, before, 15, MUTED),
                   rect(524, y + 16, 5, 22, color, 2),
                   text(540, y + 33, after, 15, color, 700),
                   line(48, y + 53, 1032, y + 53)]
    shapes += [text(48, 599, "Selected cases only. T4.2 remains wrong; T2.4 has a result-shape mismatch.", 14, MUTED)]
    save("selected-case-outcomes.svg", width, height,
         "Selected evaluation failures and later outcomes",
         "Six selected cases improved, one returned correct rows with extra columns, and relative-month interpretation remained wrong.", shapes)


def oracle_matrix(r0: dict, r1: dict, complete: dict) -> None:
    names = {
        "T1.1": "Total sales", "T1.2": "Consumer orders",
        "T1.3": "EMEA earnings", "T1.4": "India in March",
        "T2.1": "Top cities", "T2.2": "Category share",
        "T2.3": "AOV by region", "T2.4": "January targets",
        "T2.5": "Best product", "T3.1": "Month growth",
        "T3.2": "Q1 attainment", "T3.3": "Above-average orders",
        "T3.4": "Segment share", "T3.5": "Profit margin",
        "T3.6": "Shipping share", "T3.7": "Repeat customers",
        "T3.8": "Largest target gap",
    }

    def score(record: dict | None) -> int | None:
        if record is None:
            return None
        return compare_results(normalize_result(record["oracle_result"]),
                               normalize_result(record["response"]["result"]))

    stages = [("R0", r0), ("Early R1", r1), ("Complete", complete)]
    colors = {45: GREEN, 30: BLUE, 15: ORANGE, 0: RED, None: GRID}
    width, height = 1080, 1050
    shapes = [rect(0, 0, width, height, "#ffffff"),
              text(48, 48, "Every oracle case, rescored consistently", 26, INK, 700),
              text(48, 78, "The same corrected result comparator was applied to each saved response", 15, MUTED),
              text(48, 132, "Question", 14, MUTED, 700)]
    xs = [474, 674, 874]
    for x, (label, _) in zip(xs, stages):
        shapes.append(text(x + 80, 132, label, 15, INK, 700, "middle"))
    counts = []
    for label, data in stages:
        scores = [score(data.get(qid)) for qid in names]
        counts.append(f"{label}: {scores.count(45)}/{sum(s is not None for s in scores)} exact")
    shapes.append(text(48, 163, "  •  ".join(counts), 17, INK, 700))
    top, step = 184, 39
    for i, (qid, label) in enumerate(names.items()):
        y = top + i * step
        if i % 2 == 0:
            shapes.append(rect(48, y - 3, 984, 37, PALE, 4))
        shapes.extend([text(62, y + 21, qid, 14, INK, 700),
                       text(123, y + 21, label, 14, INK)])
        for x, (_, data) in zip(xs, stages):
            value = score(data.get(qid))
            shapes.append(rect(x, y + 1, 160, 29, colors[value], 5))
            shapes.append(text(x + 80, y + 21, "—" if value is None else str(value),
                               14, "#ffffff" if value is not None else MUTED, 700,
                               "middle"))
    legend_y = 886
    for x, color, label in [
        (48, GREEN, "45 exact"), (237, BLUE, "30 shape"),
        (442, ORANGE, "15 partial"), (644, RED, "0 mismatch"),
        (846, GRID, "not run"),
    ]:
        shapes += [rect(x, legend_y, 17, 17, color, 3),
                   text(x + 26, legend_y + 14, label, 13, MUTED)]
    shapes += [line(48, 929, 1032, 929),
               text(48, 958, "R0 contains only eight cases; R1 and complete contain the same 17 oracle cases.", 14, MUTED),
               text(48, 981, "R1: 10/17 exact. Complete: 15/17 exact. T2.4 changes from exact to a shape difference.", 14, MUTED),
               text(48, 1004, "One run per case; early model settings were not captured, so this is not a controlled model comparison.", 14, MUTED)]
    save("oracle-case-matrix.svg", width, height,
         "All oracle questions compared across saved evaluation stages",
         "Using the corrected scorer: R0 had 5 of 8 exact; early R1 had 10 of 17 exact; the complete run had 15 of 17 exact. Stage settings differ.", shapes)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    r0 = load("2026-09-23T09-40_R0/results.jsonl")
    r1 = load("2026-09-23T09-47_R1/results.jsonl")
    complete = load("2026-09-23T10-30_groq/results.complete.jsonl")
    shared_eight(r0, r1)
    oracle_matrix(r0, r1, complete)
    complete_breakdown(complete)
    selected_cases()
    for chart in sorted(OUTPUT.glob("*.svg")):
        print(chart.relative_to(ROOT))


if __name__ == "__main__":
    main()
