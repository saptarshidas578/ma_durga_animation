---
name: durga-line-art-animation
description: Turn a white-on-black line-art reference image (Goddess Durga) into a program that plays a live animation in a window, where every line is drawn stroke by stroke on a grid like an artist drawing fast, while the parametric equation of the current stroke is shown on screen. The user screen-records the window themselves. Use when asked to animate a line-art image from equations.
---

# Durga Line-Art Equation Animation (live program)

## Goal
Input: `reference.png` (white line art on a black background, portrait, very detailed).
Output: **a Python program** that opens a window and plays the drawing animation live. **Do not export a video.** The user will screen-record the window with their own tool.

What the user sees:
- Dark background with a faint grid and axis ticks.
- White lines appearing one stroke at a time, like an artist drawing, but fast.
- The equation of the current stroke shown on screen, appearing just before and during the stroke.
- A glowing pen tip travelling along the curve. Fresh ink glows gold and cools to white within ~0.4 s.

## Working rules (read first)
- Work fully autonomously. Do not ask the user questions. Make reasonable decisions, record them in `NOTES.md`, and keep going.
- If `reference.png` is missing, look in the working directory for the attached image (png/jpg) and use it.
- Install what you need: `pip install numpy scipy opencv-python-headless scikit-image pillow pygame tqdm`. No ffmpeg and no video encoding anywhere.
- Small modules, re-runnable, expensive steps cached in `cache/`.
- Verify your own work (see Verification) before saying you are done. Fix problems yourself.

## Key reality check
The reference has thousands of tiny elements (flower garlands, mandalas, jewellery). Hand-writing equations for all of it is impossible. So:
**extract the strokes from the image, then fit each one to a parametric equation.** The equation shown on screen is the real fitted equation used to draw that curve.

## Two-phase design (important for smooth playback)
1. **Build phase (slow, cached):** steps 1 to 5 below produce `cache/strokes.json` and `cache/timeline.json`. This may take a while. On later runs, load the cache and skip it. Add `--rebuild` to force it.
2. **Play phase (real time):** open the window and play. Nothing heavy may happen during playback. Only draw what is new each frame.

## Pipeline

### 1. Preprocess (`prep.py`)
- Load grayscale. The image has a soft glow, so use Otsu threshold, then remove components under ~6 px.
- Skeletonize (`skimage.morphology.skeletonize`) to get 1-px centerlines.
- Save `cache/skeleton.png` and a side-by-side preview with the original.

### 2. Trace strokes (`trace.py`)
- Convert the skeleton to a pixel graph (8-neighbourhood). Find endpoints and junctions.
- Walk the graph into ordered polylines (one per branch). Closed loops become closed polylines.
- Drop strokes shorter than 4 px. Merge strokes that join end to end with a smooth tangent (angle change under ~25 degrees).
- Lightly smooth each polyline (Savitzky-Golay or short moving average), keeping endpoints fixed.

### 3. Fit equations (`fit.py`)
Grid coordinates: origin at bottom-centre of the art, x right, y up, 1 grid unit = 10 px. Show all numbers in these units, rounded to 1 decimal.

For each polyline pick the simplest model that fits within ~1.2 px error:
1. **Line**: `y = m·x + c` (or `x = k`). Drawn as `P(t) = P0 + t(P1 − P0)`.
2. **Circle / arc**: `(x − h)² + (y − k)² = r²`, drawn with `x = h + r·cos t, y = k + r·sin t`.
3. **Ellipse**: `x = h + a·cos t·cosφ − b·sin t·sinφ`, `y = k + a·cos t·sinφ + b·sin t·cosφ`.
4. **Cubic Bézier chain** (everything else): Schneider fitting, max error ~1.2 px, split at corners. Shown as `B(t) = (1−t)³P0 + 3(1−t)²t P1 + 3(1−t)t² P2 + t³P3` with the four numeric points.

Save every stroke to `cache/strokes.json`:
```json
{"id": 12, "region": "crown", "type": "bezier", "points": [[x,y],...],
 "params": {...}, "equation_text": "...", "length_px": 83.2, "bbox": [x0,y0,x1,y1]}
```
Always draw from the fitted equation (sample t densely), never from the raw pixels, so what is shown is what is drawn. If a fit looks visibly wrong, use a finer Bézier chain.

### 4. Regions and order (`regions.py`, `order.py`)
Define regions with normalised bounding boxes (tune them by looking at the reference) and draw in this order:
1. `halo` (outer arc, seven small circles and their figures, leaf ornaments)
2. `crown` (tall crown, flame petals, side spirals)
3. `face` (face, eyes, bindi, ears, earrings)
4. `necklaces` (chains and pendants)
5. `body` (torso, saree folds, border patterns)
6. `arms_left`, `arms_right` (hands, bangles)
7. `weapons` (trishula, lotus, conch, bow, bell, sword, chakra, mace, discs)
8. `garlands` (long flower garlands)
9. `lion`
10. `mandalas` (lower-left circular ornaments)

Inside a region: big outlines first, then medium details, then tiny details. Within one size class, order strokes by greedy nearest-neighbour from the pen's last position, flipping a stroke's direction if its far end is closer. This gives the artist's-hand flow.

### 5. Timeline (`timeline.py`)
Target drawing time **75 s** (constant at top of file, overridable with `--duration`), plus a 1 s intro and a 4 s hold at the end.

Three tiers keep it fast:
- **Tier A (length > 60 px):** own equation shown. Base duration `0.15 + 0.012·sqrt(length_px)` s, then scaled globally. Equation appears 0.1 s before the pen starts.
- **Tier B (20–60 px):** batch 6–20 nearby strokes, drawn simultaneously. Show one equation plus `+ N similar strokes`.
- **Tier C (< 20 px):** one quick burst per region, labelled `Σ details: N tiny arcs`.

Compute one global speed factor so the total equals the target. Ease each stroke with smoothstep. Save absolute start/end times per stroke in `cache/timeline.json`.

### 6. Live player (`play.py`) using Pygame
**Layout** (`--layout side` default, `--layout stacked` optional):
- `side`: art on the left (full window height, aspect preserved), equation panel on the right. Good for landscape screens.
- `stacked`: art on top, equation panel below, portrait. Good for phone-style recordings.
- Window size: fit the current screen (about 95% of screen height), with `--scale` and `--fullscreen` options.

**Timing:** use a real-time clock (`time.perf_counter`). The animation position is computed from elapsed seconds, not from frame count, so it takes the target duration even if the frame rate dips. Target 60 fps.

**Drawing:**
- Keep a persistent `ink` surface. Each frame, draw only the newly revealed segments onto it.
- Fresh ink: segments drawn in the last ~0.4 s are drawn in gold `#FFD27A` on top; when they age out, they are drawn white `#F5F5F5` onto `ink`. Keep a small deque of recent segments.
- Pen tip: pre-render one soft glow sprite and blit it additively at the current point.
- Background `#05060A`. Grid pre-rendered once on its own surface: minor lines every 10 units (very faint), major every 50 units (faint), small dim tick labels on axes.
- Lines 2 px wide, anti-aliased (`pygame.draw.aalines` plus a 2 px line, or supersample if jagged).
- Equation panel: monospace font (try Consolas, DejaVu Sans Mono, Menlo, Courier New), typewriter effect at ~60 chars/s, active term highlighted in gold, region name, stroke counter and a thin progress bar. Large enough to read in a screen recording. Wrap long Bézier equations onto two lines.

**Controls** (show a tiny hint line that fades out after 5 s; `H` hides all HUD):
- `SPACE` start / pause / resume. **The program must wait for SPACE before starting**, so the user can begin screen recording first. After pressing SPACE, show a 3-2-1 countdown, then start.
- `R` restart, `ESC` or `Q` quit, `+` / `-` speed, `F` fullscreen, `S` save a screenshot to `shots/`.
- At the end, hold the finished picture with a subtle glow pulse. Optional `--loop` restarts after 5 s.

### 7. Entry point
`python main.py` builds if needed, then plays. Options: `--image reference.png --duration 75 --layout side|stacked --fullscreen --scale 1.0 --loop --rebuild --region halo,crown` (play only selected regions, for quick testing).

### 8. Verification (do all of these)
1. Run the build phase on `reference.png`.
2. Add a headless mode `--selftest` that uses `SDL_VIDEODRIVER=dummy`, simulates the clock, and saves: `shots/final_frame.png`, `shots/diff.png` (absolute difference vs the reference) with an SSIM/overlap score printed, and `shots/contact_sheet.png` (12 frames evenly spaced through the animation). Look at them. Missing big regions means fix tracing/fitting.
3. Measure render cost: report average and worst per-frame draw time in the selftest. It must average under 12 ms so 60 fps is realistic. If not, optimise (draw only new segments, smaller glow sprite, no full-surface blurs).
4. Confirm: grid visible, equation readable, strokes progress smoothly with no flicker, start waits for SPACE, pause/restart work.
5. Write `NOTES.md`: decisions, stroke counts per tier, fit error stats, build time, frame-time stats, how to run, recording tips.

## Quality bar
- The final picture is clearly the reference: halo circles, crown, face, eight arms with weapons, garlands and lion all present and sharp.
- Drawing feels purposeful: long lines first, details after, no random jumping across the canvas.
- Fast and watchable: no dead time, the equation always matches the line being drawn, no stutter during playback.

## If something goes wrong
- Skeleton breaks lines: dilate the binary image by 1 px before skeletonizing.
- Too many strokes (> 15,000): raise the minimum length and merge Tier C into region bursts.
- Playback stutters: precompute all curve samples in the build phase, draw only new segments per frame, avoid per-frame allocations.
- Fit errors on dense ornaments: use finer Bézier splitting rather than a worse equation type.
