"""
Pixel-art sprite renderer.

Renders each species x color combo to a transparent PNG using the same 16x16
pixel grids and Game Boy-style 4-shade ramps as blobby_sprites.html. The 30
images are pre-baked into the sprites/ folder; the bot just attaches the files
(so Pillow is only needed when (re)generating art, never at runtime).

Run it any time you change a shape or color:
    $ python sprites.py
"""

import colorsys
import os

import config

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


# --------------------------------------------------------------------------
# Shapes. Pixel codes: 0 empty, 1 body, 2 highlight, 3 shadow, 4 outline,
#                      5 eye-white, 6 pupil, 7 mouth.  (Mirrors the HTML.)
# --------------------------------------------------------------------------
GRIDS = {
    "blob": [
        "0000000000000000", "0000044444000000", "0000400000440000", "0004022211040000",
        "0040221111104000", "0040211111104000", "0402111111110400", "0402151151110400",
        "0402156156110400", "0402111111110400", "0402117777110400", "0040211111104000",
        "0040221111304000", "0004032223040000", "0000403333400000", "0000044444000000",
    ],
    "slime": [
        "0000000440000000", "0000004224000000", "0000042112400000", "0000421111240000",
        "0004211111124000", "0042111111112400", "0421111111111240", "0421151151112400",
        "0421156156111240", "0421111111111240", "0421117777111240", "0421111111111240",
        "0042111111112400", "0004211111124000", "0004222222224000", "0000444444440000",
    ],
    "ember": [
        "0000000440000000", "0000004224000000", "0000042112400000", "0000421221240000",
        "0004212112124000", "0042121111212400", "0421211111121240", "4212111111111214",
        "4121511511111124", "4211561561111124", "0421111111111240", "0042111111112400",
        "0004211111124000", "0000421111240000", "0000042112400000", "0000000440000000",
    ],
    "spark": [
        "0000040000400000", "0000040000400000", "0000044004400000", "0000004224000000",
        "0000042112400000", "0004211111124000", "0042111111112400", "0421111111111240",
        "0421151151112400", "0421156156111240", "0421111111111240", "0421117777111240",
        "0042111111112400", "0004211111124000", "0004222222224000", "0000444444440000",
    ],
    "wisp": [
        "0000044444000000", "0000422222400000", "0004221112240000", "0042211111224000",
        "0421111111112400", "0421511511112400", "0421561561112400", "0421111111112400",
        "0421117711112400", "0421111111112400", "0421111111112400", "0421111111112400",
        "0421111111112400", "0421111111112400", "0420420420420400", "0040040040040000",
    ],
    "frost": [
        "0000000000000000", "0000044000044000", "0000422004422400", "0004221442211400",
        "0042211111111240", "0421111111111124", "0421151111511124", "4211161111611124",
        "4211111111111124", "4211117777111124", "4211111111111124", "0421111111111240",
        "0042111111112400", "0004222222224000", "0000444444440000", "0000000000000000",
    ],
}

SPRITE_DIR = os.path.join(os.path.dirname(__file__), "sprites")

# --------------------------------------------------------------------------
# Authored art (the final art-bot pixel set). When the art bot exports frames
# into sprites/art/, the loader prefers them over the procedural glow renders;
# anything missing silently stays procedural, so species can be swapped one at
# a time with no data migration. See plans/ASSET_PIPELINE.md.
#
#   sprites/art/<species>_<colorname>.gif   idle, e.g. blob_lime.gif
#   sprites/art/bg/<species>.gif            background (1:1 per species)
#   sprites/art/items/<item_id>.png         cosmetic overlay (transparent)
#   sprites/art/rarity/<rarity>.png         rarity badge (transparent)
#
# Filenames use INTERNAL keys (blob/slime/... , lime/azure/...); the cute
# display names live only in config.species_name(). Bump BLOBBY_ART_VERSION to
# bust the composited sprites/dressed/ cache after re-exporting art.
# --------------------------------------------------------------------------
ART_DIR = os.path.join(SPRITE_DIR, "art")
ART_VERSION = os.environ.get("BLOBBY_ART_VERSION", "v1")
# Optional per-species nudge for the cosmetic anchor, in canvas px. The art bot
# fills this in only if one shared anchor doesn't sit right on every silhouette.
ITEM_ANCHOR = {}


def _authored_idle(species, color_index):
    """Path to an authored idle for this combo, or None if not exported. Accepts
    an animated GIF or a single transparent PNG still (Leonardo.ai exports PNGs);
    a still is brought to life with a code-driven bob at composite time."""
    name, _ = config.color_for(species, color_index)
    for ext in ("gif", "png"):
        p = os.path.join(ART_DIR, f"{species}_{name}.{ext}")
        if os.path.exists(p):
            return p
    return None


def _authored_bg(species):
    """Path to an authored background GIF/PNG for this species, or None."""
    for ext in ("gif", "png"):
        p = os.path.join(ART_DIR, "bg", f"{species}.{ext}")
        if os.path.exists(p):
            return p
    return None


def _authored_item(item_id):
    """Path to an authored cosmetic overlay PNG, or None."""
    if not item_id:
        return None
    p = os.path.join(ART_DIR, "items", f"{item_id}.png")
    return p if os.path.exists(p) else None


def rarity_icon_path(rarity):
    """Path to an authored rarity badge PNG, or None (callers fall back to emoji)."""
    p = os.path.join(ART_DIR, "rarity", f"{rarity}.png")
    return p if os.path.exists(p) else None


# --------------------------------------------------------------------------
# Color ramp: rebuild the 4 body shades + eyes/mouth from a species' embed hex.
# --------------------------------------------------------------------------
def _hsl(hexint):
    r = ((hexint >> 16) & 0xFF) / 255.0
    g = ((hexint >> 8) & 0xFF) / 255.0
    b = (hexint & 0xFF) / 255.0
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s


def _rgba(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h, l, s)
    return (round(r * 255), round(g * 255), round(b * 255), 255)


def ramp(hexint):
    h, s = _hsl(hexint)
    return {
        "1": _rgba(h, s, 0.55),                  # body
        "2": _rgba(h, min(s + 0.10, 0.90), 0.72),  # highlight
        "3": _rgba(h, s, 0.38),                  # shadow
        "4": _rgba(h, s, 0.22),                  # outline
        "5": (232, 240, 200, 255),               # eye white
        "6": (15, 56, 15, 255),                  # pupil (GB ink)
        "7": _rgba(h, s, 0.28),                  # mouth
    }


def render(species, color_index, scale=12):
    """Return a transparent PIL.Image for one species x color combo."""
    if Image is None:
        raise RuntimeError("Pillow is required to render sprites: pip install Pillow")
    grid = GRIDS[species]
    hexint = config.SPECIES[species]["colors"][color_index][1]
    pal = ramp(hexint)
    size = 16 * scale
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    px = img.load()
    for y in range(16):
        for x in range(16):
            k = grid[y][x]
            if k == "0":
                continue
            col = pal.get(k, pal["1"])
            for dy in range(scale):
                for dx in range(scale):
                    px[x * scale + dx, y * scale + dy] = col
    return img


def sprite_path(species, color_index):
    """Stable on-disk path for a combo, e.g. sprites/blob_0_lime.png."""
    name, _ = config.color_for(species, color_index)
    return os.path.join(SPRITE_DIR, f"{species}_{color_index}_{name}.png")


def build_all(scale=12):
    """(Re)generate every species x color PNG into sprites/."""
    os.makedirs(SPRITE_DIR, exist_ok=True)
    count = 0
    for species, spec in config.SPECIES.items():
        for ci in range(len(spec["colors"])):
            render(species, ci, scale).save(sprite_path(species, ci))
            count += 1
    return count


# --------------------------------------------------------------------------
# Animated "glow" rendering — the Celeste x Silksong direction.
#
# Each combo is pre-baked into sprites/<species>_<ci>_<name>.gif: a glowing
# creature (inner light core + soft bloom) on a dark vignette, with a gentle
# idle bob, a glow pulse, drifting light motes, and a blink. The bot just
# attaches the finished GIFs, so Pillow + numpy stay DEV-only (needed to
# (re)generate art, never at runtime). Build with:  python sprites.py
# --------------------------------------------------------------------------
import math
import random

try:
    from PIL import ImageDraw, ImageFilter
    import numpy as _np
except ImportError:  # pragma: no cover
    ImageDraw = ImageFilter = _np = None

ANIM_SCALE = 9       # px per cell -> 144px sprite
ANIM_FRAMES = 20
ANIM_CANVAS = 176    # extra top headroom so hats/crowns don't clip


def _sprite_offset(size, sn):
    """Center horizontally; bias the pet downward to leave headroom above
    (so hats, crowns, and halos have room to sit)."""
    return (size - sn) // 2, size - sn - 8


def anim_path(species, color_index):
    """Best idle GIF for a combo: authored art if exported, else the procedural
    glow render (sprites/blob_0_lime.gif). Authored idles win automatically."""
    authored = _authored_idle(species, color_index)
    if authored:
        return authored
    name, _ = config.color_for(species, color_index)
    return os.path.join(SPRITE_DIR, f"{species}_{color_index}_{name}.gif")


def _glow_rgb(hexint):
    """A bright glow color (r, g, b) derived from a species' embed hex."""
    h, s = _hsl(hexint)
    r, g, b, _ = _rgba(h, min(s + 0.15, 0.95), 0.66)
    return (r, g, b)


def _body_and_mask(species, color_index, scale):
    pal = ramp(config.SPECIES[species]["colors"][color_index][1])
    n = 16 * scale
    body = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    mask = Image.new("L", (n, n), 0)
    pb, pm = body.load(), mask.load()
    grid, eyes = GRIDS[species], []
    for y in range(16):
        for x in range(16):
            k = grid[y][x]
            if k == "0":
                continue
            col = pal.get(k, pal["1"])
            for dy in range(scale):
                for dx in range(scale):
                    pb[x * scale + dx, y * scale + dy] = col
                    pm[x * scale + dx, y * scale + dy] = 255
            if k in ("5", "6"):
                eyes.append((x, y))
    return body, mask, eyes


def _glow_layer(mask, color, blur):
    g = Image.composite(Image.new("RGBA", mask.size, color + (255,)),
                        Image.new("RGBA", mask.size, (0, 0, 0, 0)), mask)
    return g.filter(ImageFilter.GaussianBlur(blur))


def _core_layer(mask, scale):
    n = mask.size[0]
    core = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(core)
    cx, cy, r = n * 0.46, n * 0.40, n * 0.32
    for i in range(int(r), 0, -1):
        d.ellipse([cx - i, cy - i, cx + i, cy + i], fill=int(150 * (1 - i / r)))
    core = Image.composite(core.filter(ImageFilter.GaussianBlur(scale * 0.8)),
                           Image.new("L", (n, n), 0), mask)
    light = Image.new("RGBA", (n, n), (255, 255, 255, 0))
    light.putalpha(core)
    return light


def _vignette(size, base=(11, 16, 34), edge=(5, 7, 16)):
    yy, xx = _np.mgrid[0:size, 0:size]
    cx = cy = size / 2.0
    dist = _np.clip(_np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (size * 0.72), 0, 1)
    arr = _np.stack([base[i] * (1 - dist) + edge[i] * dist for i in range(3)], axis=-1)
    return Image.fromarray(arr.astype("uint8"), "RGB").convert("RGBA")


def _motes(count, w, color, seed):
    rng = random.Random(seed)
    return [dict(x=rng.uniform(0.10, 0.90) * w, base=rng.uniform(0, 1),
                 spd=rng.uniform(0.5, 1.0), rad=rng.choice([2, 2, 3]))
            for _ in range(count)]


def _draw_motes(img, motes, t, h, color):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for m in motes:
        prog = (m["base"] - t * m["spd"]) % 1.0
        y = h * (0.96 - 0.85 * prog)
        a = max(0, int(170 * math.sin(prog * math.pi)))
        r = m["rad"]
        d.ellipse([m["x"] - r, y - r, m["x"] + r, y + r], fill=color + (a,))
    return Image.alpha_composite(img, layer.filter(ImageFilter.GaussianBlur(1.1)))


def render_anim(species, color_index, scale=ANIM_SCALE, frames=ANIM_FRAMES, size=ANIM_CANVAS):
    """Return a list of RGB frames for one combo's idle animation."""
    if Image is None or _np is None:
        raise RuntimeError("Pillow + numpy are required to render sprites: "
                           "pip install -r requirements-dev.txt")
    glow = _glow_rgb(config.SPECIES[species]["colors"][color_index][1])
    body, mask, eyes = _body_and_mask(species, color_index, scale)
    sn = body.size[0]
    glow_img = _glow_layer(mask, glow, blur=scale * 1.7)
    core_img = _core_layer(mask, scale)
    ox, oy = _sprite_offset(size, sn)
    seed = color_index * 7 + list(config.SPECIES).index(species) * 101
    motes = _motes(6, size, glow, seed)
    out = []
    for f in range(frames):
        t = f / frames
        bob = round(math.sin(2 * math.pi * t) * 6)
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(2 * math.pi * t))
        frame = _vignette(size)
        g = glow_img.copy()
        g.putalpha(g.split()[3].point(lambda a: int(a * pulse)))
        frame.alpha_composite(g, (ox, oy + bob))
        frame.alpha_composite(body, (ox, oy + bob))
        frame.alpha_composite(core_img, (ox, oy + bob))
        frame = _draw_motes(frame, motes, t, size, glow)
        if f in (frames // 2, frames // 2 + 1) and eyes:
            d = ImageDraw.Draw(frame)
            xs = [ox + x * scale for x, _ in eyes]
            ys = [oy + bob + y * scale for _, y in eyes]
            d.line([min(xs), min(ys) + scale // 2, max(xs) + scale, min(ys) + scale // 2],
                   fill=(10, 18, 26, 255), width=max(2, scale // 3))
        out.append(frame.convert("RGB"))
    return out


def _save_gif(frames, path, duration=80):
    pal = frames[0].convert("P", palette=Image.ADAPTIVE, colors=128)
    conv = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
    conv[0].save(path, save_all=True, append_images=conv[1:], duration=duration,
                 loop=0, optimize=True, disposal=2)


def build_anim_all():
    """(Re)generate every species x color animated GIF into sprites/."""
    os.makedirs(SPRITE_DIR, exist_ok=True)
    count = 0
    for species, spec in config.SPECIES.items():
        for ci in range(len(spec["colors"])):
            _save_gif(render_anim(species, ci), anim_path(species, ci))
            count += 1
    return count


# --------------------------------------------------------------------------
# Cosmetics (Phase 2) -- composite an equipped item onto the glowing pet.
# Dressed GIFs are generated on demand and cached in sprites/dressed/ (which is
# git-ignored). Overlays are positioned from the species' own pixel grid, so a
# hat sits right on every shape without a hand-tuned table per species.
# --------------------------------------------------------------------------
DRESSED_DIR = os.path.join(SPRITE_DIR, "dressed")


def dressed_path(species, color_index, item_id):
    """Cache path for a composited look. The ART_VERSION suffix busts the cache
    when authored art is re-exported (bump BLOBBY_ART_VERSION). item_id may be a
    real cosmetic id or the sentinel '_look' for a bare background composite."""
    name, _ = config.color_for(species, color_index)
    return os.path.join(
        DRESSED_DIR, f"{species}_{color_index}_{name}__{item_id}__{ART_VERSION}.gif")


def _body_bounds(species):
    """(min_x, max_x, min_y, max_y, eye_cells) in 16x16 grid space."""
    grid = GRIDS[species]
    xs, ys, eyes = [], [], []
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch != "0":
                xs.append(x); ys.append(y)
            if ch in ("5", "6"):
                eyes.append((x, y))
    return min(xs), max(xs), min(ys), max(ys), eyes


def _cosmetic_cells(item_id, species):
    """[(cell_x, cell_y, (r,g,b)), ...] for a cosmetic, in grid space.
    Everything stays within ~2 cells above the body and not below it, so it
    never clips the canvas."""
    minx, maxx, miny, maxy, eyes = _body_bounds(species)
    cx = (minx + maxx) / 2.0
    if eyes:
        exs, eys = [e[0] for e in eyes], [e[1] for e in eyes]
        eye_l, eye_r, eye_y = min(exs), max(exs), min(eys)
    else:
        eye_l, eye_r, eye_y = int(cx) - 2, int(cx) + 2, int((miny + maxy) / 2)
    c = []
    if item_id == "party_hat":
        red, pom = (224, 72, 72), (246, 222, 96)
        c += [(cx - 1, miny, red), (cx, miny, red), (cx + 1, miny, red),
              (cx, miny - 1, pom)]
    elif item_id == "shades":
        dark, glint = (22, 26, 32), (130, 232, 244)
        for x in range(eye_l - 1, eye_r + 2):
            c.append((x, eye_y, dark))
        c.append((eye_l - 1, eye_y, glint))
    elif item_id == "crown":
        gold, tip = (236, 196, 72), (255, 242, 168)
        c += [(cx - 2, miny, gold), (cx - 1, miny, gold), (cx, miny, gold),
              (cx + 1, miny, gold), (cx + 2, miny, gold),
              (cx - 2, miny - 1, tip), (cx, miny - 1, tip), (cx + 2, miny - 1, tip)]
    elif item_id == "halo":
        pale = (250, 236, 150)
        c += [(cx - 2, miny - 2, pale), (cx - 1, miny - 2, pale), (cx, miny - 2, pale),
              (cx + 1, miny - 2, pale), (cx + 2, miny - 2, pale)]
    elif item_id == "headphones":
        band, cup = (62, 66, 78), (150, 160, 180)
        c += [(cx - 1, miny, band), (cx, miny, band), (cx + 1, miny, band),
              (minx - 1, eye_y, cup), (minx - 1, eye_y + 1, cup),
              (maxx + 1, eye_y, cup), (maxx + 1, eye_y + 1, cup)]
    elif item_id == "scarf":
        c1, c2 = (206, 72, 92), (242, 132, 152)
        row = maxy - 2
        for i, x in enumerate(range(minx, maxx + 1)):
            c.append((x, row, c1 if i % 2 == 0 else c2))
    elif item_id == "star_aura":
        spark = (255, 246, 184)
        c += [(minx - 1, miny + 1, spark), (maxx + 1, miny, spark),
              (maxx + 1, maxy - 1, spark), (minx - 1, maxy - 2, spark),
              (cx, miny - 2, spark)]
    return c


def _draw_cosmetic(frame, cells, scale, ox, oy):
    d = ImageDraw.Draw(frame)
    for cxf, cyf, col in cells:
        x0 = ox + int(round(cxf * scale))
        y0 = oy + int(round(cyf * scale))
        d.rectangle([x0, y0, x0 + scale - 1, y0 + scale - 1], fill=col + (255,))


def render_dressed(species, color_index, item_id, scale=ANIM_SCALE,
                   frames=ANIM_FRAMES, size=ANIM_CANVAS):
    """Frames of the pet wearing one cosmetic, composited over the glow render."""
    if Image is None or _np is None:
        raise RuntimeError("Pillow + numpy required: pip install -r requirements-dev.txt")
    glow = _glow_rgb(config.SPECIES[species]["colors"][color_index][1])
    body, mask, eyes = _body_and_mask(species, color_index, scale)
    sn = body.size[0]
    glow_img = _glow_layer(mask, glow, blur=scale * 1.7)
    core_img = _core_layer(mask, scale)
    ox, oy = _sprite_offset(size, sn)
    seed = color_index * 7 + list(config.SPECIES).index(species) * 101
    motes = _motes(6, size, glow, seed)
    cells = _cosmetic_cells(item_id, species)
    out = []
    for f in range(frames):
        t = f / frames
        bob = round(math.sin(2 * math.pi * t) * 6)
        pulse = 0.55 + 0.45 * (0.5 + 0.5 * math.sin(2 * math.pi * t))
        frame = _vignette(size)
        g = glow_img.copy()
        g.putalpha(g.split()[3].point(lambda a: int(a * pulse)))
        frame.alpha_composite(g, (ox, oy + bob))
        frame.alpha_composite(body, (ox, oy + bob))
        frame.alpha_composite(core_img, (ox, oy + bob))
        _draw_cosmetic(frame, cells, scale, ox, oy + bob)  # rides the bob
        frame = _draw_motes(frame, motes, t, size, glow)
        out.append(frame.convert("RGB"))
    return out


def _open_frames(path, size):
    """Load every frame of an authored GIF/PNG as RGBA, normalized to `size`."""
    im = Image.open(path)
    frames = []
    try:
        while True:
            f = im.convert("RGBA")
            if f.size != (size, size):
                f = f.resize((size, size))
            frames.append(f)
            im.seek(im.tell() + 1)
    except EOFError:
        pass
    return frames or [Image.new("RGBA", (size, size), (0, 0, 0, 0))]


def render_authored(species, color_index, item_id=None, size=ANIM_CANVAS,
                    frames=ANIM_FRAMES):
    """Composite authored frames: background -> authored idle -> cosmetic overlay.
    Requires an authored idle to exist. A multi-frame idle keeps its own motion;
    a single still gets a gentle code-driven bob so it still feels alive. Missing
    background/overlay are skipped (transparent idle lands on a dark backdrop)."""
    if Image is None:
        raise RuntimeError("Pillow required: pip install -r requirements-dev.txt")
    idle = _open_frames(_authored_idle(species, color_index), size)
    bg_path = _authored_bg(species)
    bg = _open_frames(bg_path, size) if bg_path else None
    item_path = _authored_item(item_id)
    item = _open_frames(item_path, size)[0] if item_path else None
    dx, dy = ITEM_ANCHOR.get(species, (0, 0))
    animated = len(idle) > 1
    n = len(idle) if animated else frames
    out = []
    for i in range(n):
        t = i / n
        bob = 0 if animated else round(math.sin(2 * math.pi * t) * 6)
        base = Image.new("RGBA", (size, size), (10, 14, 26, 255))  # dark fallback
        if bg:
            base.alpha_composite(bg[i % len(bg)])
        base.alpha_composite(idle[i if animated else 0], (0, bob))
        if item is not None:
            base.alpha_composite(item, (dx, dy + bob))  # cosmetic rides the bob
        out.append(base.convert("RGB"))
    return out


def ensure_dressed(species, color_index, item_id=None):
    """Return the path the bot should attach, compositing + caching once if needed.

    Authored art wins: if an authored idle exists and there's a background and/or
    cosmetic overlay to layer on, the composite is cached under sprites/dressed/.
    With nothing to composite, the raw authored idle (or procedural GIF) is used.
    Falls back to the original procedural cosmetic render when there's no
    authored idle. Never raises just because art is missing -- it degrades."""
    has_item = bool(item_id) and item_id in config.ITEMS

    # --- authored path -----------------------------------------------------
    if _authored_idle(species, color_index):
        overlay = _authored_item(item_id) if has_item else None
        os.makedirs(DRESSED_DIR, exist_ok=True)
        # Always composite authored art: it adds the idle bob, the background if
        # one exists, and the cosmetic if one exists -- and normalizes a PNG still
        # into a GIF the bot attaches uniformly. Cached, so Pillow runs once/look.
        key = item_id if overlay else "_look"
        path = dressed_path(species, color_index, key)
        if not os.path.exists(path):
            _save_gif(render_authored(species, color_index,
                                      item_id if overlay else None), path)
        return path

    # --- procedural path (unchanged behavior) ------------------------------
    if not has_item:
        return anim_path(species, color_index)
    os.makedirs(DRESSED_DIR, exist_ok=True)
    path = dressed_path(species, color_index, item_id)
    if not os.path.exists(path):
        _save_gif(render_dressed(species, color_index, item_id), path)
    return path


if __name__ == "__main__":
    n = build_all()
    print(f"rendered {n} static sprites into {SPRITE_DIR}")
    try:
        m = build_anim_all()
        print(f"rendered {m} animated glow GIFs into {SPRITE_DIR}")
    except RuntimeError as exc:
        print(exc)
