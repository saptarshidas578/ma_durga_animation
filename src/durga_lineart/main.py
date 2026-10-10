"""Build cached curve geometry, then play it live in a Pygame window."""

import argparse, json, os, time
from pathlib import Path


def main():
    project_root = Path(__file__).resolve().parents[2]
    ap = argparse.ArgumentParser(description="Animate fitted equations from white line art")
    ap.add_argument("--image", default=str(project_root / "assets" / "reference.png"))
    ap.add_argument("--duration", type=float, default=75.0)
    ap.add_argument("--layout", choices=("side", "stacked"), default="side")
    ap.add_argument("--fullscreen", action="store_true")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--region", default="", help="comma-separated region names to play")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    os.chdir(project_root)
    image = Path(args.image)
    if not image.is_absolute():
        image = project_root / image
    image = image.resolve()
    if not image.exists():
        raise SystemExit(f"Reference image not found: {image}")
    Path("cache").mkdir(exist_ok=True)
    started = time.perf_counter()
    strokes_path = Path("cache/strokes.json")
    timeline_path = Path("cache/timeline.json")
    if args.rebuild or not strokes_path.exists():
        from .prep import preprocess
        from .trace import trace_skeleton
        from .fit import fit_strokes, save_strokes
        from .order import order_strokes

        skel = preprocess(image)
        traced = trace_skeleton(skel)
        strokes, errors = fit_strokes(traced, skel.shape)
        strokes = order_strokes(strokes)
        save_strokes(strokes, str(strokes_path))
        build_seconds = time.perf_counter() - started
        (Path("cache") / "build_stats.json").write_text(
            json.dumps(
                {
                    "build_seconds": build_seconds,
                    "pixel_strokes": len(strokes),
                    "fit_rms_mean": float(sum(errors) / max(1, len(errors))),
                    "fit_rms_max": float(max(errors, default=0)),
                    "fit_max_error": float(max((s["fit_error_px"] for s in strokes), default=0)),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Built {len(strokes):,} fitted strokes in {build_seconds:.1f}s")
    else:
        strokes = json.loads(strokes_path.read_text(encoding="utf-8"))
        stats_path = Path("cache/build_stats.json")
        build_seconds = (
            json.loads(stats_path.read_text(encoding="utf-8")).get("build_seconds", 0)
            if stats_path.exists()
            else 0
        )
    if args.region:
        selected = set(x.strip() for x in args.region.split(","))
        strokes = [s for s in strokes if s["region"] in selected]
        for i, s in enumerate(strokes):
            s["id"] = i
    from .timeline import build_timeline, save_timeline

    timeline = build_timeline(strokes, args.duration)
    save_timeline(timeline, str(timeline_path))
    counts = {k: sum(s["tier"] == k for s in strokes) for k in "ABC"}
    print(
        f"Tier counts: A={counts['A']:,}, B={counts['B']:,}, C={counts['C']:,}; animation={timeline['target_duration']:g}s + intro/hold; Tier A equation lead-in={timeline['tier_a_read_time']:.2f}s"
    )
    if args.selftest:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    from .play import Player, selftest

    if args.selftest:
        stats = selftest(strokes, timeline, str(image), args.layout)
        stats.update({"tier_counts": counts, "build_seconds": build_seconds})
        Path("cache/selftest_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        return
    import pygame

    pygame.init()
    info = pygame.display.Info()
    sw = max(640, info.current_w)
    sh = max(720, info.current_h)
    if args.layout == "side":
        height = min(900, int(sh * 0.95))
        width = min(1400, int(height * 1400 / 900), sw)
        size = (width, int(width * 900 / 1400))
    else:
        height = min(1400, int(sh * 0.95))
        width = min(900, int(height * 900 / 1400), sw)
        size = (width, int(width * 1400 / 900))
    Player(strokes, timeline, str(image), size, args.layout, args.scale).run(
        args.fullscreen, args.loop
    )


if __name__ == "__main__":
    main()
