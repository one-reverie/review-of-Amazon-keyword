from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "packaging" / "TokenAnalyzer.ico"


def create_icon(output_path: Path) -> None:
    size = 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle((8, 8, 248, 248), radius=50, fill="#F4511E")
    draw.ellipse((54, 48, 154, 148), outline="white", width=18)
    draw.line((137, 133, 184, 180), fill="white", width=20)

    bar_color = "#138A62"
    draw.rounded_rectangle((48, 184, 88, 208), radius=8, fill=bar_color)
    draw.rounded_rectangle((100, 166, 140, 208), radius=8, fill=bar_color)
    draw.rounded_rectangle((152, 142, 192, 208), radius=8, fill=bar_color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(
        output_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="生成词元分析器Windows图标")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    create_icon(args.output.resolve())
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
