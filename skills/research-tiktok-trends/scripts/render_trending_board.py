#!/usr/bin/env python3
"""Render a trending sound board exactly as the platform published it.

The envelope's ``data`` is the same object the free tool pages show: ranked rows in the board's
own order, today's and yesterday's fastest risers, the board day (``fetchedAt``) and whether the
board is ``stale`` (today's not built yet, so this is the last published one). This script keeps
that order, copies every number as given, and adds nothing the board does not carry: the row
number is the returned position, a missing ``dailyGrowth`` is shown as n/a, and the only derived
value is ``growthRate`` written as a percentage.

One script, two platform faces. Instagram counts reels (``clipsCount``), TikTok counts videos
(``userCount``), and each links to its own sound page; everything else about the board has the
same shape, so the same bytes ship in research-instagram-trends and research-tiktok-trends -- a
fix applied on one side only would make the same published board read differently depending on
which Skill the user happened to reach. Fixed labels are English, like every other renderer in
those packages; ``--language`` is accepted from older callers and ignored.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PLATFORMS = {
    "get_instagram_audio_board": "instagram",
    "get_tiktok_sound_board": "tiktok",
}
RANKED_BY = {
    "instagram": {"daily_growth", "clips_count"},
    "tiktok": {"daily_growth", "user_count"},
}
COUNT_KEY = {"instagram": "clipsCount", "tiktok": "userCount"}
COUNT_LABEL = {"instagram": "Reels", "tiktok": "Videos"}
TITLE = {
    "instagram": "Trending Instagram Reels audio",
    "tiktok": "Trending TikTok sounds",
}
BASIS = {
    "daily_growth": "daily growth",
    "clips_count": "reels using the audio",
    "user_count": "videos using the sound",
}
LINK = {
    "instagram": "https://www.instagram.com/reels/audio/{id}/",
    "tiktok": "https://www.tiktok.com/music/x-{id}",
}

STALE = "Today's board has not been built yet; this is the last published board."
EMPTY = "The board returned no sounds."
RISERS_EMPTY = "No risers on this day."
NO_RISERS = "This board carries no riser lists."
NA = "n/a"
FOOTER = (
    "Counts and growth are the board's own numbers in the board's own order; n/a means the board "
    "has no baseline for that sound yet, not zero growth. The board shows usage, not niche fit, "
    "audience demand or virality."
)
COLUMNS = ["#", "Title", "Author", "{count}", "Daily growth", "Link"]
RISER_COLUMNS = ["#", "Title", "Author", "{count}", "Daily growth", "Growth rate", "Link"]
RISER_HEADING = {
    "today": "Fastest risers today ({date})",
    "yesterday": "Fastest risers yesterday ({date})",
}


def cell(value):
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("|", "&#124;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def number(value):
    """Copy a board number as written; only a null becomes the n/a label."""
    if value is None:
        return NA
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Board number is not numeric: {value!r}")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def percent(rate):
    if isinstance(rate, bool) or not isinstance(rate, (int, float)):
        raise ValueError(f"growthRate is not numeric: {rate!r}")
    return f"{rate * 100:.1f}%"


def board_day(fetched_at):
    return str(fetched_at)[:10] if isinstance(fetched_at, str) and len(fetched_at) >= 10 else str(fetched_at)


def platform_of(envelope, data):
    platform = PLATFORMS.get(envelope.get("operation"))
    if platform:
        return platform
    basis = data.get("rankedBy")
    if basis == "clips_count" or "discovered" in data:
        return "instagram"
    if basis == "user_count" or "chartUpdatedAt" in data:
        return "tiktok"
    raise ValueError("Cannot tell which platform this board belongs to")


def check_row(row, count_key, riser=False):
    if not isinstance(row, dict):
        raise ValueError("Board row is not an object")
    if row.get("locked") is True:
        raise ValueError("Board row is locked; the connector face never returns a walled board")
    for key in ("id", "title", "author", count_key):
        if key not in row:
            raise ValueError(f"Board row is missing {key}")
    count = row[count_key]
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise ValueError(f"Board row {count_key} is invalid: {count!r}")
    if riser and row.get("growthRate") is None:
        raise ValueError("Riser row is missing growthRate")


def table(rows, platform, riser=False):
    count_key = COUNT_KEY[platform]
    header = [c.replace("{count}", COUNT_LABEL[platform]) for c in (RISER_COLUMNS if riser else COLUMNS)]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    for position, row in enumerate(rows, start=1):
        check_row(row, count_key, riser)
        cells = [str(position), cell(row["title"]), cell(row["author"]), number(row[count_key]),
                 number(row.get("dailyGrowth"))]
        if riser:
            cells.append(percent(row["growthRate"]))
        cells.append(LINK[platform].format(id=cell(row["id"])))
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render(envelope):
    if not isinstance(envelope, dict) or envelope.get("status") != "completed":
        raise ValueError("Trending board retrieval did not complete")
    data = envelope.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("sounds"), list):
        raise ValueError("Trending board data is missing")
    platform = platform_of(envelope, data)
    if not data.get("fetchedAt") or data.get("rankedBy") not in RANKED_BY[platform]:
        raise ValueError("Trending board day or ranking basis is missing or unsupported")
    if not isinstance(data.get("stale"), bool):
        raise ValueError("Trending board stale flag is missing")
    rising = data.get("rising")
    if not isinstance(rising, dict) or "today" not in rising or "yesterday" not in rising:
        raise ValueError("Trending board rising block is missing")

    lines = [f"# {TITLE[platform]}", ""]
    lines.append(f"Board from {cell(board_day(data['fetchedAt']))}")
    if data["stale"]:
        lines.append(STALE)
    lines.append(f"Ranked by {BASIS[data['rankedBy']]}")
    if platform == "tiktok" and data.get("chartUpdatedAt"):
        lines.append(f"Platform chart updated {cell(board_day(data['chartUpdatedAt']))}")
    lines.append("")
    if data["sounds"]:
        lines += table(data["sounds"], platform)
    else:
        lines.append(EMPTY)

    any_risers = False
    for key in ("today", "yesterday"):
        day = rising.get(key)
        if day is None:
            continue
        if not isinstance(day, dict) or day.get("locked") is True or not isinstance(day.get("sounds"), list):
            raise ValueError(f"Riser list for {key} is not readable")
        any_risers = True
        lines += ["", "## " + RISER_HEADING[key].format(date=cell(day.get("date", ""))), ""]
        if day["sounds"]:
            lines += table(day["sounds"], platform, riser=True)
        else:
            lines.append(RISERS_EMPTY)
    if not any_risers:
        lines += ["", NO_RISERS]

    lines += ["", FOOTER]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("envelope", type=Path, help="persisted creator-trending-board envelope")
    parser.add_argument("output", type=Path, help="Markdown report to write")
    parser.add_argument("--language", help="accepted from older callers; fixed labels are English")
    args = parser.parse_args()
    try:
        text = render(json.loads(args.envelope.read_text(encoding="utf-8")))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(json.dumps({"status": "ok", "path": str(args.output)}))
        return 0
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "failed", "error": f"{type(error).__name__}: {error}"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
