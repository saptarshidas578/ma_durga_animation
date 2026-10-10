"""Build a compact, cached 75-second reveal schedule."""

import json
import math
from pathlib import Path
from .regions import REGION_ORDER

TARGET_DURATION = 75.0
TIER_A_READ_TIME = 0.25


def build_timeline(strokes, duration=TARGET_DURATION):
    # Events list stroke indexes sharing a start/end; Tier B batches of ten and
    # Tier C draws as one quick regional burst.
    events = []
    for region in REGION_ORDER:
        region_strokes = [s for s in strokes if s["region"] == region]
        for s in region_strokes:
            if s["tier"] == "A":
                events.append(
                    {
                        "ids": [s["id"]],
                        "base": 0.15 + 0.012 * math.sqrt(s["length_px"]),
                        "label": s["equation_text"],
                        "region": region,
                        "tier": "A",
                    }
                )
        mids = [s for s in region_strokes if s["tier"] == "B"]
        for i in range(0, len(mids), 10):
            batch = mids[i : i + 10]
            events.append(
                {
                    "ids": [s["id"] for s in batch],
                    "base": 0.18
                    + 0.02 * math.sqrt(sum(s["length_px"] for s in batch) / len(batch)),
                    "label": batch[0]["equation_text"] + f"  + {len(batch)-1} similar strokes",
                    "region": region,
                    "tier": "B",
                }
            )
        tiny = [s for s in region_strokes if s["tier"] == "C"]
        if tiny:
            events.append(
                {
                    "ids": [s["id"] for s in tiny],
                    "base": 0.55,
                    "label": f"Σ details: {len(tiny)} tiny arcs",
                    "region": region,
                    "tier": "C",
                }
            )
    total = sum(e["base"] for e in events) or 1
    tier_a_count = sum(len(e["ids"]) for e in events if e["tier"] == "A")
    pre_roll_total = tier_a_count * TIER_A_READ_TIME
    effective_duration = max(float(duration), pre_roll_total + 0.5)
    scale = (effective_duration - pre_roll_total) / total
    t = 1.0
    by_id = {}
    for event_index, e in enumerate(events):
        dt = e["base"] * scale
        burst_span = min(0.22, dt * 0.12)
        label_start = t
        if e["tier"] == "A":
            t += TIER_A_READ_TIME
        for j, sid in enumerate(e["ids"]):
            if e["tier"] == "C":
                start = t + (dt - burst_span) * j / max(1, len(e["ids"]) - 1)
                end = start + burst_span
            else:
                start = t
                end = t + dt
            by_id[str(sid)] = {
                "label_start": round(label_start, 5),
                "start": round(start, 5),
                "end": round(end, 5),
                "event": event_index,
                "region": e["region"],
                "tier": e["tier"],
                "label": e["label"],
                "stroke_count": len(e["ids"]),
            }
        t += dt
    result = {
        "target_duration": effective_duration,
        "requested_duration": float(duration),
        "tier_a_read_time": TIER_A_READ_TIME,
        "intro": 1.0,
        "hold": 4.0,
        "total_time": round(t + 4, 5),
        "speed_factor": round(scale, 6),
        "events": events,
        "strokes": by_id,
    }
    return result


def save_timeline(timeline, path="cache/timeline.json"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(timeline, separators=(",", ":")), encoding="utf-8")
