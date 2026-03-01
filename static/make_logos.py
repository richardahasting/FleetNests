#!/usr/bin/env python3
"""
FleetNests logo generator using pycairo.
Produces:
  fleetnests-icon.png  — 100x100 square icon
  fleetnests-logo.png  — 400x100 horizontal navbar logo
"""

import math
import cairo

# ── Colours (0-1 float) ────────────────────────────────────────────────────
NAVY  = (10/255,  35/255,  66/255)   # #0A2342
GOLD  = (201/255, 168/255, 76/255)   # #C9A84C
WHITE = (1.0, 1.0, 1.0)

FONT_SERIF     = "/usr/share/fonts/truetype/noto/NotoSerif-Bold.ttf"
FONT_SANS      = "/usr/share/fonts/truetype/lato/Lato-Bold.ttf"

# ── Helpers ───────────────────────────────────────────────────────────────
def set_colour(ctx, rgb, alpha=1.0):
    ctx.set_source_rgba(rgb[0], rgb[1], rgb[2], alpha)


def rounded_rect(ctx, x, y, w, h, r):
    """Draw a rounded rectangle path."""
    ctx.new_sub_path()
    ctx.arc(x + r,     y + r,     r, math.pi,       3*math.pi/2)
    ctx.arc(x + w - r, y + r,     r, 3*math.pi/2,   0)
    ctx.arc(x + w - r, y + h - r, r, 0,              math.pi/2)
    ctx.arc(x + r,     y + h - r, r, math.pi/2,      math.pi)
    ctx.close_path()


# ── Anchor icon ───────────────────────────────────────────────────────────
def draw_anchor(ctx, cx, cy, size, colour):
    """
    Draw a stylised anchor centred at (cx, cy) scaled by `size`.
    size ≈ half-height of the finished icon in px.
    """
    lw  = size * 0.07          # line width
    ctx.set_line_width(lw)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    ctx.set_line_join(cairo.LINE_JOIN_ROUND)
    set_colour(ctx, colour)

    # ── ring at top (toroidal loop) ───────────────────────────────────────
    ring_r = size * 0.13
    ring_y = cy - size * 0.72
    ctx.new_path()
    ctx.arc(cx, ring_y, ring_r, 0, 2*math.pi)
    ctx.stroke()

    # ── vertical shaft ────────────────────────────────────────────────────
    shaft_top    = ring_y + ring_r          # just below ring
    shaft_bottom = cy + size * 0.45
    ctx.move_to(cx, shaft_top)
    ctx.line_to(cx, shaft_bottom)
    ctx.stroke()

    # ── crossbar ──────────────────────────────────────────────────────────
    bar_y   = cy - size * 0.38
    bar_half = size * 0.42
    ctx.move_to(cx - bar_half, bar_y)
    ctx.line_to(cx + bar_half, bar_y)
    ctx.stroke()

    # small balls at crossbar ends
    ball_r = lw * 1.1
    set_colour(ctx, colour)
    for bx in (cx - bar_half, cx + bar_half):
        ctx.new_path()
        ctx.arc(bx, bar_y, ball_r, 0, 2*math.pi)
        ctx.fill()

    # ── curved bottom U-shape ────────────────────────────────────────────
    arm_spread = size * 0.38
    arm_y_top  = cy + size * 0.10
    fluke_y    = cy + size * 0.55

    ctx.new_path()
    ctx.move_to(cx - arm_spread, arm_y_top)
    ctx.curve_to(
        cx - arm_spread, fluke_y,   # control 1
        cx,              fluke_y,   # control 2
        cx,              fluke_y,   # end
    )
    ctx.move_to(cx, fluke_y)
    ctx.curve_to(
        cx,              fluke_y,
        cx + arm_spread, fluke_y,
        cx + arm_spread, arm_y_top,
    )
    ctx.stroke()

    # small balls at fluke ends
    for bx in (cx - arm_spread, cx + arm_spread):
        ctx.new_path()
        ctx.arc(bx, arm_y_top, ball_r, 0, 2*math.pi)
        ctx.fill()


def draw_wing_arc(ctx, cx, cy, size, colour):
    """
    Draw a graceful arc / nest-curve above the anchor ring,
    suggesting wings or a bird's nest.
    """
    set_colour(ctx, colour)
    ctx.set_line_width(size * 0.07)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)

    ring_y   = cy - size * 0.72
    arc_y    = ring_y - size * 0.08   # sits just above the ring
    spread   = size * 0.42
    lift     = size * 0.32            # how high the arc rises

    # Left wing
    ctx.new_path()
    ctx.move_to(cx - size * 0.08, arc_y)
    ctx.curve_to(
        cx - spread * 0.55, arc_y - lift * 0.6,
        cx - spread,        arc_y - lift * 0.2,
        cx - spread,        arc_y + size * 0.08,
    )
    ctx.stroke()

    # Right wing (mirror)
    ctx.new_path()
    ctx.move_to(cx + size * 0.08, arc_y)
    ctx.curve_to(
        cx + spread * 0.55, arc_y - lift * 0.6,
        cx + spread,        arc_y - lift * 0.2,
        cx + spread,        arc_y + size * 0.08,
    )
    ctx.stroke()


# ── Icon (100×100) ────────────────────────────────────────────────────────
def make_icon(path, size=100):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, size, size)
    ctx     = cairo.Context(surface)

    # Navy circle background
    pad = size * 0.04
    ctx.arc(size/2, size/2, size/2 - pad, 0, 2*math.pi)
    set_colour(ctx, NAVY)
    ctx.fill()

    # Thin gold border ring
    ctx.arc(size/2, size/2, size/2 - pad, 0, 2*math.pi)
    set_colour(ctx, GOLD)
    ctx.set_line_width(size * 0.025)
    ctx.stroke()

    anchor_size = size * 0.38
    cx = size / 2
    cy = size / 2 + size * 0.04   # nudge anchor down a touch so wings fit

    draw_wing_arc(ctx, cx, cy, anchor_size, GOLD)
    draw_anchor(ctx,   cx, cy, anchor_size, GOLD)

    surface.write_to_png(path)
    print(f"  Wrote {path}")


# ── Wordmark helper ───────────────────────────────────────────────────────
def draw_wordmark(ctx, x, y, height):
    """
    Draw 'FleetNests' wordmark starting at (x, y-baseline).
    Returns the total width consumed.
    """
    fleet_size = height * 0.52
    nests_size = height * 0.48

    # ── "Fleet" in NotoSerif-Bold (elegant serif) ─────────────────────────
    ctx.new_path()
    set_colour(ctx, WHITE)
    ctx.set_font_size(fleet_size)

    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_BEST)
    fo.set_hint_style(cairo.HINT_STYLE_NONE)
    fo.set_hint_metrics(cairo.HINT_METRICS_OFF)
    ctx.set_font_options(fo)

    serif_face = cairo.ToyFontFace("serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
    ctx.set_font_face(serif_face)
    ctx.set_font_size(fleet_size)

    fleet_ext  = ctx.text_extents("Fleet")
    ctx.move_to(x, y)
    ctx.show_text("Fleet")

    # ── "Nests" in Lato-Bold (clean sans) — gold ─────────────────────────
    sans_face = cairo.ToyFontFace("sans-serif", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_face(sans_face)
    ctx.set_font_size(nests_size)
    set_colour(ctx, GOLD)

    nests_ext = ctx.text_extents("Nests")

    # Align baselines: nudge "Nests" so cap-heights visually match
    nests_x = x + fleet_ext.x_advance + height * 0.015
    nests_y = y + (fleet_size - nests_size) * 0.05   # very slight lift
    ctx.move_to(nests_x, nests_y)
    ctx.show_text("Nests")

    total_w = (nests_x - x) + nests_ext.x_advance
    return total_w


# ── Horizontal logo (400×100) ─────────────────────────────────────────────
def make_logo(path, icon_path, w=400, h=100):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx     = cairo.Context(surface)

    # Transparent background — nothing to paint

    # ── Icon tile ─────────────────────────────────────────────────────────
    icon_px   = 80          # icon drawn square inside the strip
    icon_pad  = (h - icon_px) / 2
    icon_cx   = icon_pad + icon_px / 2
    icon_cy   = h / 2

    # Navy circle
    ctx.arc(icon_cx, icon_cy, icon_px/2, 0, 2*math.pi)
    set_colour(ctx, NAVY)
    ctx.fill()

    # Gold border
    ctx.arc(icon_cx, icon_cy, icon_px/2, 0, 2*math.pi)
    set_colour(ctx, GOLD)
    ctx.set_line_width(icon_px * 0.025)
    ctx.stroke()

    # Anchor + wings inside the tile
    anchor_size = icon_px * 0.38
    draw_wing_arc(ctx, icon_cx, icon_cy + icon_px*0.04, anchor_size, GOLD)
    draw_anchor(  ctx, icon_cx, icon_cy + icon_px*0.04, anchor_size, GOLD)

    # ── Wordmark ──────────────────────────────────────────────────────────
    text_x    = icon_pad + icon_px + h * 0.08
    baseline  = h * 0.67
    draw_wordmark(ctx, text_x, baseline, h)

    surface.write_to_png(path)
    print(f"  Wrote {path}")


# ── Main ──────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    base = "/home/richard/projects/fleetnests/static"

    icon_path = f"{base}/fleetnests-icon.png"
    logo_path = f"{base}/fleetnests-logo.png"

    print("Generating FleetNests logos …")
    make_icon(icon_path)
    make_logo(logo_path, icon_path)
    print("Done.")
