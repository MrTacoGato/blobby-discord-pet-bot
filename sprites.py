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


if __name__ == "__main__":
    n = build_all()
    print(f"rendered {n} sprites into {SPRITE_DIR}")
