"""Make a square icon source from the clinic logo (step 10.4).

    python packaging/make_icon.py
    cargo tauri icon icon-src.png --output desktop/src-tauri/icons

`cargo tauri icon` requires a SQUARE source, and the clinic logo is wide. Rather
than distorting it (which would look wrong on the taskbar), this pads it onto a
transparent square canvas with a little margin, then scales to 1024x1024 — the
size Tauri wants so every derived icon, down to the 16px tray, stays sharp.

Output is gitignored: it is generated from a committed source image, so there is
no reason to store both.
"""

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "frontend" / "public" / "clinic-logo.png"
OUT = ROOT / "icon-src.png"
MARGIN = 0.10  # breathing room so the mark is not flush to the icon edge


def main() -> int:
    src = Image.open(SOURCE).convert("RGBA")
    w, h = src.size
    side = max(w, h)
    pad = int(side * MARGIN)
    size = side + pad * 2

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.paste(src, ((size - w) // 2, (size - h) // 2), src)
    canvas.resize((1024, 1024), Image.LANCZOS).save(OUT)

    print(f"source {w}x{h} -> {OUT.name} 1024x1024 (square, transparent padding)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
