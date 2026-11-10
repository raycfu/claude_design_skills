#!/usr/bin/env python3
"""Reel builder: wraps your edited effect clips in a chat-style "typed a command, got an edit" reel.

Usage:
  python reel.py config.json                 # render the full reel (video + typing sounds)
  python reel.py config.json --test 3.0 9.5  # save still frames at those times for checking
  python reel.py config.json --info          # print duration and frame count

See ../examples/config.json for every option.
"""
import sys, os, json, math, subprocess, argparse, tempfile, shutil, wave
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIRS = [os.path.join(HERE, '..', 'fonts'), os.path.join(HERE, '..', '..', 'effects', 'fonts'),
             os.path.expanduser('~/.claude/skills/effects/fonts')]

def find_font(name):
    for d in FONT_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p): return p
    raise SystemExit(f'Font {name} not found. Install the effects skill or put {name} in reel-builder/fonts.')

INTER, SERIF, MONO = find_font('Inter.ttf'), find_font('PlayfairDisplay.ttf'), find_font('SpaceMono-Bold.ttf')
_fc = {}
def F(weight, size, path=None):
    path = path or INTER
    k = (path, weight, int(size))
    if k not in _fc:
        f = ImageFont.truetype(path, int(size))
        try:
            axes = f.get_variation_axes()
            vals = [max(a['minimum'], min(a['maximum'], weight)) if a['name'] in (b'Weight', 'Weight') else a['default'] for a in axes]
            f.set_variation_by_axes(vals)
        except Exception:
            pass
        _fc[k] = f
    return _fc[k]
R, M, SB, B, XB = 400, 500, 600, 700, 800

W, H, FPS = 1080, 1920, 30
BG = (38, 38, 36); PANEL = (48, 48, 46); KEY = (68, 68, 66); KEY2 = (52, 52, 50)
TXT = (236, 234, 228); DIM = (150, 148, 142); ORANGE = (217, 119, 87); ORDK = (92, 52, 40)
# per-effect cycle: typing until T_SEND, dot build T_DOT..T_CARD, card plays until T_ZOOM, zoom until T_FULL, then full screen
T_SEND, T_DOT, T_CARD, T_ZOOM, T_FULL = 0.92, 0.95, 1.4, 1.95, 2.2
CX0, CY0, CW, CH = 36, 552, 640, 1138

def clamp(x, a=0.0, b=1.0): return max(a, min(b, x))
def eout(t): t = clamp(t); return 1 - (1 - t) ** 3
def einout(t): t = clamp(t); return t * t * (3 - 2 * t)

class Reader:
    """Sequential frame reader with cheap forward seeking."""
    def __init__(self, path):
        if not os.path.exists(path): raise SystemExit(f'Missing clip: {path}')
        self.path = path; self.cap = None; self.idx = -1; self.last = None
    def get(self, i):
        i = max(0, i)
        if self.cap is None or i < self.idx:
            if self.cap: self.cap.release()
            self.cap = cv2.VideoCapture(self.path); self.cap.set(cv2.CAP_PROP_POS_FRAMES, i); self.idx = i - 1
        while self.idx < i:
            ok, fr = self.cap.read()
            if not ok: break
            self.idx += 1
            if fr.shape[1] != W or fr.shape[0] != H: fr = cv2.resize(fr, (W, H), interpolation=cv2.INTER_AREA)
            self.last = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        if self.last is None: raise SystemExit(f'Could not read frames from {self.path}')
        return self.last

def still(path, t=0.0):
    cap = cv2.VideoCapture(path); cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * FPS)); ok, fr = cap.read(); cap.release()
    if not ok: raise SystemExit(f'Could not read a frame from {path}')
    return Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))

def rounded(im, r):
    im = im.convert('RGBA'); m = Image.new('L', im.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, im.width - 1, im.height - 1], max(0, r), fill=255)
    a = np.minimum(np.asarray(im.getchannel('A')), np.asarray(m)); im.putalpha(Image.fromarray(a)); return im

def cover(im, w, h, r):
    sc = max(w / im.width, h / im.height)
    t2 = im.resize((int(im.width * sc) + 1, int(im.height * sc) + 1), Image.LANCZOS)
    x0 = (t2.width - w) // 2; y0 = (t2.height - h) // 2
    return rounded(t2.crop((x0, y0, x0 + w, y0 + h)), r)

def icon(d, cx, cy, r, t, spin=True):
    """Original working indicator: a spinning ring, a solid dot when idle."""
    if spin:
        a0 = (t * 520) % 360
        d.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill=(90, 60, 50), width=max(3, int(r * 0.32)))
        d.arc([cx - r, cy - r, cx + r, cy + r], a0, a0 + 110, fill=ORANGE, width=max(3, int(r * 0.32)))
    else:
        d.ellipse([cx - r * 0.7, cy - r * 0.7, cx + r * 0.7, cy + r * 0.7], fill=ORANGE)

def topbar(d):
    d.ellipse([45, 87, 135, 177], fill=(52, 52, 50))
    for yy, x1 in ((124, 104), (140, 98)): d.line([(76, yy), (x1, yy)], fill=TXT, width=4)
    d.rounded_rectangle([382, 92, 698, 172], 40, fill=(52, 52, 50))
    d.rounded_rectangle([540, 100, 690, 164], 32, fill=(76, 76, 73))
    d.text((461, 132), 'Chat', font=F(M, 36), fill=DIM, anchor='mm')
    d.text((615, 132), 'Code', font=F(SB, 36), fill=TXT, anchor='mm')
    d.ellipse([945, 87, 1035, 177], fill=(52, 52, 50))
    d.rounded_rectangle([974, 116, 1002, 146], 5, outline=TXT, width=3)
    d.line([(990, 130), (1010, 108)], fill=TXT, width=4)

ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
KW, KH, KG = 94, 112, 13
KY = [1375, 1515, 1655, 1795]
def key_rect(ch):
    for ri, row in enumerate(ROWS):
        if ch in row:
            n = len(row); x0 = (W - (n * KW + (n - 1) * KG)) / 2
            x = x0 + row.index(ch) * (KW + KG); return x, KY[ri], x + KW, KY[ri] + KH
    if ch in '/-_': return 740, KY[3], 920, KY[3] + KH
    return None

def keyboard(c, pressed, typed_word):
    d = ImageDraw.Draw(c)
    d.rectangle([0, 1240, W, H], fill=(33, 33, 31))
    d.line([(0, 1330), (W, 1330)], fill=(52, 52, 50), width=2)
    if typed_word: d.text((210, 1285), f'“{typed_word}”', font=F(M, 32), fill=DIM, anchor='mm')
    for row in ROWS:
        for ch in row:
            x0, y0, x1, y1 = key_rect(ch)
            d.rounded_rectangle([x0, y0, x1, y1], 14, fill=KEY)
            d.text(((x0 + x1) / 2, (y0 + y1) / 2 - 2), ch, font=F(R, 48), fill=TXT, anchor='mm')
    d.rounded_rectangle([20, KY[2], 133, KY[2] + KH], 14, fill=KEY2)
    d.polygon([(76, KY[2] + 34), (54, KY[2] + 60), (66, KY[2] + 60), (66, KY[2] + 78), (86, KY[2] + 78), (86, KY[2] + 60), (98, KY[2] + 60)], outline=TXT, width=3)
    d.rounded_rectangle([947, KY[2], 1060, KY[2] + KH], 14, fill=KEY2)
    d.polygon([(975, KY[2] + 56), (992, KY[2] + 38), (1032, KY[2] + 38), (1032, KY[2] + 74), (992, KY[2] + 74)], outline=TXT, width=3)
    d.rounded_rectangle([75, KY[3], 270, KY[3] + KH], 14, fill=KEY2); d.text((172, KY[3] + KH / 2), '123', font=F(R, 38), fill=TXT, anchor='mm')
    d.rounded_rectangle([290, KY[3], 715, KY[3] + KH], 14, fill=KEY); d.text((502, KY[3] + KH / 2), 'space', font=F(R, 38), fill=TXT, anchor='mm')
    d.rounded_rectangle([740, KY[3], 920, KY[3] + KH], 14, fill=KEY2); d.text((830, KY[3] + KH / 2), '/', font=F(R, 42), fill=TXT, anchor='mm')
    if pressed and pressed != ' ':
        kr = key_rect(pressed)
        if kr:
            x0, y0, x1, y1 = kr; cx = (x0 + x1) / 2; top = y0 - 150
            d.rounded_rectangle([cx - 60, top, cx + 60, y1], 18, fill=(110, 110, 106))
            d.text((cx, top + 62), pressed, font=F(R, 64), fill=TXT, anchor='mm')

def composer(c, thumb, text, t, y0=815, placeholder='Reply to Claude...'):
    d = ImageDraw.Draw(c)
    d.rounded_rectangle([30, y0, 1050, y0 + 405], 42, fill=PANEL)
    if thumb is not None:
        c.alpha_composite(cover(thumb, 112, 158, 14), (56, y0 + 22)); d = ImageDraw.Draw(c)
        d.ellipse([150, y0 + 16, 178, y0 + 44], fill=(240, 240, 236)); d.text((164, y0 + 30), '×', font=F(B, 22), fill=(30, 30, 30), anchor='mm')
    ty = y0 + 243
    if text:
        d.text((56, ty), text, font=F(R, 46), fill=TXT, anchor='lm'); x = 56 + d.textlength(text, font=F(R, 46)) + 3
    else:
        d.text((56, ty), placeholder, font=F(R, 44), fill=DIM, anchor='lm'); x = 56
    if (t * 2.2) % 1 < 0.6: d.rectangle([x, ty - 30, x + 3, ty + 30], fill=ORANGE if text else TXT)
    iy = y0 + 345
    d.line([(64, iy), (96, iy)], fill=DIM, width=4); d.line([(80, iy - 16), (80, iy + 16)], fill=DIM, width=4)
    for yy, xx in ((iy - 9, 152), (iy + 9, 136)):
        d.line([(124, yy), (164, yy)], fill=DIM, width=3); d.ellipse([xx - 6, yy - 6, xx + 6, yy + 6], outline=DIM, width=3, fill=PANEL)
    d.rounded_rectangle([808, iy - 22, 828, iy + 10], 10, outline=DIM, width=3); d.arc([802, iy - 8, 834, iy + 18], 0, 180, fill=DIM, width=3)
    d.line([(818, iy + 18), (818, iy + 26)], fill=DIM, width=3)
    d.rounded_rectangle([870, iy - 37, 944, iy + 37], 22, fill=ORANGE)
    d.line([(907, iy + 20), (907, iy - 20)], fill=(255, 255, 255), width=6)
    d.line([(890, iy - 3), (907, iy - 20), (924, iy - 3)], fill=(255, 255, 255), width=6, joint='curve')

def menu(c, items, y_bottom=790):
    d = ImageDraw.Draw(c); ih = 104
    y0 = y_bottom - len(items) * ih - 26
    d.rounded_rectangle([30, y0, 1050, y_bottom], 32, fill=(46, 46, 44))
    for i, (a, b, hi) in enumerate(items):
        yy = y0 + 13 + i * ih
        if hi: d.rounded_rectangle([42, yy, 1038, yy + ih - 6], 24, fill=(64, 64, 61))
        d.text((66, yy + 34), a, font=F(SB, 40), fill=TXT, anchor='lm')
        d.text((66, yy + 76), b, font=F(R, 29), fill=DIM, anchor='lm')

def reply_bar(c):
    d = ImageDraw.Draw(c)
    d.rounded_rectangle([28, 1770, 1052, 1882], 56, fill=(48, 48, 46))
    d.text((70, 1826), '+', font=F(R, 44), fill=DIM, anchor='mm')
    d.text((110, 1826), 'Reply to Claude...', font=F(R, 42), fill=DIM, anchor='lm')
    d.rounded_rectangle([902, 1800, 922, 1832], 10, outline=DIM, width=3); d.arc([895, 1814, 929, 1846], 0, 180, fill=DIM, width=3)
    d.line([(912, 1846), (912, 1856)], fill=DIM, width=3)
    d.ellipse([950, 1790, 1022, 1862], fill=(64, 64, 61))
    d.line([(986, 1842), (986, 1810)], fill=TXT, width=5); d.line([(972, 1824), (986, 1810), (1000, 1824)], fill=TXT, width=5)

def bubble_right(c, thumb, text):
    d = ImageDraw.Draw(c)
    if thumb is not None:
        c.alpha_composite(cover(thumb, 104, 160, 16), (918, 200)); d = ImageDraw.Draw(c)
    f = F(R, 40); tw = d.textlength(text, font=f)
    y = 400 if thumb is not None else 230
    d.rounded_rectangle([1026 - tw - 56, y - 38, 1026, y + 38], 38, fill=ORDK)
    d.text((1026 - 28, y), text, font=f, fill=ORANGE, anchor='rm')

CELL = 13
_rnd = {}
def dots(img, k):
    """Orange dot mosaic that resolves into the frame as k goes 0 -> 1."""
    h, w = img.shape[:2]; gh, gw = h // CELL, w // CELL
    small = cv2.resize(img[:gh * CELL, :gw * CELL], (gw, gh), interpolation=cv2.INTER_AREA)
    lum = small.mean(-1, keepdims=True) / 255
    if (gh, gw) not in _rnd: _rnd[(gh, gw)] = np.random.default_rng(7).random((gh, gw))
    rnd = _rnd[(gh, gw)]
    p1 = clamp(k / 0.45)
    on = (rnd < p1 * 1.15).astype(np.float32)[..., None]
    colmix = clamp((k - 0.3) / 0.4)
    col = np.array(ORANGE, np.float32) * (0.35 + 0.65 * lum) * (1 - colmix) + small * colmix
    rad = (0.28 + 0.2 * lum[..., 0]) * CELL * (0.6 + 0.4 * p1)
    yy, xx = np.mgrid[0:CELL, 0:CELL].astype(np.float32) - CELL / 2 + 0.5
    D = np.tile(np.sqrt(xx ** 2 + yy ** 2), (gh, gw))
    Rr = np.repeat(np.repeat(rad, CELL, 0), CELL, 1)
    m = np.clip(Rr - D + 0.7, 0, 1)[..., None]
    out = np.zeros_like(img)
    out[:gh * CELL, :gw * CELL] = np.repeat(np.repeat(col * on, CELL, 0), CELL, 1) * m
    mix = einout((k - 0.62) / 0.38)
    return np.clip(out * (1 - mix) + img * mix, 0, 255)

def card_img(frame_rgb, w, h, k_dots):
    img = cv2.resize(frame_rgb, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32)
    if k_dots < 1: img = dots(img, k_dots)
    return Image.fromarray(img.astype(np.uint8))

def zoom_to_full(c, fr, x0c, y0c, z):
    x0 = x0c * (1 - z); y0 = y0c * (1 - z); w = CW + (W - CW) * z; h = CH + (H - CH) * z
    ci = Image.fromarray(fr).resize((int(w), int(h)), Image.LANCZOS)
    c.alpha_composite(rounded(ci, int(22 * (1 - z))), (int(x0), int(y0)))


class Reel:
    def __init__(self, cfg, base):
        self.cfg = cfg
        P = lambda p: p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))
        self.full = float(cfg.get('full_seconds', 2.0))
        self.cyc = T_FULL + self.full
        self.fx = []
        for e in cfg['effects']:
            raw = P(e.get('raw', e['edited']))
            self.fx.append(dict(name=e['name'], desc=e.get('desc', ''), reader=Reader(P(e['edited'])),
                                thumb=still(raw, 0).resize((240, 427), Image.LANCZOS), offset=float(e.get('offset', 0.0))))
        co = cfg.get('cold_open') or {}
        self.open = float(co.get('seconds', 1.4)) if co else 0.0
        self.co_lines = co.get('lines', ['Claude', 'edited', 'this.'])
        self.co_fx = int(co.get('effect', 0))
        self.co_at = float(co.get('from', 2.0))
        self.co_y = float(co.get('y', 360)); self.co_gap = float(co.get('gap', 165)); self.co_step = float(co.get('stagger', 0.15))
        self.end0 = self.open + len(self.fx) * self.cyc
        self.end_len = float(cfg.get('end_seconds', 5.6))
        self.dur = self.end0 + self.end_len
        self.word = cfg.get('cta_word', 'EFFECT')
        self.cmd = '/' + cfg.get('end_command', self.word.lower())
        self.greet = cfg.get('greeting', 'Evening, Ray')
        self.reply1 = cfg.get('reply_line1', f'Comment “{self.word}” and I’ll send you')
        self.reply2 = cfg.get('reply_line2', 'the prompts')
        self.grid_setup(cfg.get('grid', [])[:8], P)

    # ---- timings ----
    @staticmethod
    def key_times(n):
        step = min(0.07, 0.74 / max(1, n)); return [0.1 + step * i for i in range(n)]
    def end_key_times(self): return [0.1 + 0.09 * i for i in range(len(self.cmd))]
    def end_send(self): return self.end_key_times()[-1] + 0.21
    def sfx_times(self):
        out = []
        for k, f in enumerate(self.fx):
            out += [self.open + k * self.cyc + x for x in self.key_times(len('/' + f['name']))]
        return out + [self.end0 + x for x in self.end_key_times()]

    # ---- pieces ----
    def effect_frame(self, k, ct):
        f = self.fx[k]; return f['reader'].get(int((f['offset'] + ct) * FPS))

    def cycle(self, k, lt):
        f = self.fx[k]; cmd = '/' + f['name']
        c = Image.new('RGBA', (W, H), BG + (255,)); d = ImageDraw.Draw(c); topbar(d)
        if lt < T_SEND:
            ti = self.key_times(len(cmd)); nt = sum(lt >= x for x in ti); txt = cmd[:nt]
            pressed = cmd[nt - 1] if nt > 0 and lt - ti[nt - 1] < 0.07 else None
            if len(txt) >= 2: menu(c, [(cmd, f['desc'], True)])
            composer(c, f['thumb'], txt, lt)
            word = txt.lstrip('/'); keyboard(c, pressed, word[-7:] if word else '')
            if lt > T_SEND - 0.07: ImageDraw.Draw(c).rounded_rectangle([866, 1123, 948, 1197], 24, outline=(255, 210, 190), width=4)
            return c
        bubble_right(c, f['thumb'], cmd); d = ImageDraw.Draw(c)
        icon(d, 78, 512, 17, lt)
        d.text((118, 512), f"Editing with {f['name']}...", font=F(R, 38), fill=(200, 198, 192), anchor='lm')
        reply_bar(c)
        if lt < T_DOT: return c
        fr = self.effect_frame(k, lt - T_DOT)
        if lt < T_ZOOM:
            c.alpha_composite(rounded(card_img(fr, CW, CH, clamp((lt - T_DOT) / (T_CARD - T_DOT))), 22), (CX0, CY0)); return c
        zoom_to_full(c, fr, CX0, CY0, einout((lt - T_ZOOM) / (T_FULL - T_ZOOM)))
        return c

    def cold_open(self, t):
        f = self.fx[self.co_fx]; hold = self.open - 0.3
        if t < hold:
            c = Image.fromarray(f['reader'].get(int((self.co_at + t) * FPS))).convert('RGBA')
            z = 1.06 - 0.06 * eout(t / hold)
            im = c.resize((int(W * z), int(H * z)), Image.LANCZOS)
            c = im.crop(((im.width - W) // 2, (im.height - H) // 2, (im.width - W) // 2 + W, (im.height - H) // 2 + H))
            for i, txt in enumerate(self.co_lines):
                t0 = 0.05 + self.co_step * i
                if t < t0: continue
                a = eout((t - t0) / 0.1)
                lay = Image.new('RGBA', (W, 200), (0, 0, 0, 0)); ld = ImageDraw.Draw(lay)
                ld.text((W / 2, 104), txt, font=F(XB, 150), fill=(0, 0, 0, 160), anchor='mm'); lay = lay.filter(ImageFilter.GaussianBlur(10))
                ImageDraw.Draw(lay).text((W / 2, 100), txt, font=F(XB, 150), fill=(ORANGE + (255,)) if i == len(self.co_lines) - 1 else (255, 255, 255, 255), anchor='mm')
                s = 1.5 - 0.5 * a
                lay = lay.resize((int(W * s), int(200 * s)), Image.LANCZOS)
                c.alpha_composite(lay, (int(W / 2 - lay.width / 2), int(self.co_y + i * self.co_gap - lay.height / 2)))
            return c
        u = (t - hold) / 0.3
        fr = f['reader'].get(int(max(0, self.co_at + hold - u * 3.0) * FPS)).astype(np.float32)
        sh = int(18 * (1 - u) + 6)
        out = fr.copy(); out[..., 0] = np.roll(fr[..., 0], sh, 1); out[..., 2] = np.roll(fr[..., 2], -sh, 1)
        for r in np.random.default_rng(int(t * 100)).integers(0, H, 14): out[r:r + 30] = np.roll(out[r:r + 30], int(80 * (1 - u)), 1)
        bg = Image.new('RGBA', (W, H), BG + (255,)); topbar(ImageDraw.Draw(bg))
        z = einout(u); w = W + (CW - W) * z; h = H + (CH - H) * z
        im = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).resize((int(w), int(h)), Image.LANCZOS)
        bg.alpha_composite(rounded(im, int(22 * z)), (int(CX0 * z), int(CY0 * z)))
        if u > 0.75: bg.alpha_composite(Image.new('RGBA', (W, H), BG + (int(255 * (u - 0.75) / 0.25),)))
        return bg

    # ---- end grid: live tiles, warm glow, animated CTA ----
    def grid_setup(self, grid, P):
        cfg = self.cfg; tw, gap = 244, 14; th = int(tw * 16 / 9); band = 430
        gx0 = (W - (4 * tw + 3 * gap)) / 2; row1 = H / 2 - band / 2 - gap - th; row2 = H / 2 + band / 2 + gap
        self.g_tw, self.g_th = tw, th
        self.g_pos = [(gx0 + (i % 4) * (tw + gap), row1 if i < 4 else row2) for i in range(len(grid))]
        self.g_frames, self.g_labels = [], []
        for g in grid:
            cap = cv2.VideoCapture(P(g['clip'])); cap.set(cv2.CAP_PROP_POS_FRAMES, int(float(g.get('t', 1.0)) * FPS)); fr = []
            while len(fr) < int(FPS * 2.4):
                ok, f = cap.read()
                if not ok: break
                f = cv2.resize(f, (tw * 2, int(tw * 2 * f.shape[0] / f.shape[1])), interpolation=cv2.INTER_AREA)
                fr.append(np.asarray(cover(Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB)), tw, th, 18)))
            cap.release()
            if not fr: raise SystemExit(f"Could not read grid clip {g['clip']}")
            self.g_frames.append(fr + fr[::-1][1:-1])
            lab = g.get('label', '')
            if lab:
                f = F(SB, 21); lw = int(ImageDraw.Draw(Image.new('L', (1, 1))).textlength(lab, font=f)) + 24
                im = Image.new('RGBA', (lw, 36), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
                d.rounded_rectangle([0, 0, lw - 1, 35], 18, fill=(10, 10, 10, 200)); d.text((12, 18), lab, font=f, fill=(255, 255, 255), anchor='lm')
                self.g_labels.append(im)
            else: self.g_labels.append(None)
        # background: deep charcoal, warm glow behind the CTA, fine grain
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.32)) ** 2)
        glow = np.clip(1 - r, 0, 1) ** 2.2
        bg = np.array([17, 16, 15], np.float32) + glow[..., None] * np.array([96, 46, 26], np.float32)
        bg += np.random.default_rng(3).normal(0, 2.2, (H, W, 1))
        self.g_bg = Image.fromarray(np.clip(bg, 0, 255).astype(np.uint8)).convert('RGBA')
        sh = Image.new('RGBA', (tw + 80, th + 80), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle([40, 52, tw + 40, th + 52], 20, fill=(0, 0, 0, 170))
        self.g_shadow = np.asarray(sh.filter(ImageFilter.GaussianBlur(16))).copy()
        rim = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
        ImageDraw.Draw(rim).rounded_rectangle([0, 0, tw - 1, th - 1], 18, outline=(255, 255, 255, 46), width=2)
        self.g_rim = rim
        # centre text layers
        def txt(t, font, fill, glow_col=None, gr=26):
            d0 = ImageDraw.Draw(Image.new('L', (1, 1))); bb = d0.textbbox((0, 0), t, font=font)
            w, h = bb[2] - bb[0] + gr * 4, bb[3] - bb[1] + gr * 4
            im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
            if glow_col:
                g2 = Image.new('RGBA', (w, h), (0, 0, 0, 0)); ImageDraw.Draw(g2).text((gr * 2 - bb[0], gr * 2 - bb[1]), t, font=font, fill=glow_col)
                im.alpha_composite(g2.filter(ImageFilter.GaussianBlur(gr)))
            ImageDraw.Draw(im).text((gr * 2 - bb[0], gr * 2 - bb[1]), t, font=font, fill=fill); return im
        self.t_title = txt(cfg.get('grid_title', 'Effect of the Day'), F(XB, 92), (255, 255, 255, 255), (0, 0, 0, 160), 14)
        self.t_sub = txt(cfg.get('grid_subtitle', f'{len(grid)} effects  ·  made in Claude'), F(M, 38), ORANGE + (255,), None, 4)
        self.t_comment = txt('Comment', F(SB, 66), (236, 232, 224, 255), (0, 0, 0, 170), 12)
        self.t_word = txt(f'“{self.word}”', F(XB, 168), (255, 255, 255, 255), ORANGE + (230,), 30)
        wm = txt(f'“{self.word}”', F(XB, 168), (255, 255, 255, 255), None, 30); self.t_word_mask = np.asarray(wm)[..., 3].astype(np.float32) / 255
        pf = F(SB, 42); ptx = cfg.get('cta_pill', 'for every effect’s prompt'); pw = int(ImageDraw.Draw(Image.new('L', (1, 1))).textlength(ptx, font=pf)) + 64
        pill = Image.new('RGBA', (pw, 74), (0, 0, 0, 0)); d = ImageDraw.Draw(pill)
        d.rounded_rectangle([0, 0, pw - 1, 73], 37, fill=ORANGE + (255,)); d.text((pw / 2, 37), ptx, font=pf, fill=(255, 255, 255), anchor='mm')
        self.t_pill = pill
        self.t_head = txt(cfg.get('grid_header', 'CLAUDE VIDEO EFFECTS').upper(), F(B, 34), (236, 232, 224, 230), None, 4)
        hw = self.t_head.width
        dot = Image.new('RGBA', (hw + 60, self.t_head.height), (0, 0, 0, 0)); ImageDraw.Draw(dot).ellipse([4, dot.height / 2 - 9, 22, dot.height / 2 + 9], fill=ORANGE + (255,))
        dot.alpha_composite(self.t_head, (52, 0)); self.t_head = dot
        self.t_foot = txt(cfg.get('grid_footer', '@raycfu  ·  follow for more'), F(M, 34), (200, 196, 188, 230), None, 4)
        self.g_top = row1; self.g_bot = row2 + th
        more = cfg.get('more_label'); self.t_more = None
        if more:
            mf = F(M, 30); mw = int(ImageDraw.Draw(Image.new('L', (1, 1))).textlength(more, font=mf)) + 48
            m = Image.new('RGBA', (mw, 48), (0, 0, 0, 0)); d = ImageDraw.Draw(m)
            d.rounded_rectangle([0, 0, mw - 1, 47], 24, fill=(255, 255, 255, 22), outline=(255, 255, 255, 70), width=2)
            d.text((mw / 2, 24), more, font=mf, fill=(236, 232, 224), anchor='mm'); self.t_more = m

    @staticmethod
    def _put(c, im, cx, cy, s=1.0, a=1.0):
        if a <= 0.01 or s <= 0.01: return
        if abs(s - 1) > 0.004: im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BILINEAR)
        if a < 0.999:
            arr = np.asarray(im).copy(); arr[..., 3] = (arr[..., 3] * a).astype(np.uint8); im = Image.fromarray(arr)
        c.alpha_composite(im, (int(cx - im.width / 2), int(cy - im.height / 2)))

    def grid_frame(self, gt, cta):
        c = self.g_bg.copy(); fi = int(gt * FPS); tw, th = self.g_tw, self.g_th
        dim = 1 - 0.42 * eout(cta)
        for i, (x, y) in enumerate(self.g_pos):
            k = eout((gt - 0.045 * i) / 0.4)
            if k <= 0: continue
            s = 0.88 + 0.12 * k; drift = (1 - k) * 40 * (1 if i < 4 else -1)
            sh = self.g_shadow.copy(); sh[..., 3] = (sh[..., 3] * k * (0.6 + 0.4 * dim)).astype(np.uint8)
            self._put(c, Image.fromarray(sh), x + tw / 2, y + th / 2 + 12 + drift, s)
            arr = self.g_frames[i][fi % len(self.g_frames[i])].copy()
            if dim < 0.999: arr[..., :3] = (arr[..., :3] * dim).astype(np.uint8)
            tile = Image.fromarray(arr); tile.alpha_composite(self.g_rim)
            lab = self.g_labels[i]
            if lab: tile.alpha_composite(lab, (10, th - 46))
            self._put(c, tile, x + tw / 2, y + th / 2 + drift, s, k)
        kh = eout((gt - 0.55) / 0.4)
        self._put(c, self.t_head, W / 2, self.g_top - 70 + 16 * (1 - kh), 1, kh)
        self._put(c, self.t_foot, W / 2, self.g_bot + 70 - 16 * (1 - kh), 1, kh)
        cy = H / 2
        pre = 1 - eout(cta / 0.5)
        if pre > 0:
            k1 = eout((gt - 0.35) / 0.35)
            self._put(c, self.t_title, W / 2, cy - 40 - 30 * (1 - k1), 1, k1 * pre)
            self._put(c, self.t_sub, W / 2, cy + 48, 1, eout((gt - 0.5) / 0.35) * pre)
        if cta > 0:
            k1 = eout(cta / 0.45); k2 = eout((cta - 0.12) / 0.5); k3 = eout((cta - 0.35) / 0.45); k4 = eout((cta - 0.5) / 0.45)
            self._put(c, self.t_comment, W / 2, cy - 152 + 20 * (1 - k1), 1, k1)
            wy = cy - 38; ws = 1.35 - 0.35 * k2
            self._put(c, self.t_word, W / 2, wy, ws, k2)
            sp = (gt * 0.9) % 1.6  # shine sweep across the word, repeating
            if k2 >= 1 and sp < 0.7:
                m = self.t_word_mask; hh, ww = m.shape; xs = np.arange(ww, dtype=np.float32)
                band = np.clip(1 - np.abs(xs - (-0.2 + 1.4 * sp / 0.7) * ww + (np.arange(hh)[:, None] * 0.35)) / (ww * 0.06), 0, 1)
                sh = np.zeros((hh, ww, 4), np.uint8); sh[..., :3] = 255; sh[..., 3] = (m * band * 150).astype(np.uint8)
                self._put(c, Image.fromarray(sh), W / 2, wy)
            pulse = 1 + 0.025 * math.sin(gt * 6.0) * k3
            self._put(c, self.t_pill, W / 2, cy + 88 + 24 * (1 - k3), (0.9 + 0.1 * k3) * pulse, k3)
            if self.t_more is not None: self._put(c, self.t_more, W / 2, cy + 168 + 20 * (1 - k4), 1, k4)
        return np.asarray(c.convert('RGB'))

    def end(self, lt):
        c = Image.new('RGBA', (W, H), BG + (255,)); d = ImageDraw.Draw(c); topbar(d)
        cmd = self.cmd; send = self.end_send()
        if lt < send:
            icon(d, W / 2, 470, 34, lt, spin=False)
            d.text((W / 2, 570), self.greet, font=F(R, 76, SERIF), fill=(226, 222, 212), anchor='mm')
            ti = self.end_key_times(); nt = sum(lt >= x for x in ti); txt = cmd[:nt]
            pressed = cmd[nt - 1] if nt and lt - ti[nt - 1] < 0.07 else None
            if len(txt) >= 2: menu(c, [(cmd, self.cfg.get('end_desc', 'every effect, one prompt each'), True)])
            composer(c, None, txt, lt, placeholder='Chat with Claude')
            keyboard(c, pressed, txt.lstrip('/'))
            return c
        bubble_right(c, None, cmd); d = ImageDraw.Draw(c)
        r0 = send + 0.15; full = self.reply1 + ' ' + self.reply2
        if lt >= r0:
            icon(d, 78, 352, 17, lt, spin=lt < r0 + 0.75)
            sh = full[:int(len(full) * clamp((lt - r0) / 0.7))]
            d.text((118, 352), sh[:len(self.reply1)], font=F(R, 38), fill=TXT, anchor='lm')
            if len(sh) > len(self.reply1): d.text((118, 404), sh[len(self.reply1) + 1:], font=F(R, 38), fill=TXT, anchor='lm')
        reply_bar(c)
        D0 = r0 + 0.75; D1, Z0, Z1 = D0 + 0.45, D0 + 0.95, D0 + 1.2
        if lt < D0: return c
        gt = lt - D0; cta = clamp((lt - Z1 - 0.3) / 1.0)
        g = self.grid_frame(gt, cta)
        if lt < Z0:
            c.alpha_composite(rounded(card_img(g, CW, CH, clamp((lt - D0) / (D1 - D0))), 22), (CX0, 470)); return c
        if lt >= Z1: return Image.fromarray(g).convert('RGBA')
        zoom_to_full(c, g, CX0, 470, einout((lt - Z0) / (Z1 - Z0)))
        return c

    def frame(self, t):
        if t < self.open: c = self.cold_open(t)
        elif t < self.end0:
            tt = t - self.open; k = int(tt // self.cyc); c = self.cycle(k, tt - k * self.cyc)
        else: c = self.end(t - self.end0)
        img = np.asarray(c.convert('RGB'))
        if t > self.dur - 0.1: img = (img * clamp((self.dur - t) / 0.1)).astype(np.uint8)
        return img


def typing_wav(times, dur, path, seed=11):
    """Soft keyboard clicks, one per keypress, nothing else (leave room for your own music)."""
    SR = 48000; rng = np.random.default_rng(seed); buf = np.zeros((int(dur * SR) + 1, 2))
    def bandpass(x, lo, hi):  # FFT band-pass, no scipy needed
        X = np.fft.rfft(x); f = np.fft.rfftfreq(len(x), 1 / SR)
        X *= 1 / (1 + (lo / np.maximum(f, 1)) ** 4) / (1 + (f / hi) ** 4)
        return np.fft.irfft(X, len(x))
    for tm in times:
        var = 0.85 + 0.3 * rng.random(); n = int(0.045 * SR); t = np.arange(n) / SR
        body = bandpass(rng.normal(0, 1, n), 1800 * var, 7500) * np.exp(-t * 260) * 2.2
        cl = (body * 0.6 + np.sin(2 * np.pi * (180 * var + 40) * t) * np.exp(-t * 120) * 0.35
              + np.sin(2 * np.pi * 3200 * var * t) * np.exp(-t * 900) * 0.15) * (0.75 + 0.25 * rng.random())
        pan = rng.uniform(-0.2, 0.2); s = int(tm * SR); e = min(len(buf), s + n)
        buf[s:e, 0] += cl[:e - s] * (1 - pan); buf[s:e, 1] += cl[:e - s] * (1 + pan)
    if np.abs(buf).max() > 0: buf = buf / np.abs(buf).max() * 10 ** (-3 / 20)
    w = wave.open(path, 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((buf * 32767).astype(np.int16).tobytes()); w.close()


def render_chunk(cfg_path, a, b, out, crf):
    cfg = json.load(open(cfg_path)); reel = Reel(cfg, os.path.dirname(os.path.abspath(cfg_path)))
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                          '-c:v', 'libx264', '-crf', str(crf), '-preset', 'slow', '-tune', 'film', '-profile:v', 'high', '-pix_fmt', 'yuv420p', out],
                         stdin=subprocess.PIPE)
    for i in range(a, b): p.stdin.write(reel.frame(i / FPS).tobytes())
    p.stdin.close(); return p.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('config'); ap.add_argument('--test', nargs='*', type=float); ap.add_argument('--info', action='store_true')
    ap.add_argument('--jobs', type=int, default=max(1, min(4, (os.cpu_count() or 2)))); ap.add_argument('--crf', type=int, default=8)
    ap.add_argument('--chunk', nargs=3)  # internal: a b out
    a = ap.parse_args()
    if a.chunk: sys.exit(render_chunk(a.config, int(a.chunk[0]), int(a.chunk[1]), a.chunk[2], a.crf))
    base = os.path.dirname(os.path.abspath(a.config)); cfg = json.load(open(a.config)); reel = Reel(cfg, base)
    n = int(round(reel.dur * FPS))
    if a.info: print(f'duration {reel.dur:.2f}s, {n} frames, {len(reel.sfx_times())} keypresses'); return
    if a.test is not None:
        for t in a.test:
            p = os.path.join(base, f'check_{t:05.2f}.jpg'); Image.fromarray(reel.frame(t)).save(p, quality=90); print(p)
        return
    out = os.path.join(base, cfg.get('output', 'reel.mp4'))
    tmp = tempfile.mkdtemp(prefix='reel_')
    try:
        bounds = [int(n * i / a.jobs) for i in range(a.jobs + 1)]
        env = dict(os.environ, OMP_NUM_THREADS='1')
        procs = [subprocess.Popen([sys.executable, __file__, a.config, '--crf', str(a.crf), '--chunk', str(bounds[i]), str(bounds[i + 1]),
                                   os.path.join(tmp, f'c{i}.mp4')], env=env) for i in range(a.jobs)]
        if any(p.wait() for p in procs): raise SystemExit('A render chunk failed.')
        with open(os.path.join(tmp, 'list.txt'), 'w') as f:
            for i in range(a.jobs): f.write(f"file '{os.path.join(tmp, f'c{i}.mp4')}'\n")
        silent = out.replace('.mp4', '_silent.mp4'); wav = out.replace('.mp4', '_typing.wav')
        subprocess.check_call(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', os.path.join(tmp, 'list.txt'),
                               '-c', 'copy', '-movflags', '+faststart', silent])
        typing_wav(reel.sfx_times(), reel.dur, wav)
        subprocess.check_call(['ffmpeg', '-y', '-loglevel', 'error', '-i', silent, '-i', wav, '-map', '0:v', '-map', '1:a', '-c:v', 'copy',
                               '-af', 'volume=-3dB', '-ar', '48000', '-c:a', 'aac', '-b:a', '320k', '-shortest', '-movflags', '+faststart', out])
        print(f'Done: {out}\n      {silent}\n      {wav}')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
