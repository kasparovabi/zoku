#!/usr/bin/env python3
"""Generate a professional GitHub social preview image (1280x640) for Phantom Agent."""

from PIL import Image, ImageDraw, ImageFont
import math

WIDTH, HEIGHT = 1280, 640
BG_COLOR = (13, 17, 23)  # #0d1117
OUTPUT_PATH = "assets/social-preview.png"

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def draw_decorations(draw: ImageDraw.ImageDraw, img: Image.Image):
    """Draw subtle geometric decorations on the background."""
    # Diagonal accent lines in the corners (muted blue-gray)
    line_color = (30, 40, 60, 120)

    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # Top-left corner lines
    for i in range(5):
        offset = i * 18
        odraw.line(
            [(0, 60 + offset), (60 + offset, 0)],
            fill=(48, 63, 95, 60 + i * 10),
            width=2,
        )

    # Bottom-right corner lines
    for i in range(5):
        offset = i * 18
        odraw.line(
            [(WIDTH, HEIGHT - 60 - offset), (WIDTH - 60 - offset, HEIGHT)],
            fill=(48, 63, 95, 60 + i * 10),
            width=2,
        )

    # Subtle horizontal rule above the bottom tagline
    odraw.line(
        [(WIDTH // 2 - 200, 530), (WIDTH // 2 + 200, 530)],
        fill=(88, 110, 150, 80),
        width=1,
    )

    # Small dots pattern along the top
    for i in range(0, WIDTH, 40):
        alpha = int(30 + 20 * math.sin(i * 0.05))
        odraw.ellipse(
            [(i - 1, 18), (i + 1, 20)],
            fill=(88, 110, 150, alpha),
        )

    # Small dots pattern along the bottom
    for i in range(0, WIDTH, 40):
        alpha = int(30 + 20 * math.sin(i * 0.05 + 1))
        odraw.ellipse(
            [(i - 1, HEIGHT - 20), (i + 1, HEIGHT - 18)],
            fill=(88, 110, 150, alpha),
        )

    # Subtle radial glow behind center (gives depth)
    for r in range(250, 0, -2):
        alpha = int(8 * (1 - r / 250))
        odraw.ellipse(
            [
                (WIDTH // 2 - r, HEIGHT // 2 - 60 - r),
                (WIDTH // 2 + r, HEIGHT // 2 - 60 + r),
            ],
            fill=(40, 70, 120, alpha),
        )

    # Composite overlay onto base
    base = img.convert("RGBA")
    base = Image.alpha_composite(base, overlay)
    return base


def main():
    img = Image.new("RGBA", (WIDTH, HEIGHT), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)

    # Apply decorations
    img = draw_decorations(draw, img)
    draw = ImageDraw.Draw(img)

    # Load fonts
    title_font = ImageFont.truetype(FONT_BOLD, 72)
    ghost_font = ImageFont.truetype(FONT_REGULAR, 80)
    tagline_font = ImageFont.truetype(FONT_REGULAR, 28)
    footer_font = ImageFont.truetype(FONT_REGULAR, 20)

    # -- Ghost emoji flanking the title --
    title_text = "Phantom Agent"
    ghost = "\U0001f441"  # eye emoji as fallback; we'll use text symbols
    # Since emoji rendering is unreliable in PIL, use a styled text approach
    # Draw the ghost characters using the magnifying glass idea as unicode
    ghost_char = "\u25C8"  # diamond shape as subtle flair

    # Main title
    title_y = 210
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    tw = bbox[2] - bbox[0]

    # Draw subtle title shadow
    draw.text(
        ((WIDTH - tw) // 2 + 2, title_y + 2),
        title_text,
        fill=(0, 0, 0, 180),
        font=title_font,
    )
    # Draw title
    draw.text(
        ((WIDTH - tw) // 2, title_y),
        title_text,
        fill=(240, 244, 248, 255),
        font=title_font,
    )

    # Diamond accents on either side of title
    accent_color = (100, 140, 200, 160)
    diamond_font = ImageFont.truetype(FONT_REGULAR, 36)
    dbbox = draw.textbbox((0, 0), ghost_char, font=diamond_font)
    dw = dbbox[2] - dbbox[0]

    title_left = (WIDTH - tw) // 2
    title_right = title_left + tw
    diamond_y = title_y + 22

    draw.text(
        (title_left - dw - 20, diamond_y),
        ghost_char,
        fill=accent_color,
        font=diamond_font,
    )
    draw.text(
        (title_right + 20, diamond_y),
        ghost_char,
        fill=accent_color,
        font=diamond_font,
    )

    # Tagline
    tagline = "Your invisible workflow detective for Claude Code"
    tagline_y = 310
    bbox = draw.textbbox((0, 0), tagline, font=tagline_font)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((WIDTH - tw) // 2, tagline_y),
        tagline,
        fill=(140, 150, 170, 255),
        font=tagline_font,
    )

    # Footer
    footer = "Zero config  \u00b7  Zero dependencies  \u00b7  Pure Python"
    footer_y = 555
    bbox = draw.textbbox((0, 0), footer, font=footer_font)
    tw = bbox[2] - bbox[0]
    draw.text(
        ((WIDTH - tw) // 2, footer_y),
        footer,
        fill=(100, 110, 130, 220),
        font=footer_font,
    )

    # Convert to RGB for PNG saving
    final = img.convert("RGB")
    final.save(OUTPUT_PATH, "PNG")
    print(f"Social preview saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
