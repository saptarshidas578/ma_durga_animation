"""Pygame live player and deterministic headless self-test."""

import math, os, time
from collections import deque
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw
import pygame
from skimage.metrics import structural_similarity

BG = (5, 6, 10)
WHITE = (245, 245, 245)
GOLD = (255, 210, 122)
GRID = (25, 27, 33)


class Player:
    def __init__(self, strokes, timeline, image_path, size=(1400, 900), layout="side", scale=1.0):
        pygame.init()
        self.strokes = strokes
        self.timeline = timeline
        self.size = size
        self.layout = layout
        self.screen = pygame.Surface(size)
        self.ink = pygame.Surface(size)
        self.ink.fill(BG)
        self.font = pygame.font.SysFont(["consolas", "dejavusansmono", "couriernew"], 28)
        self.eq_font = pygame.font.SysFont(["consolas", "dejavusansmono", "couriernew"], 20)
        self.small = pygame.font.SysFont(["consolas", "couriernew"], 18)
        ref = Image.open(image_path).convert("L")
        self.ref_size = ref.size
        sw, sh = size
        rw, rh = self.ref_size
        if layout == "side":
            panel = int(sw * 0.50)
            box = (sw - panel - 38, sh - 40)
            avail = (box[0], box[1])
            self.panel_x = sw - panel
            self.panel_rect = pygame.Rect(self.panel_x, 0, panel, sh)
            self.artbox = pygame.Rect(18, 20, *avail)
        else:
            panel = int(sh * 0.23)
            self.panel_x = 0
            self.panel_rect = pygame.Rect(0, sh - panel, sw, panel)
            self.artbox = pygame.Rect(20, 15, sw - 40, sh - panel - 25)
        self.artscale = min(self.artbox.width / rw, self.artbox.height / rh) * scale
        self.draw_w = int(rw * self.artscale)
        self.draw_h = int(rh * self.artscale)
        self.ox = self.artbox.x + (self.artbox.width - self.draw_w) // 2
        self.oy = self.artbox.y + (self.artbox.height - self.draw_h) // 2
        self._grid()
        self.points = [np.asarray(s["points"], dtype=np.float32) for s in strokes]
        self.schedules = [
            timeline["strokes"].get(
                str(s["id"]),
                {"start": 1, "end": 76, "label": "", "region": s["region"], "tier": s["tier"]},
            )
            for s in strokes
        ]
        self.pending = sorted(range(len(strokes)), key=lambda i: self.schedules[i]["start"])
        self.pending_i = 0
        self.active = []
        self.progress = np.zeros(len(strokes), dtype=np.int32)
        self.done = np.zeros(len(strokes), dtype=bool)
        self.recent = deque()
        self.hud = True
        self.start_wall = None
        self.elapsed = 0
        self.paused = False
        self.countdown = 0
        self.paused_at = 0
        self.hint_until = 5

    def xy(self, p):
        x, y = p
        return (
            round(self.ox + self.draw_w / 2 + x * 10 * self.artscale),
            round(self.oy + self.draw_h - y * 10 * self.artscale),
        )

    def _grid(self):
        self.grid = pygame.Surface(self.size, pygame.SRCALPHA)
        sw, sh = self.size
        step = max(8, int(100 * self.artscale))
        major = step * 5
        xstart = self.ox + self.draw_w // 2
        ybase = self.oy + self.draw_h
        x = xstart % step
        while x < sw:
            majorline = (x - xstart) % major == 0
            pygame.draw.line(
                self.grid, (46, 49, 57, 100) if majorline else (26, 28, 34, 90), (x, 0), (x, sh), 1
            )
            x += step
        y = ybase % step
        while y < sh:
            majorline = (y - ybase) % major == 0
            pygame.draw.line(
                self.grid, (46, 49, 57, 100) if majorline else (26, 28, 34, 90), (0, y), (sw, y), 1
            )
            y += step
        pygame.draw.line(self.grid, (70, 74, 84, 150), (xstart, 0), (xstart, sh), 1)
        pygame.draw.line(self.grid, (70, 74, 84, 150), (0, ybase), (sw, ybase), 1)
        for k in range(-100, 101, 5):
            xx = xstart + k * step // 10
            yy = ybase - k * step // 10
            if 0 <= xx < sw:
                pygame.draw.line(self.grid, (95, 98, 108, 150), (xx, ybase - 4), (xx, ybase + 4), 1)
            if 0 <= yy < sh:
                pygame.draw.line(
                    self.grid, (95, 98, 108, 150), (xstart - 4, yy), (xstart + 4, yy), 1
                )
            if k and k % 10 == 0:
                if 0 <= xx < sw:
                    self.grid.blit(
                        self.small.render(str(k), True, (86, 89, 98)), (xx + 3, ybase + 5)
                    )
                if 0 <= yy < sh:
                    self.grid.blit(
                        self.small.render(str(k), True, (86, 89, 98)), (xstart + 6, yy - 8)
                    )

    @staticmethod
    def eased(f):
        return f * f * (3 - 2 * f)

    def update(self, t):
        while (
            self.pending_i < len(self.pending)
            and self.schedules[self.pending[self.pending_i]]["start"] <= t
        ):
            i = self.pending[self.pending_i]
            self.pending_i += 1
            self.active.append(i)
        for i in self.active:
            pts = self.points[i]
            n = len(pts)
            if self.done[i] or n < 2:
                continue
            sc = self.schedules[i]
            frac = self.eased(
                max(0, min(1, (t - sc["start"]) / max(0.0001, sc["end"] - sc["start"])))
            )
            target = max(1, int(frac * (n - 1)))
            old = int(self.progress[i])
            if target > old:
                chunk = [self.xy(p) for p in pts[max(0, old) : target + 1]]
                if len(chunk) >= 2:
                    pygame.draw.aalines(self.ink, WHITE, False, chunk)
                    pygame.draw.lines(self.ink, WHITE, False, chunk, 2)
                    self.recent.append((t + 0.4, chunk))
                self.progress[i] = target
            if t >= sc["end"] and target >= n - 1:
                # Make sure the final point is drawn and seal the stroke.
                chunk = [self.xy(p) for p in pts[max(0, int(self.progress[i])) :]]
                if len(chunk) >= 2:
                    pygame.draw.lines(self.ink, WHITE, False, chunk, 2)
                self.done[i] = True
        self.active = [i for i in self.active if not self.done[i]]
        while self.recent and self.recent[0][0] < t:
            self.recent.popleft()

    def compose(self, t, save_path=None):
        self.screen.fill(BG)
        self.screen.blit(self.grid, (0, 0))
        self.screen.blit(self.ink, (0, 0))
        for expiry, chunk in self.recent:
            if len(chunk) >= 2:
                pygame.draw.lines(self.screen, GOLD, False, chunk, 2)
        current = None
        for i in self.active:
            if not self.done[i]:
                current = i
                break
        upcoming = None
        if current is None and self.pending_i < len(self.pending):
            candidate = self.pending[self.pending_i]
            if (
                self.schedules[candidate].get(
                    "label_start", self.schedules[candidate]["start"] - 0.1
                )
                <= t
            ):
                upcoming = candidate
        if current is not None and self.progress[current] < len(self.points[current]):
            p = self.xy(self.points[current][self.progress[current]])
            pygame.draw.circle(self.screen, (115, 80, 40), p, 11)
            pygame.draw.circle(self.screen, GOLD, p, 4)
        if self.hud:
            if self.layout == "side":
                pygame.draw.rect(self.screen, (9, 10, 15), self.panel_rect)
                x = self.panel_x + 22
                y = 26
                width = self.panel_rect.width - 44
            else:
                pygame.draw.rect(self.screen, (9, 10, 15), self.panel_rect)
                x = 24
                y = self.panel_rect.y + 16
                width = self.panel_rect.width - 48
            title = self.small.render("DURGA · EQUATION DRAWING", True, WHITE)
            self.screen.blit(title, (x, y))
            y += 38
            label_stroke = current if current is not None else upcoming
            if label_stroke is not None:
                sc = self.schedules[label_stroke]
                label = sc.get("label", "")
                if sc["tier"] != "A":
                    label = label[: max(1, int(max(0, t - sc["start"] + 0.1) * 60))]
                region_text = self.small.render(
                    f"{sc['region'].upper()}  ·  TIER {sc['tier']}", True, (24, 20, 12)
                )
                badge = pygame.Rect(
                    x, y, region_text.get_width() + 18, region_text.get_height() + 8
                )
                pygame.draw.rect(self.screen, GOLD, badge, border_radius=5)
                self.screen.blit(region_text, (x + 9, y + 4))
                y += badge.height + 13
                y = self._wrap(label, x, y, width)
            else:
                self.screen.blit(
                    self.small.render(
                        "Every curve is sampled from its fitted equation.", True, (180, 185, 195)
                    ),
                    (x, y),
                )
                y += 32
            progress = min(1, t / max(1, self.timeline["target_duration"] + 1))
            pygame.draw.rect(self.screen, (40, 42, 49), (x, y, width, 5))
            pygame.draw.rect(self.screen, GOLD, (x, y, int(width * progress), 5))
            y += 20
            count = int(self.done.sum())
            self.screen.blit(
                self.small.render(
                    f"{count:,} / {len(self.strokes):,} strokes   {progress*100:4.1f}%",
                    True,
                    (180, 185, 195),
                ),
                (x, y),
            )
            y += 30
            if t < 5:
                self.screen.blit(
                    self.small.render(
                        "SPACE start/pause · R restart · +/- speed · F fullscreen · H hide",
                        True,
                        (130, 135, 145),
                    ),
                    (x, y),
                )
            if self.countdown:
                txt = self.font.render(str(self.countdown), True, GOLD)
                self.screen.blit(
                    txt, (self.ox + self.draw_w // 2 - 10, self.oy + self.draw_h // 2 - 20)
                )
        if save_path:
            pygame.image.save(self.screen, str(save_path))
        return self.screen

    def _wrap(self, text, x, y, width):
        lines = []
        for block in text.splitlines() or [""]:
            line = ""
            for word in block.split(" "):
                test = (line + " " + word).strip()
                if self.eq_font.size(test)[0] <= width:
                    line = test
                elif line:
                    lines.append(line)
                    line = word
                else:
                    # Break long unspaced formula tokens by characters.
                    piece = ""
                    for char in word:
                        if self.eq_font.size(piece + char)[0] > width and piece:
                            lines.append(piece)
                            piece = char
                        else:
                            piece += char
                    line = piece
            if line:
                lines.append(line)
        for line in lines[:5]:
            self.screen.blit(self.eq_font.render(line, True, WHITE), (x, y))
            y += 26
        return y + 5

    def reset(self):
        self.ink.fill(BG)
        self.pending_i = 0
        self.active = []
        self.progress[:] = 0
        self.done[:] = False
        self.recent.clear()
        self.elapsed = 0
        self.countdown = 0
        self.start_wall = None

    def run(self, fullscreen=False, loop=False, speed=1.0):
        display = pygame.display.set_mode(self.size, pygame.FULLSCREEN if fullscreen else 0)
        pygame.display.set_caption("Durga · Equation Drawing — SPACE to start")
        clock = pygame.time.Clock()
        mode = "waiting"
        scale = speed
        start = time.perf_counter()
        countdown_start = None
        while True:
            for e in pygame.event.get():
                if e.type == pygame.QUIT:
                    return
                if e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_ESCAPE, pygame.K_q):
                        return
                    if e.key == pygame.K_h:
                        self.hud = not self.hud
                    if e.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                        scale *= 1.2
                    if e.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                        scale /= 1.2
                    if e.key == pygame.K_f:
                        fullscreen = not fullscreen
                        display = pygame.display.set_mode(
                            self.size, pygame.FULLSCREEN if fullscreen else 0
                        )
                    if e.key == pygame.K_s:
                        Path("shots").mkdir(exist_ok=True)
                        pygame.image.save(
                            self.compose(self.elapsed), f"shots/screenshot_{int(time.time())}.png"
                        )
                    if e.key == pygame.K_r:
                        self.reset()
                        mode = "waiting"
                    if e.key == pygame.K_SPACE:
                        if mode == "waiting":
                            mode = "countdown"
                            countdown_start = time.perf_counter()
                        elif mode == "countdown":
                            mode = "playing"
                            start = time.perf_counter() - self.elapsed / scale
                        elif mode == "playing":
                            mode = "paused"
                            self.paused_at = time.perf_counter()
                        elif mode == "paused":
                            start += time.perf_counter() - self.paused_at
                            mode = "playing"
            now = time.perf_counter()
            if mode == "countdown":
                passed = now - countdown_start
                self.countdown = max(1, 3 - int(passed))
                if passed >= 3:
                    mode = "playing"
                    self.countdown = 0
                    start = now
            if mode == "playing":
                self.elapsed = (now - start) * scale
                self.update(self.elapsed)
            frame = self.compose(self.elapsed)
            if mode == "waiting":
                txt = self.font.render(
                    "Press SPACE when your screen recording is ready", True, GOLD
                )
                frame.blit(
                    txt,
                    (self.ox + self.draw_w // 2 - txt.get_width() // 2, self.oy + self.draw_h - 45),
                )
            display.blit(frame, (0, 0))
            pygame.display.flip()
            clock.tick(60)
            if mode == "playing" and self.elapsed >= self.timeline["total_time"]:
                if loop:
                    self.reset()
                    mode = "waiting"
                else:
                    mode = "finished"


def selftest(strokes, timeline, image_path, layout="side"):
    Path("shots").mkdir(exist_ok=True)
    size = (1400, 900) if layout == "side" else (900, 1400)
    p = Player(strokes, timeline, image_path, size, layout)
    total = timeline["total_time"]
    frames = 600
    times = np.linspace(0, total, frames)
    checkpoints = set(np.linspace(0, frames - 1, 12, dtype=int).tolist())
    render_ms = []
    sheet = []
    for j, t in enumerate(times):
        before = time.perf_counter()
        p.update(float(t))
        surf = p.compose(float(t))
        render_ms.append((time.perf_counter() - before) * 1000)
        if j in checkpoints:
            sheet.append(surf.copy())
    final = p.compose(total)
    pygame.image.save(final, "shots/final_frame.png")
    # Compare the art viewport with the source at the same raster dimensions.
    src = Image.open(image_path).convert("L").resize((p.draw_w, p.draw_h), Image.Resampling.LANCZOS)
    crop = final.subsurface((p.ox, p.oy, p.draw_w, p.draw_h)).copy()
    rendered = Image.frombytes("RGB", crop.get_size(), pygame.image.tostring(crop, "RGB"))
    gray = np.asarray(rendered.convert("L"))
    ref = np.asarray(src)
    ref = ref[: gray.shape[0], : gray.shape[1]]
    # SSIM is reported as a structural metric; overlap compares bright ink masks.
    ssim = float(structural_similarity(ref, gray, data_range=255))
    a = ref > 100
    b = gray > 100
    overlap = float((a & b).sum() / max(1, (a | b).sum()))
    diff = np.abs(ref.astype(np.int16) - gray.astype(np.int16)).astype(np.uint8)
    Image.fromarray(diff).save("shots/diff.png")
    cols = 3
    thumb = (size[0] // 3, size[1] // 3)
    sheet_img = Image.new("RGB", (thumb[0] * cols, thumb[1] * 4), (5, 6, 10))
    for i, surf in enumerate(sheet):
        im = Image.frombytes("RGB", surf.get_size(), pygame.image.tostring(surf, "RGB"))
        im.thumbnail(thumb, Image.Resampling.LANCZOS)
        sheet_img.paste(im, ((i % cols) * thumb[0], (i // cols) * thumb[1]))
    sheet_img.save("shots/contact_sheet.png")
    avg = float(np.mean(render_ms))
    worst = float(np.max(render_ms))
    print(
        f"Selftest: SSIM={ssim:.4f} overlap={overlap:.4f}; render average={avg:.2f} ms worst={worst:.2f} ms over {frames} frames"
    )
    pygame.quit()
    return {"ssim": ssim, "overlap": overlap, "avg_ms": avg, "worst_ms": worst}
