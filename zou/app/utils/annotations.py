"""
Render Fabric.js annotation objects on top of a still image with Pillow.

This is a server-side approximation of the canvas-based renderer used in
Kitsu's player. Shape rotation, shadows and gradients are not reproduced;
everything else (including PSBrush pressure-varying stroke width) maps to
ImageDraw primitives.
"""

import logging
import math
import os
import re

from PIL import Image, ImageColor, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


DEFAULT_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial.ttf",
]

# Render the overlay at this multiple of the target size, then LANCZOS
# down to get cheap anti-aliasing. Pillow's ImageDraw primitives don't
# AA on their own.
SUPERSAMPLE = 2


def render_annotation_on_image(image_path, annotation):
    """
    Open `image_path`, draw the Fabric.js objects from
    annotation["drawing"]["objects"] on top, then save the composite back
    to the same path. Returns image_path.
    """
    objects = (annotation or {}).get("drawing", {}).get("objects", []) or []
    if not objects:
        return image_path

    image = Image.open(image_path).convert("RGBA")
    ss_size = (image.size[0] * SUPERSAMPLE, image.size[1] * SUPERSAMPLE)
    overlay = Image.new("RGBA", ss_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for obj in objects:
        _draw_object(draw, obj, ss_size)

    if SUPERSAMPLE != 1:
        overlay = overlay.resize(image.size, Image.LANCZOS)
    composite = Image.alpha_composite(image, overlay).convert("RGB")
    composite.save(image_path, "PNG")
    return image_path


def _draw_object(draw, obj, image_size):
    if not isinstance(obj, dict):
        return
    obj_type = (obj.get("type") or "").lower()
    scale_x, scale_y = _get_scales(obj, image_size)
    try:
        if obj_type == "path":
            _draw_path(draw, obj, scale_x, scale_y)
        elif obj_type == "psstroke":
            _draw_psstroke(draw, obj, scale_x, scale_y)
        elif obj_type == "rect":
            _draw_rect(draw, obj, scale_x, scale_y)
        elif obj_type in ("circle", "ellipse"):
            _draw_ellipse(draw, obj, scale_x, scale_y)
        elif obj_type == "line":
            _draw_line(draw, obj, scale_x, scale_y)
        elif obj_type == "polyline":
            _draw_polyline(draw, obj, scale_x, scale_y)
        elif obj_type == "polygon":
            _draw_polygon(draw, obj, scale_x, scale_y)
        elif obj_type in ("i-text", "text", "textbox"):
            _draw_text(draw, obj, scale_x, scale_y)
        elif obj_type == "arrow":
            _draw_arrow(draw, obj, scale_x, scale_y)
        elif obj_type == "group":
            for child in obj.get("objects", []) or []:
                _draw_object(draw, child, image_size)
        else:
            logger.debug("Unsupported annotation type: %s", obj_type)
    except Exception:
        logger.exception(
            "Failed to render annotation object of type %s", obj_type
        )


def _get_scales(obj, image_size):
    image_width, image_height = image_size
    canvas_width = obj.get("canvasWidth") or image_width
    canvas_height = obj.get("canvasHeight") or image_height
    return image_width / canvas_width, image_height / canvas_height


def _stroke_width(obj, scale):
    raw = obj.get("strokeWidth", 1)
    if raw is None:
        raw = 1
    return max(1, int(round(raw * scale)))


# CSS rgba() with alpha as float 0..1, which PIL.ImageColor.getrgb refuses.
_CSS_RGBA_RE = re.compile(
    r"^\s*rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*"
    r"(?:,\s*(\d*\.?\d+)\s*)?\)\s*$",
    re.IGNORECASE,
)


def _parse_color(value, default=None):
    if value is None or value == "" or value == "transparent":
        return default
    if isinstance(value, str):
        match = _CSS_RGBA_RE.match(value)
        if match:
            r, g, b, a = match.groups()
            alpha = float(a) if a is not None else 1.0
            if 0 <= alpha <= 1:
                alpha_255 = round(alpha * 255)
            else:
                alpha_255 = max(0, min(255, round(alpha)))
            return (int(r), int(g), int(b), alpha_255)
    try:
        rgb = ImageColor.getrgb(value)
    except (ValueError, AttributeError):
        return default
    if len(rgb) == 3:
        return rgb + (255,)
    return rgb


def _stroke_color(obj):
    """Return the stroke colour or None when no stroke was set. Shapes
    that always need a visible line (path, line, arrow…) layer their own
    fallback on top."""
    return _parse_color(obj.get("stroke"), default=None)


def _line_color(obj):
    """Stroke with a black default — for shapes whose body IS the stroke
    (line, arrow, path, psstroke, polyline). If the JSON has no stroke
    but a fill, use the fill; else default to opaque black."""
    return _stroke_color(obj) or _fill_color(obj) or (0, 0, 0, 255)


def _fill_color(obj):
    return _parse_color(obj.get("fill"), default=None)


def _origin(obj, scale_x, scale_y):
    left = (obj.get("left", 0) or 0) * scale_x
    top = (obj.get("top", 0) or 0) * scale_y
    return left, top


def _size(obj, scale_x, scale_y):
    width = (obj.get("width", 0) or 0) * (obj.get("scaleX", 1) or 1) * scale_x
    height = (
        (obj.get("height", 0) or 0) * (obj.get("scaleY", 1) or 1) * scale_y
    )
    return width, height


def _outline_kwargs(obj, scale_x):
    """Common outline/width pair for fillable shapes (rect, ellipse,
    polygon). When `stroke` is absent we pass `outline=None, width=0` so
    Pillow draws no outline — that's the whiteboard sticker case (a
    fill-only fabric.Rect)."""
    stroke = _stroke_color(obj)
    if stroke is None:
        return {"outline": None, "width": 0}
    return {"outline": stroke, "width": _stroke_width(obj, scale_x)}


def _draw_rect(draw, obj, scale_x, scale_y):
    x, y = _origin(obj, scale_x, scale_y)
    w, h = _size(obj, scale_x, scale_y)
    if w <= 0 or h <= 0:
        return
    draw.rectangle(
        [x, y, x + w, y + h],
        fill=_fill_color(obj),
        **_outline_kwargs(obj, scale_x),
    )


def _draw_ellipse(draw, obj, scale_x, scale_y):
    x, y = _origin(obj, scale_x, scale_y)
    if obj.get("rx") is not None or obj.get("ry") is not None:
        rx = (obj.get("rx", 0) or 0) * (obj.get("scaleX", 1) or 1) * scale_x
        ry = (obj.get("ry", 0) or 0) * (obj.get("scaleY", 1) or 1) * scale_y
        w, h = rx * 2, ry * 2
    elif obj.get("radius") is not None:
        r = (obj.get("radius", 0) or 0) * scale_x
        w = h = r * 2
    else:
        w, h = _size(obj, scale_x, scale_y)
    if w <= 0 or h <= 0:
        return
    draw.ellipse(
        [x, y, x + w, y + h],
        fill=_fill_color(obj),
        **_outline_kwargs(obj, scale_x),
    )


def _draw_line(draw, obj, scale_x, scale_y):
    # x1, y1, x2, y2 are already in canvas-absolute coords. left/top are
    # bbox metadata fabric uses for selection — don't add them.
    x1 = (obj.get("x1", 0) or 0) * scale_x
    y1 = (obj.get("y1", 0) or 0) * scale_y
    x2 = (obj.get("x2", 0) or 0) * scale_x
    y2 = (obj.get("y2", 0) or 0) * scale_y
    draw.line(
        [(x1, y1), (x2, y2)],
        fill=_line_color(obj),
        width=_stroke_width(obj, scale_x),
    )


def _flatten_points(points, scale_x, scale_y):
    return [
        ((p.get("x", 0) or 0) * scale_x, (p.get("y", 0) or 0) * scale_y)
        for p in points or []
    ]


def _draw_polyline(draw, obj, scale_x, scale_y):
    points = _flatten_points(obj.get("points"), scale_x, scale_y)
    if len(points) < 2:
        return
    draw.line(points, fill=_line_color(obj), width=_stroke_width(obj, scale_x))


def _draw_polygon(draw, obj, scale_x, scale_y):
    points = _flatten_points(obj.get("points"), scale_x, scale_y)
    if len(points) < 3:
        return
    draw.polygon(
        points, fill=_fill_color(obj), **_outline_kwargs(obj, scale_x)
    )


def _draw_arrow(draw, obj, scale_x, scale_y):
    # Same convention as line: x1/y1/x2/y2 are canvas-absolute coords.
    x1 = (obj.get("x1", 0) or 0) * scale_x
    y1 = (obj.get("y1", 0) or 0) * scale_y
    x2 = (obj.get("x2", 0) or 0) * scale_x
    y2 = (obj.get("y2", 0) or 0) * scale_y
    color = _line_color(obj)
    width = _stroke_width(obj, scale_x)
    head_size = (obj.get("arrowHeadSize", 15) or 15) * scale_x
    angle = math.atan2((y2 - y1), (x2 - x1))

    # Shorten the body so it sits fully inside the head triangle —
    # otherwise Pillow's rounded end cap (radius = width/2) pokes past
    # the geometric tip. Matches Kitsu's Arrow._toSVG export.
    if head_size > 0:
        body_offset = head_size * 0.7
        body_end_x = x2 - body_offset * math.cos(angle)
        body_end_y = y2 - body_offset * math.sin(angle)
    else:
        body_end_x, body_end_y = x2, y2

    draw.line([(x1, y1), (body_end_x, body_end_y)], fill=color, width=width)

    if head_size <= 0:
        return
    left = (
        x2 - head_size * math.cos(angle - math.pi / 6),
        y2 - head_size * math.sin(angle - math.pi / 6),
    )
    right = (
        x2 - head_size * math.cos(angle + math.pi / 6),
        y2 - head_size * math.sin(angle + math.pi / 6),
    )
    draw.polygon([(x2, y2), left, right], fill=color, outline=color)


def _draw_text(draw, obj, scale_x, scale_y):
    text = obj.get("text") or ""
    if not text:
        return
    x, y = _origin(obj, scale_x, scale_y)
    font_size = int(
        round(
            (obj.get("fontSize", 16) or 16)
            * (obj.get("scaleY", 1) or 1)
            * scale_y
        )
    )
    font = _load_font(max(1, font_size))
    background = _parse_color(obj.get("backgroundColor"), default=None)
    if background is not None:
        try:
            bbox = draw.textbbox((x, y), text, font=font)
            draw.rectangle(bbox, fill=background)
        except AttributeError:
            pass
    # Fabric Text uses `fill` for the glyph colour; fall back to stroke
    # then to opaque black so text is never invisible.
    color = _fill_color(obj) or _stroke_color(obj) or (0, 0, 0, 255)
    draw.text((x, y), text, fill=color, font=font)


def _load_font(size):
    for candidate in DEFAULT_FONT_PATHS:
        if os.path.isfile(candidate):
            try:
                return ImageFont.truetype(candidate, size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _draw_psstroke(draw, obj, scale_x, scale_y):
    # PSBrush strokes (the freehand pen in Kitsu). Each segment uses
    # width = leading-point.pressure * strokeWidth (see
    # fabricjs-psbrush index.mjs:421). Pillow can't vary width within a
    # single line call, so we draw segment by segment and stamp a disk at
    # each junction to round the joins.
    points = obj.get("strokePoints") or []
    if len(points) < 2:
        return
    color = _line_color(obj)
    base_width = (obj.get("strokeWidth", 1) or 1) * scale_x

    def to_screen(p):
        return (
            (p.get("x", 0) or 0) * scale_x,
            (p.get("y", 0) or 0) * scale_y,
        )

    def segment_width(point):
        pressure = point.get("pressure")
        if pressure is None:
            pressure = 1
        return max(1, int(round(pressure * base_width)))

    def stamp_cap(pos, width):
        r = width / 2
        if r < 1:
            return
        draw.ellipse(
            [(pos[0] - r, pos[1] - r), (pos[0] + r, pos[1] + r)], fill=color
        )

    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        width = segment_width(p1)
        a, b = to_screen(p1), to_screen(p2)
        draw.line([a, b], fill=color, width=width)
        stamp_cap(a, width)

    # Cap the trailing point with the last segment's width.
    stamp_cap(to_screen(points[-1]), segment_width(points[-2]))


def _draw_path(draw, obj, scale_x, scale_y):
    raw = obj.get("path")
    if not raw:
        return
    commands = _parse_path_commands(raw)
    if not commands:
        return
    # Path commands are stored in canvas-absolute coords: fabric
    # normalises left=calcDim.left and pathOffset=(calcDim.left+w/2,
    # calcDim.top+h/2) on Path construction, so the two render-time
    # translations cancel out and world coord = path coord.
    color = _line_color(obj)
    width = _stroke_width(obj, scale_x)

    def to_screen(px, py):
        return (px * scale_x, py * scale_y)

    segments = []
    current = None
    start = None
    for cmd in commands:
        op = cmd[0].upper()
        params = cmd[1:]
        if op == "M" and len(params) >= 2:
            if segments and len(segments[-1]) < 2:
                segments.pop()
            current = to_screen(params[0], params[1])
            start = current
            segments.append([current])
        elif op == "L" and len(params) >= 2:
            current = to_screen(params[0], params[1])
            if not segments:
                segments.append([])
            segments[-1].append(current)
        elif op == "Q" and len(params) >= 4:
            cx, cy = params[0], params[1]
            ex, ey = params[2], params[3]
            if not segments:
                segments.append([])
            if current is None:
                current = to_screen(cx, cy)
                segments[-1].append(current)
            segments[-1].extend(
                _quad_points(current, to_screen(cx, cy), to_screen(ex, ey))
            )
            current = to_screen(ex, ey)
        elif op == "C" and len(params) >= 6:
            c1 = to_screen(params[0], params[1])
            c2 = to_screen(params[2], params[3])
            ep = to_screen(params[4], params[5])
            if not segments:
                segments.append([])
            if current is None:
                current = c1
                segments[-1].append(current)
            segments[-1].extend(_cubic_points(current, c1, c2, ep))
            current = ep
        elif op == "Z":
            if start is not None and segments and segments[-1]:
                segments[-1].append(start)
            current = start

    for points in segments:
        if len(points) >= 2:
            draw.line(points, fill=color, width=width, joint="curve")


def _parse_path_commands(raw):
    if isinstance(raw, str):
        return _parse_path_string(raw)
    if isinstance(raw, list):
        return [list(cmd) for cmd in raw if cmd]
    return []


def _parse_path_string(text):
    commands = []
    pattern = re.compile(r"([MLQCZmlqcz])\s*([^MLQCZmlqcz]*)")
    for match in pattern.finditer(text):
        op = match.group(1).upper()
        if op == "Z":
            commands.append([op])
            continue
        numbers = [
            float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", match.group(2))
        ]
        commands.append([op, *numbers])
    return commands


def _quad_points(p0, p1, p2, steps=8):
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1]
        points.append((x, y))
    return points


def _cubic_points(p0, p1, p2, p3, steps=12):
    points = []
    for i in range(1, steps + 1):
        t = i / steps
        x = (
            (1 - t) ** 3 * p0[0]
            + 3 * (1 - t) ** 2 * t * p1[0]
            + 3 * (1 - t) * t * t * p2[0]
            + t**3 * p3[0]
        )
        y = (
            (1 - t) ** 3 * p0[1]
            + 3 * (1 - t) ** 2 * t * p1[1]
            + 3 * (1 - t) * t * t * p2[1]
            + t**3 * p3[1]
        )
        points.append((x, y))
    return points
