#!/usr/bin/env python3
"""Generate a simulated terminal demo GIF showing Phantom Agent in action."""

from PIL import Image, ImageDraw, ImageFont

# --- Configuration ---
WIDTH, HEIGHT = 800, 500
BG_COLOR = (40, 42, 54)        # #282a36
TITLE_BAR_COLOR = (50, 52, 66)
TITLE_BAR_HEIGHT = 32
GREEN = (80, 250, 123)
WHITE = (248, 248, 242)
LIGHT_GRAY = (189, 189, 189)
DOT_RED = (255, 85, 85)
DOT_YELLOW = (241, 250, 140)
DOT_GREEN = (80, 250, 123)

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FONT_SIZE = 14
LINE_HEIGHT = 20
LEFT_MARGIN = 16
TOP_MARGIN = TITLE_BAR_HEIGHT + 12

TYPING_MS = 50
PAUSE_MS = 1500
OUTPUT_MS = 800


def load_font():
    return ImageFont.truetype(FONT_PATH, FONT_SIZE)


def draw_title_bar(draw: ImageDraw.ImageDraw):
    """Draw macOS-style title bar with colored dots."""
    draw.rectangle([(0, 0), (WIDTH, TITLE_BAR_HEIGHT)], fill=TITLE_BAR_COLOR)
    cx, cy, r = 20, TITLE_BAR_HEIGHT // 2, 6
    for i, color in enumerate([DOT_RED, DOT_YELLOW, DOT_GREEN]):
        draw.ellipse(
            [(cx + i * 22 - r, cy - r), (cx + i * 22 + r, cy + r)], fill=color
        )
    font = load_font()
    draw.text(
        (WIDTH // 2, TITLE_BAR_HEIGHT // 2),
        "phantom-agent -- bash",
        fill=LIGHT_GRAY,
        font=font,
        anchor="mm",
    )


def make_frame(lines):
    """Create a single frame image from a list of (text, color) line entries."""
    img = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)
    draw_title_bar(draw)
    font = load_font()
    y = TOP_MARGIN
    for segments in lines:
        x = LEFT_MARGIN
        for text, color in segments:
            draw.text((x, y), text, fill=color, font=font)
            bbox = font.getbbox(text)
            x += bbox[2] - bbox[0]
        y += LINE_HEIGHT
    return img


# --- Define the terminal script ---
script = [
    ("cmd", "python -m phantom install --global"),
    (
        "out",
        [
            "Installing Phantom Agent hooks GLOBALLY (all projects)...",
            "",
            "  Created ~/.phantom",
            "  Updated ~/.claude/settings.json (global, all projects)",
            "",
            "Phantom Agent is now active.",
        ],
    ),
    ("pause",),
    ("cmd", "python -m phantom status"),
    (
        "out",
        [
            "Phantom Agent Status",
            "========================================",
            "  Installed:     Yes",
            "  Sessions:      7",
            "  Total actions: 156",
            "  Patterns:      3",
        ],
    ),
    ("pause",),
    ("cmd", "python -m phantom patterns"),
    (
        "out",
        [
            "Discovered 3 workflow pattern(s):",
            "",
            "  Pattern 1: Grep > Read > Edit > Bash",
            "    Seen in:  4 sessions",
            "",
            "  Pattern 2: Read > Edit > Bash > Bash",
            "    Seen in:  3 sessions",
            "",
            "  Pattern 3: Glob > Read > Edit",
            "    Seen in:  2 sessions",
        ],
    ),
    ("pause",),
]


def build_frames():
    """Walk through the script and yield (PIL.Image, duration_ms) tuples."""
    screen_lines = []

    for entry in script:
        kind = entry[0]

        if kind == "cmd":
            command = entry[1]
            # Type the command character by character
            for i in range(1, len(command) + 1):
                typed = command[:i]
                current = list(screen_lines)
                current.append([("$ ", GREEN), (typed, WHITE)])
                yield make_frame(current), TYPING_MS
            # Finalize the prompt line on screen
            screen_lines.append([("$ ", GREEN), (command, WHITE)])

        elif kind == "out":
            output_lines = entry[1]
            for line in output_lines:
                screen_lines.append([(line, LIGHT_GRAY)])
            yield make_frame(screen_lines), OUTPUT_MS

        elif kind == "pause":
            yield make_frame(screen_lines), PAUSE_MS

    # Final pause before loop restarts
    yield make_frame(screen_lines), 3000


def main():
    frames_and_durations = list(build_frames())
    frames = [f for f, _ in frames_and_durations]
    durations = [d for _, d in frames_and_durations]

    out_path = "/home/user/claw-code/assets/demo.gif"
    frames[0].save(
        out_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
    )
    print(f"Saved {len(frames)} frames to {out_path}")


if __name__ == "__main__":
    main()
