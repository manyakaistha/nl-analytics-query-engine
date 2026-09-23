"""Create editable Excalidraw versions of the README data-flow diagrams.

Run: uv run python scripts/build_excalidraw_data_flow.py
Outputs: docs/diagrams/application-data-flow.excalidraw and clipboard JSON.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "docs" / "diagrams"
STAMP = int(time.time() * 1000)
COUNTER = 0

INK = "#17243a"
MUTED = "#536478"
EDGE = "#52657d"
BLUE = ("#3b73b9", "#e8f1fc")
PURPLE = ("#7957a7", "#f0eafd")
TEAL = ("#18816f", "#e6f6f1")
AMBER = ("#bb7b20", "#fff5df")
RED = ("#bf4a53", "#fdecef")
GRAY = ("#6b7788", "#f2f5f8")

BACKGROUNDS: list[dict] = []
ARROWS: list[dict] = []
NODES: list[dict] = []
LABELS: list[dict] = []
BOXES: dict[str, dict] = {}


def ident(key: str) -> str:
    return hashlib.sha1(key.encode()).hexdigest()[:22]


def common(key: str, kind: str, x: int, y: int, width: int, height: int,
           stroke: str, fill: str, *, roundness: int | None = 3) -> dict:
    global COUNTER
    COUNTER += 1
    return {
        "id": ident(key), "type": kind, "x": x, "y": y,
        "width": width, "height": height, "angle": 0,
        "strokeColor": stroke, "backgroundColor": fill,
        "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
        "roughness": 0, "opacity": 100, "groupIds": [], "frameId": None,
        "index": f"b{COUNTER:04x}",
        "roundness": {"type": roundness} if roundness else None,
        "seed": int(hashlib.sha1((key + "seed").encode()).hexdigest()[:7], 16),
        "version": 1,
        "versionNonce": int(hashlib.sha1((key + "nonce").encode()).hexdigest()[:7], 16),
        "isDeleted": False, "boundElements": [], "updated": STAMP,
        "link": None, "locked": False, "created": None,
    }


def free_text(key: str, x: int, y: int, value: str, *, size: int = 20,
              color: str = INK, width: int = 1800, height: int = 40,
              bold: bool = False) -> None:
    element = common(key, "text", x, y, width, height, color, "transparent",
                     roundness=None)
    element.update({
        "text": value, "fontSize": size, "fontFamily": 2,
        "textAlign": "left", "verticalAlign": "top", "containerId": None,
        "originalText": value, "autoResize": False, "lineHeight": 1.2,
        "labelPosition": None, "baseFontSize": None,
    })
    if bold:
        element["strokeWidth"] = 2
    LABELS.append(element)


def panel(key: str, x: int, y: int, width: int, height: int,
          title: str, subtitle: str) -> None:
    element = common(key, "rectangle", x, y, width, height,
                     "#d9e2eb", "#f9fbfd")
    element["strokeWidth"] = 1
    BACKGROUNDS.append(element)
    free_text(key + "-title", x + 36, y + 22, title, size=27, width=width - 70)
    free_text(key + "-subtitle", x + 36, y + 59, subtitle,
              size=17, color=MUTED, width=width - 70)


def node(key: str, x: int, y: int, width: int, height: int, label: str,
         color: tuple[str, str] = BLUE, *, diamond: bool = False,
         font_size: int = 19) -> None:
    shape = common(key, "diamond" if diamond else "rectangle", x, y,
                   width, height, color[0], color[1],
                   roundness=2 if diamond else 3)
    text_id = ident(key + "-text")
    shape["boundElements"].append({"type": "text", "id": text_id})
    text_height = round(len(label.split("\n")) * font_size * 1.2)
    text_x = x + (30 if diamond else 12)
    text_width = width - (60 if diamond else 24)
    text_y = y + round((height - text_height) / 2)
    caption = common(key + "-text", "text", text_x, text_y, text_width,
                     text_height, INK, "transparent", roundness=None)
    caption.update({
        "text": label, "fontSize": font_size, "fontFamily": 2,
        "textAlign": "center", "verticalAlign": "middle",
        "containerId": shape["id"], "originalText": label,
        "autoResize": False, "lineHeight": 1.2,
        "labelPosition": None, "baseFontSize": None,
    })
    BOXES[key] = shape
    NODES.extend([shape, caption])


def anchor(key: str, side: str) -> tuple[int, int]:
    b = BOXES[key]
    x, y, w, h = b["x"], b["y"], b["width"], b["height"]
    return {
        "left": (x - 6, y + h // 2),
        "right": (x + w + 6, y + h // 2),
        "top": (x + w // 2, y - 6),
        "bottom": (x + w // 2, y + h + 6),
    }[side]


def binding(key: str, side: str) -> dict:
    fixed = {
        "left": [-0.025, 0.5], "right": [1.025, 0.5],
        "top": [0.5, -0.025], "bottom": [0.5, 1.025],
    }[side]
    return {"elementId": BOXES[key]["id"], "mode": "orbit", "fixedPoint": fixed}


def arrow(key: str, source: str, target: str, *,
          start: str = "right", end: str = "left",
          via: list[tuple[int, int]] | None = None,
          label: str | None = None, label_xy: tuple[int, int] | None = None,
          dashed: bool = False, color: str = EDGE) -> None:
    a, b = anchor(source, start), anchor(target, end)
    absolute = [a] + (via or []) + [b]
    relative = [[x - a[0], y - a[1]] for x, y in absolute]
    element = common(key, "arrow", a[0], a[1],
                     max(x for x, _ in absolute) - min(x for x, _ in absolute),
                     max(y for _, y in absolute) - min(y for _, y in absolute),
                     color, "transparent", roundness=2)
    element.update({
        "points": relative,
        "startBinding": binding(source, start),
        "endBinding": binding(target, end),
        "startArrowhead": None, "endArrowhead": "arrow",
        "elbowed": False, "moveMidPointsWithElement": False,
        "strokeStyle": "dashed" if dashed else "solid",
    })
    for endpoint in (source, target):
        BOXES[endpoint]["boundElements"].append({"id": element["id"], "type": "arrow"})
    ARROWS.append(element)
    if label and label_xy:
        free_text(key + "-label", label_xy[0], label_xy[1], label,
                  size=16, color=color, width=160, height=24)


def build() -> list[dict]:
    free_text("main-title", 70, 35,
              "Intelligent Analytics Query Engine — Data Flow",
              size=36, width=2450, height=52)
    free_text("main-subtitle", 72, 92,
              "Editable Excalidraw reconstruction of the README diagrams",
              size=19, color=MUTED, width=2450)

    panel("setup-panel", 60, 150, 2580, 455, "1 · Data preparation",
          "Run preprocessing, then load the prepared CSV snapshot into DuckDB on first use.")
    node("raw-sales", 100, 275, 270, 90, "Raw sales and\ntargets CSVs", BLUE)
    node("raw-rules", 100, 420, 270, 100, "Raw dictionary and\ncurated SQL examples", BLUE)
    node("preprocess", 520, 350, 290, 100, "scripts/preprocess.py", PURPLE)
    node("processed-csv", 950, 275, 300, 90, "Processed sales and\ntargets CSVs", TEAL)
    node("processed-rules", 950, 420, 300, 90, "Processed dictionary\nand SQL examples", TEAL)
    node("database", 1390, 275, 290, 90, "In-memory DuckDB\n(on first use)", TEAL)
    node("view", 1790, 275, 280, 90, "sales_with_revenue\nview", TEAL)
    node("profile", 2200, 275, 300, 90, "Data profile for\nthe prompt", PURPLE)
    node("snapshot-hash", 1790, 420, 280, 90, "Loaded CSV hash\nfor cache key", PURPLE)
    node("created-log", 1390, 420, 290, 90, "Create feedback log\nif absent", GRAY)

    arrow("a-raw-sales", "raw-sales", "preprocess")
    arrow("a-raw-rules", "raw-rules", "preprocess")
    arrow("a-prepared-csv", "preprocess", "processed-csv")
    arrow("a-prepared-rules", "preprocess", "processed-rules")
    arrow("a-create-log", "preprocess", "created-log",
          start="bottom", end="bottom", via=[(665, 555), (1535, 555)])
    arrow("a-csv-db", "processed-csv", "database")
    arrow("a-db-view", "database", "view")
    arrow("a-view-profile", "view", "profile")
    arrow("a-csv-hash", "processed-csv", "snapshot-hash",
          start="bottom", end="top", via=[(1100, 392), (1930, 392)])

    panel("query-panel", 60, 640, 2580, 1350, "2 · Per-query path",
          "The selected model is checked before prompt assembly. Cache hits skip Groq and DuckDB.")
    node("browser", 100, 775, 250, 95, "Browser: question\nand selected model", BLUE)
    node("api", 430, 775, 250, 95, "POST /api/query", BLUE)
    node("model", 760, 775, 250, 95, "Allowed model or\nserver default", PURPLE)
    node("prompt", 1090, 755, 330, 135,
         "Build prompt: rules, data\nprofile, dictionary, examples,\nrecent feedback counts", PURPLE,
         font_size=18)
    node("key", 1510, 775, 310, 95,
         "Cache key: question, prompt,\ndata hash, model settings", PURPLE,
         font_size=18)
    node("cache", 1940, 760, 250, 125, "Cache hit?", AMBER, diamond=True)
    node("hit-log", 2280, 710, 280, 95, "Append SUCCESS\nhistory entry", GRAY)
    node("hit-return", 2280, 860, 280, 95, "Return cached answer\n(no Groq or SQL)", BLUE,
         font_size=18)

    for src, dst in [("browser", "api"), ("api", "model"),
                     ("model", "prompt"), ("prompt", "key"), ("key", "cache")]:
        arrow(f"a-{src}-{dst}", src, dst)
    arrow("a-hit", "cache", "hit-log", label="hit", label_xy=(2198, 717))
    arrow("a-hit-return", "hit-log", "hit-return", start="bottom", end="top")

    node("groq", 1940, 1010, 250, 90, "Groq generates\nstructured JSON", PURPLE)
    node("parse", 1610, 1010, 250, 90, "Parse and validate\nmodel output", PURPLE)
    node("guard", 1280, 1010, 250, 90, "Single SELECT\nstatement guard", AMBER)
    node("execute", 950, 1010, 250, 90, "Execute SQL\nin DuckDB", TEAL)
    node("format", 620, 1010, 250, 90, "Format rows + model\nexplanation", TEAL)
    node("success-log", 290, 1010, 250, 90, "Append SUCCESS\nhistory entry", GRAY)
    node("store-cache", 290, 1190, 250, 90, "Store successful\nanswer if small enough", TEAL,
         font_size=18)
    node("fresh-return", 620, 1190, 250, 90, "Return fresh answer", BLUE)
    arrow("a-miss", "cache", "groq", start="bottom", end="top",
          label="miss", label_xy=(2048, 913))
    for src, dst in [("groq", "parse"), ("parse", "guard"),
                     ("guard", "execute"), ("execute", "format"),
                     ("format", "success-log")]:
        arrow(f"a-{src}-{dst}", src, dst, start="left", end="right")
    arrow("a-success-store", "success-log", "store-cache", start="bottom", end="top")
    arrow("a-store-return", "store-cache", "fresh-return")

    node("retryable-error", 1280, 1180, 250, 85,
         "Retryable generation,\nvalidation or SQL error", RED, font_size=17)
    node("retry", 1280, 1320, 250, 110, "Attempts left?\n(maximum 3)", AMBER,
         diamond=True, font_size=18)
    node("fail-log", 1940, 1320, 250, 90, "Append FAILED\nhistory entry", RED)
    node("fail-return", 1940, 1520, 250, 90, "Return error response\n(no cache entry)", RED,
         font_size=18)
    arrow("a-parse-error", "parse", "retryable-error",
          start="bottom", end="right",
          via=[(1735, 1135), (1595, 1135)], color=RED[0])
    arrow("a-guard-error", "guard", "retryable-error",
          start="bottom", end="top", color=RED[0])
    arrow("a-sql-error", "execute", "retryable-error",
          start="bottom", end="left",
          via=[(1075, 1135), (1210, 1135)], color=RED[0])
    arrow("a-error-retry", "retryable-error", "retry",
          start="bottom", end="top", color=RED[0])
    arrow("a-retry", "retry", "groq", start="bottom", end="right",
          via=[(1405, 1460), (2250, 1460), (2250, 1055)],
          label="retry with error context", label_xy=(1510, 1435),
          color=AMBER[0])
    arrow("a-exhausted", "retry", "fail-log", start="right", end="left",
          label="exhausted", label_xy=(1650, 1330), color=RED[0])
    arrow("a-rate-limit", "groq", "fail-log", start="bottom", end="top",
          label="429: stop", label_xy=(2080, 1190), color=RED[0])
    arrow("a-fail-return", "fail-log", "fail-return", start="bottom", end="top")

    node("feedback", 100, 1720, 250, 90, "Optional thumbs\nfeedback", BLUE)
    node("feedback-api", 430, 1720, 250, 90, "POST /api/feedback", BLUE)
    node("update-entry", 760, 1720, 250, 90, "Update matching\nhistory entry", GRAY)
    node("feedback-csv", 1090, 1720, 250, 90, "feedback_log.csv", TEAL)
    node("aggregate", 1420, 1720, 250, 90, "Aggregate recent\nfeedback counts", PURPLE)
    node("next-prompt", 1750, 1720, 280, 90, "Used by a later\nquery's prompt", PURPLE)
    for src, dst in [("feedback", "feedback-api"),
                     ("feedback-api", "update-entry"),
                     ("update-entry", "feedback-csv"),
                     ("feedback-csv", "aggregate"),
                     ("aggregate", "next-prompt")]:
        arrow(f"a-{src}-{dst}", src, dst)
    free_text("note-history", 95, 1855,
              "Cache hit, successful SQL, and exhausted/error paths append to the same feedback log."
              " Thumbs feedback updates an existing matching row.",
              size=17, color=MUTED, width=2400)
    free_text("note-output", 95, 1889,
              "The model writes its explanation before it sees result rows. Successful SQL with zero rows still follows the success path.",
              size=17, color=MUTED, width=2400)

    return BACKGROUNDS + ARROWS + NODES + LABELS


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    elements = build()
    # Keep canvas backgrounds behind connectors, with editable nodes and text on top.
    for position, element in enumerate(elements, 1):
        element["index"] = f"b{position:04x}"
    scene = {
        "type": "excalidraw", "version": 2,
        "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }
    clipboard = {"type": "excalidraw/clipboard", "elements": elements, "files": {}}
    for name, payload in [
        ("application-data-flow.excalidraw", scene),
        ("application-data-flow.clipboard.json", clipboard),
    ]:
        path = OUTPUT / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        print(path.relative_to(ROOT))
    print(f"{len(elements)} editable elements")


if __name__ == "__main__":
    main()
