# Durga line-art equation animation

## Run

From the repository root, install the dependencies and run:

```sh
python -m pip install -r requirements.txt
python main.py
```

This opens the live Pygame window and waits for **SPACE**. It then shows a 3 second countdown before drawing. The program does not export video. On another Python installation, install dependencies with `python -m pip install -r requirements.txt`, then run `python main.py`.

Useful options:

- `--duration 75` changes the drawing duration in seconds (default 75).
- `--layout stacked` uses a portrait layout; default `side` uses a landscape layout.
- `--fullscreen` starts fullscreen, and `--scale 0.9` adjusts the art size.
- `--loop` restarts after the finished image hold.
- `--region halo,crown` plays selected comma-separated regions.
- `--rebuild` reruns preprocessing, tracing, fitting, ordering, and caching.
- `--selftest` runs the headless verification and writes images to `shots/`.

Controls: SPACE starts, pauses, and resumes; R restarts; +/- changes playback speed; F toggles fullscreen; S saves a screenshot under `shots/`; H hides the HUD; ESC or Q quits.

## Pipeline and decisions

- `prep.py` applies Otsu thresholding, removes connected components smaller than 6 pixels, and skeletonizes. It handles the solid white face specially: instead of leaving the skeleton medial axis (which produced a diamond-like artifact), it traces the face component's boundary and enclosed feature contours. It saves `cache/skeleton.png` and `cache/preprocess_preview.png`.
- `trace.py` walks an 8-neighbour pixel graph, suppresses redundant diagonal links, keeps loops and branches, drops paths shorter than 4 pixels, and smooths while holding endpoints fixed.
- `fit.py` chooses line, circle, ellipse, or cubic Bezier chains. The displayed coordinates use a bottom-centre origin and one grid unit per 10 pixels. If a smoothed cubic chain would exceed 1.2 px from the traced centerline, it switches to a finer piecewise cubic representation of the raw path.
- `regions.py` assigns strokes to normalized image regions. `order.py` follows the skill's region order, draws longer tiers first, and uses a nearest endpoint walk with direction reversal.
- `timeline.py` puts Tier A strokes on their own equations and reserves a full 0.25 seconds before each one for reading. It batches Tier B in groups of ten and staggers Tier C over short regional bursts to avoid a single-frame spike. The reveal remains 75 seconds at the default setting, plus 1 second intro and 4 seconds end hold. If a requested duration is too short to fit every Tier A lead-in, it is extended automatically.
- `play.py` precomputes and caches curve samples, draws only new segments, uses a persistent ink surface and a 0.4 second gold trail, and bases playback on `time.perf_counter()`.

The equation panel uses a larger 20 px monospace font, with a highlighted region badge. Long cubic Bezier equations show the formula and control points on two lines. The side layout gives the panel half the window width for screen recording.

The cached source geometry remains in image pixel coordinates for fitting and is saved as bottom-centre grid-coordinate samples for playback. Generated caches can be removed and rebuilt with `--rebuild`.

## Build and fit results

- Build time: **11.4 seconds** in the verified run.
- Total strokes: **4,190**.
- Tiers: **A 202**, **B 858**, **C 3,130**.
- Equation types: 2,322 lines, 1,509 circles, 156 ellipses, 203 Bezier chains.
- Maximum sampled fit deviation: **1.199 px**; mean of per-stroke maxima: **0.367 px**; median: **0.291 px**. Mean per-stroke RMS deviation: **0.246 px**.

## Verification

Ran the full build on `assets/reference.png`, then `python main.py --rebuild --selftest`. Headless verification uses a simulated clock across 600 frames and produced:

- Average render time: **4.59 ms/frame** (below the 12 ms target).
- Worst frame: **19.86 ms**.
- Every Tier A stroke has a verified **0.25 second** full-equation lead-in.
- Final-frame comparison: SSIM **0.7148**, bright-pixel overlap **0.5464**. The reference uses thick white strokes; the generated image is a thin centerline animation, so overlap is lower even though the full composition is present.
- The 12-frame contact sheet shows the halo/crown first, then the face and body, arms and weapons, garlands, lion, and lower mandalas.

Images: `shots/final_frame.png`, `shots/diff.png`, `shots/contact_sheet.png`. Build and selftest metrics are also saved in `cache/build_stats.json` and `cache/selftest_stats.json`.

## Recording tips

Open the window, begin your screen recording, then press SPACE. The 3 second countdown gives time to settle before drawing begins. Keep the equation panel visible for the recording; use H only if you want a clean art-only view. `--layout stacked` is useful for portrait capture, while `--layout side` leaves more room for readable equations. For a shorter preview, try `--duration 20 --region halo,crown,face`.
