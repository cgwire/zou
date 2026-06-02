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

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont

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

    for obj in objects:
        _draw_object(overlay, obj, ss_size)

    if SUPERSAMPLE != 1:
        overlay = overlay.resize(image.size, Image.LANCZOS)
    composite = Image.alpha_composite(image, overlay).convert("RGB")
    composite.save(image_path, "PNG")
    return image_path


def _draw_object(overlay, obj, image_size):
    if not isinstance(obj, dict):
        return
    if isinstance(obj.get("eraser"), dict):
        # The eraser punches holes via destination-out compositing, which
        # Pillow primitives can't do in-place. Render the shape onto its
        # own transparent layer, subtract the eraser mask from that layer's
        # alpha channel, then composite the result back onto the overlay.
        layer = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
        _dispatch_shape(layer, obj, image_size)
        _apply_eraser(layer, obj, image_size)
        overlay.alpha_composite(layer)
    else:
        _dispatch_shape(overlay, obj, image_size)


def _dispatch_shape(target, obj, image_size):
    obj_type = (obj.get("type") or "").lower()
    scale_x, scale_y = _get_scales(obj, image_size)
    draw = ImageDraw.Draw(target)
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
            _draw_text(target, obj, scale_x, scale_y)
        elif obj_type == "arrow":
            _draw_arrow(draw, obj, scale_x, scale_y)
        elif obj_type == "group":
            for child in obj.get("objects", []) or []:
                _draw_object(target, child, image_size)
        else:
            logger.debug("Unsupported annotation type: %s", obj_type)
    except Exception:
        logger.exception(
            "Failed to render annotation object of type %s", obj_type
        )


def _apply_eraser(layer, parent_obj, image_size):
    """
    Subtract the eraser mask from `layer`'s alpha channel.

    The eraser is a fabric Group of paths in the PARENT's local centered
    coordinate frame (eraser group sits at origin (0, 0) with the parent's
    untransformed dimensions, with default `originX/Y='center'`). Each
    child path is positioned within that frame via its own
    `left/top/scaleX/scaleY/angle`. Path commands run from the path-local
    frame → parent-centered frame → canvas frame → image frame.

    Pillow has no destination-out compositing, so we stamp the eraser
    paths onto an L-mode mask (255 = erased) and subtract that mask from
    the layer's alpha. Anti-aliasing comes from the renderer's overall
    supersample + LANCZOS downsample.
    """
    eraser = parent_obj.get("eraser")
    if not isinstance(eraser, dict):
        return
    children = eraser.get("objects") or []
    if not children:
        return

    scale_x, scale_y = _get_scales(parent_obj, image_size)
    parent_centered = _make_object_transform(parent_obj, 0, 0)
    parent_scale_x = parent_obj.get("scaleX", 1) or 1

    mask = Image.new("L", layer.size, 0)
    mask_draw = ImageDraw.Draw(mask)

    for child in children:
        if not isinstance(child, dict):
            continue
        if (child.get("type") or "").lower() != "path":
            continue
        _draw_eraser_path_on_mask(
            mask_draw,
            child,
            parent_centered,
            parent_scale_x,
            scale_x,
            scale_y,
        )

    if mask.getbbox() is None:
        return

    _, _, _, alpha = layer.split()
    layer.putalpha(ImageChops.subtract(alpha, mask))


def _draw_eraser_path_on_mask(
    mask_draw, child, parent_centered, parent_scale_x, scale_x, scale_y
):
    raw = child.get("path")
    if not raw:
        return
    commands = _parse_path_commands(raw)
    if not commands:
        return
    anchors = _extract_path_anchor_points(commands)
    # Child path local → eraser-centered (= parent-centered) coords.
    child_transform = _centered_transform(
        _with_default_bbox(child, anchors),
        fallback_pivot=_bbox_centre(anchors),
    )

    def to_image(px, py):
        ex, ey = child_transform(px, py)
        cx_out, cy_out = parent_centered(ex, ey)
        return cx_out * scale_x, cy_out * scale_y

    # Eraser stroke width sits in the parent's local frame: it scales
    # with the parent's transform (scaleX) before reaching canvas, then
    # again with the canvas → image factor.
    raw_width = child.get("strokeWidth", 1) or 1
    pillow_width = max(1, int(round(raw_width * parent_scale_x * scale_x)))

    segments = _path_to_segments(commands, to_image)
    for points in segments:
        if len(points) >= 2:
            mask_draw.line(points, fill=255, width=pillow_width, joint="curve")


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
    """
    Return the stroke colour or None when no stroke was set. Shapes
    that always need a visible line (path, line, arrow…) layer their own
    fallback on top.
    """
    return _parse_color(obj.get("stroke"), default=None)


def _line_color(obj):
    """
    Stroke with a black default — for shapes whose body IS the stroke
    (line, arrow, path, psstroke, polyline). If the JSON has no stroke
    but a fill, use the fill; else default to opaque black.
    """
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


def _make_object_transform(obj, pivot_x, pivot_y):
    """
    Build the affine transform fabric applies to a shape's local
    coords:  T(center) ∘ R(angle) ∘ S(scaleX, scaleY) ∘ T(-pivot).

    Returns a function (px, py) → (wx, wy) in CANVAS coordinates.

    The translate target matches fabric's `getRelativeCenterPoint()`:
    the un-rotated bbox centre `(left + w/2 · scaleX, top + h/2 · scaleY)`
    is itself rotated around `(left, top)` by `angle`. When a fabric UI
    rotation happens, fabric updates `left`/`top` so the bbox centre
    stays put visually — which means at render time, the rendering
    centre is no longer `left + w/2` for rotated shapes. Without this
    extra rotation the rendered position is off by an amount that
    looks like the shape's own translation, which is why side-by-side
    annotations appeared to inherit each other's drag.

    """
    angle_rad = math.radians(obj.get("angle", 0) or 0)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    scale_x = obj.get("scaleX", 1) or 1
    scale_y = obj.get("scaleY", 1) or 1
    left = obj.get("left", 0) or 0
    top = obj.get("top", 0) or 0
    width = obj.get("width", 0) or 0
    height = obj.get("height", 0) or 0
    naive_cx = left + width / 2 * scale_x
    naive_cy = top + height / 2 * scale_y
    cx = left + (naive_cx - left) * cos_a - (naive_cy - top) * sin_a
    cy = top + (naive_cx - left) * sin_a + (naive_cy - top) * cos_a

    def transform(px, py):
        dx = px - pivot_x
        dy = py - pivot_y
        sx = dx * scale_x
        sy = dy * scale_y
        return (
            sx * cos_a - sy * sin_a + cx,
            sx * sin_a + sy * cos_a + cy,
        )

    return transform


def _bbox_transform(obj):
    """
    Transform for shapes whose local coords are in the (0,0)–(w,h)
    bbox: rect, ellipse, text.
    """
    width = obj.get("width", 0) or 0
    height = obj.get("height", 0) or 0
    return _make_object_transform(obj, width / 2, height / 2)


def _centered_transform(obj, fallback_pivot=None):
    """
    Transform for shapes whose local coords are in fabric's centered
    system (path commands, polyline points, line endpoints, PSBrush
    strokePoints).

    Pivot resolution:
    1. `pathOffset` from the JSON if present (Path serialises it).
    2. `fallback_pivot` if the caller provides one — typically the
    bbox centre of the shape's own anchor points, which is what
    fabric would recompute on deserialisation as `calcDim.left +
    w/2, calcDim.top + h/2`.
    3. Otherwise `(left + w/2, top + h/2)`. That assumes the shape
    was never translated — fine for rect-like data without a
    pathOffset, broken for moved path/psstroke without an explicit
    offset (use option 2 there).

    """
    path_offset = obj.get("pathOffset")
    if path_offset:
        pivot_x = path_offset.get("x", 0) or 0
        pivot_y = path_offset.get("y", 0) or 0
    elif fallback_pivot is not None:
        pivot_x, pivot_y = fallback_pivot
    else:
        width = obj.get("width", 0) or 0
        height = obj.get("height", 0) or 0
        left = obj.get("left", 0) or 0
        top = obj.get("top", 0) or 0
        pivot_x = left + width / 2
        pivot_y = top + height / 2
    return _make_object_transform(obj, pivot_x, pivot_y)


def _bbox_centre(points):
    """
    Mid-point of the bbox of a list of (x, y) tuples.
    """
    if not points:
        return 0, 0
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _with_default_bbox(obj, anchor_points):
    """
    Return a copy of `obj` with `left`/`top`/`width`/`height` filled
    in from the anchor points' bbox when missing — fabric would compute
    those from `calcDim` on deserialisation. Required so that the
    transform's centre and pivot align when the JSON only stores the
    shape's own points (typical of test data and some external
    integrations).
    """
    if not anchor_points:
        return obj
    if (
        obj.get("width") is not None
        and obj.get("height") is not None
        and obj.get("left") is not None
        and obj.get("top") is not None
    ):
        return obj
    xs = [p[0] for p in anchor_points]
    ys = [p[1] for p in anchor_points]
    bbox_left = min(xs)
    bbox_top = min(ys)
    out = dict(obj)
    out.setdefault("left", bbox_left)
    out.setdefault("top", bbox_top)
    out.setdefault("width", max(xs) - bbox_left)
    out.setdefault("height", max(ys) - bbox_top)
    return out


def _to_image(point, scale_x, scale_y):
    return point[0] * scale_x, point[1] * scale_y


def _stroke_outline_width(obj, scale_x):
    """
    Outline width to pass to Pillow's `width` kwarg. Returns 0 (no
    outline) when the shape has no stroke — this is what makes the
    whiteboard sticker (a fill-only fabric.Rect) render correctly.
    """
    if _stroke_color(obj) is None:
        return 0
    return _stroke_width(obj, scale_x)


def _stroke_polygon(draw, points, color, width):
    """
    Pillow's draw.polygon doesn't accept an outline-width kwarg, so
    we draw each edge as a thick line. This is also what lets rotated
    rects and ellipses keep their outline intact under transforms.
    """
    if color is None or width <= 0 or len(points) < 2:
        return
    for i in range(len(points)):
        draw.line(
            [points[i], points[(i + 1) % len(points)]],
            fill=color,
            width=width,
        )


def _draw_rect(draw, obj, scale_x, scale_y):
    width = obj.get("width", 0) or 0
    height = obj.get("height", 0) or 0
    if width <= 0 or height <= 0:
        return
    transform = _bbox_transform(obj)
    corners = [(0, 0), (width, 0), (width, height), (0, height)]
    image_corners = [
        _to_image(transform(*c), scale_x, scale_y) for c in corners
    ]
    fill = _fill_color(obj)
    if fill is not None:
        draw.polygon(image_corners, fill=fill)
    _stroke_polygon(
        draw,
        image_corners,
        _stroke_color(obj),
        _stroke_outline_width(obj, scale_x),
    )


_ELLIPSE_SAMPLES = 64


def _draw_ellipse(draw, obj, scale_x, scale_y):
    if obj.get("rx") is not None or obj.get("ry") is not None:
        width = (obj.get("rx", 0) or 0) * 2
        height = (obj.get("ry", 0) or 0) * 2
    elif obj.get("radius") is not None:
        width = height = (obj.get("radius", 0) or 0) * 2
    else:
        width = obj.get("width", 0) or 0
        height = obj.get("height", 0) or 0
    if width <= 0 or height <= 0:
        return
    # Build the transform with the resolved width/height so the pivot
    # and centre line up for rx/ry-style ellipses too.
    sized = dict(obj)
    sized["width"] = width
    sized["height"] = height
    transform = _bbox_transform(sized)
    local = [
        (
            width / 2
            + width / 2 * math.cos(2 * math.pi * i / _ELLIPSE_SAMPLES),
            height / 2
            + height / 2 * math.sin(2 * math.pi * i / _ELLIPSE_SAMPLES),
        )
        for i in range(_ELLIPSE_SAMPLES)
    ]
    image_points = [_to_image(transform(*p), scale_x, scale_y) for p in local]
    fill = _fill_color(obj)
    if fill is not None:
        draw.polygon(image_points, fill=fill)
    _stroke_polygon(
        draw,
        image_points,
        _stroke_color(obj),
        _stroke_outline_width(obj, scale_x),
    )


def _draw_line(draw, obj, scale_x, scale_y):
    x1 = obj.get("x1", 0) or 0
    y1 = obj.get("y1", 0) or 0
    x2 = obj.get("x2", 0) or 0
    y2 = obj.get("y2", 0) or 0
    anchors = [(x1, y1), (x2, y2)]
    transform = _centered_transform(
        _with_default_bbox(obj, anchors),
        fallback_pivot=_bbox_centre(anchors),
    )
    draw.line(
        [
            _to_image(transform(x1, y1), scale_x, scale_y),
            _to_image(transform(x2, y2), scale_x, scale_y),
        ],
        fill=_line_color(obj),
        width=_stroke_width(obj, scale_x),
    )


def _flatten_points(points, transform, scale_x, scale_y):
    return [
        _to_image(
            transform(p.get("x", 0) or 0, p.get("y", 0) or 0),
            scale_x,
            scale_y,
        )
        for p in points or []
    ]


def _polyline_anchors(obj):
    raw = obj.get("points") or []
    return [(p.get("x", 0) or 0, p.get("y", 0) or 0) for p in raw]


def _draw_polyline(draw, obj, scale_x, scale_y):
    anchors = _polyline_anchors(obj)
    transform = _centered_transform(
        _with_default_bbox(obj, anchors),
        fallback_pivot=_bbox_centre(anchors),
    )
    points = _flatten_points(obj.get("points"), transform, scale_x, scale_y)
    if len(points) < 2:
        return
    draw.line(points, fill=_line_color(obj), width=_stroke_width(obj, scale_x))


def _draw_polygon(draw, obj, scale_x, scale_y):
    anchors = _polyline_anchors(obj)
    transform = _centered_transform(
        _with_default_bbox(obj, anchors),
        fallback_pivot=_bbox_centre(anchors),
    )
    points = _flatten_points(obj.get("points"), transform, scale_x, scale_y)
    if len(points) < 3:
        return
    fill = _fill_color(obj)
    if fill is not None:
        draw.polygon(points, fill=fill)
    _stroke_polygon(
        draw,
        points,
        _stroke_color(obj),
        _stroke_outline_width(obj, scale_x),
    )


def _draw_arrow(draw, obj, scale_x, scale_y):
    raw_x1 = obj.get("x1", 0) or 0
    raw_y1 = obj.get("y1", 0) or 0
    raw_x2 = obj.get("x2", 0) or 0
    raw_y2 = obj.get("y2", 0) or 0
    anchors = [(raw_x1, raw_y1), (raw_x2, raw_y2)]
    transform = _centered_transform(
        _with_default_bbox(obj, anchors),
        fallback_pivot=_bbox_centre(anchors),
    )
    x1_c, y1_c = transform(raw_x1, raw_y1)
    x2_c, y2_c = transform(raw_x2, raw_y2)
    x1, y1 = _to_image((x1_c, y1_c), scale_x, scale_y)
    x2, y2 = _to_image((x2_c, y2_c), scale_x, scale_y)
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


def _draw_text(overlay, obj, scale_x, scale_y):
    text = obj.get("text") or ""
    if not text:
        return
    font_size = int(
        round(
            (obj.get("fontSize", 16) or 16)
            * (obj.get("scaleY", 1) or 1)
            * scale_y
        )
    )
    font = _load_font(max(1, font_size))
    color = _fill_color(obj) or _stroke_color(obj) or (0, 0, 0, 255)
    background = _parse_color(obj.get("backgroundColor"), default=None)

    # Render the text + optional background onto a transparent
    # sub-image sized to the glyph bbox, then rotate/paste onto the
    # overlay. Going through a sub-image is the only way Pillow can
    # rotate text — `ImageDraw.text` has no rotation kwarg.
    measure_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    try:
        bbox = measure_draw.textbbox((0, 0), text, font=font)
    except AttributeError:
        # Pillow < 9.2 — getsize fallback (length-only).
        w, h = measure_draw.textsize(text, font=font)
        bbox = (0, 0, w, h)
    text_w = max(1, bbox[2] - bbox[0])
    text_h = max(1, bbox[3] - bbox[1])
    text_img = Image.new("RGBA", (text_w, text_h), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_img)
    if background is not None:
        text_draw.rectangle([0, 0, text_w, text_h], fill=background)
    # textbbox can return a non-zero top — shift the draw origin so the
    # glyph sits flush against the sub-image's top-left.
    text_draw.text((-bbox[0], -bbox[1]), text, fill=color, font=font)

    angle = obj.get("angle", 0) or 0
    if angle:
        text_img = text_img.rotate(-angle, expand=True, resample=Image.BICUBIC)

    # Position: fabric anchors the text at (left, top) and rotates
    # around the bbox centre. Compute that centre in image coords and
    # paste so the rotated sub-image is centred on it.
    obj_w = obj.get("width", 0) or text_w / scale_x
    obj_h = obj.get("height", 0) or text_h / scale_y
    obj_scale_x = obj.get("scaleX", 1) or 1
    obj_scale_y = obj.get("scaleY", 1) or 1
    left = obj.get("left", 0) or 0
    top = obj.get("top", 0) or 0
    centre_x = (left + obj_w / 2 * obj_scale_x) * scale_x
    centre_y = (top + obj_h / 2 * obj_scale_y) * scale_y
    paste_x = int(round(centre_x - text_img.size[0] / 2))
    paste_y = int(round(centre_y - text_img.size[1] / 2))
    overlay.alpha_composite(text_img, (paste_x, paste_y))


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
    # PSBrush stores its own strokeOffset (analogous to pathOffset) but
    # it's not always serialised. Both the pivot and the bbox metadata
    # fall back to what we can derive from strokePoints — fabric does
    # the same in `_setPositionDimensions` on deserialisation, and that
    # keeps the pivot fixed when the user drags the stroke so
    # translations actually move the rendering.
    anchors = [(p.get("x", 0) or 0, p.get("y", 0) or 0) for p in points]
    normalised = _with_default_bbox(obj, anchors)
    stroke_offset = obj.get("strokeOffset")
    if stroke_offset:
        normalised = dict(normalised)
        normalised["pathOffset"] = {
            "x": stroke_offset.get("x", 0) or 0,
            "y": stroke_offset.get("y", 0) or 0,
        }
        transform = _centered_transform(normalised)
    else:
        transform = _centered_transform(
            normalised, fallback_pivot=_bbox_centre(anchors)
        )
    base_width = (obj.get("strokeWidth", 1) or 1) * scale_x

    def to_screen(p):
        return _to_image(
            transform(p.get("x", 0) or 0, p.get("y", 0) or 0),
            scale_x,
            scale_y,
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
    # Apply fabric's full affine transform (T·R·S·T(-pathOffset)) so the
    # path is positioned/scaled/rotated correctly even when the user
    # transformed it. When pathOffset is absent from the JSON, fall
    # back to the bbox centre of the path commands themselves — that's
    # what fabric computes from `calcDim` and what makes translation
    # `left` actually move the rendering.
    color = _line_color(obj)
    width = _stroke_width(obj, scale_x)
    anchors = _extract_path_anchor_points(commands)
    transform = _centered_transform(
        _with_default_bbox(obj, anchors),
        fallback_pivot=_bbox_centre(anchors),
    )

    def to_screen(px, py):
        return _to_image(transform(px, py), scale_x, scale_y)

    segments = _path_to_segments(commands, to_screen)
    for points in segments:
        if len(points) >= 2:
            draw.line(points, fill=color, width=width, joint="curve")


def _path_to_segments(commands, to_point):
    """
    Flatten an SVG-like command list (M/L/Q/C/Z) into polyline
    segments expressed via `to_point(px, py)` for every anchor and
    sampled curve point. Shared by the path renderer and the eraser
    mask renderer.
    """
    segments = []
    current = None
    start = None
    for cmd in commands:
        op = cmd[0].upper()
        params = cmd[1:]
        if op == "M" and len(params) >= 2:
            if segments and len(segments[-1]) < 2:
                segments.pop()
            current = to_point(params[0], params[1])
            start = current
            segments.append([current])
        elif op == "L" and len(params) >= 2:
            current = to_point(params[0], params[1])
            if not segments:
                segments.append([])
            segments[-1].append(current)
        elif op == "Q" and len(params) >= 4:
            cx, cy = params[0], params[1]
            ex, ey = params[2], params[3]
            if not segments:
                segments.append([])
            if current is None:
                current = to_point(cx, cy)
                segments[-1].append(current)
            segments[-1].extend(
                _quad_points(current, to_point(cx, cy), to_point(ex, ey))
            )
            current = to_point(ex, ey)
        elif op == "C" and len(params) >= 6:
            c1 = to_point(params[0], params[1])
            c2 = to_point(params[2], params[3])
            ep = to_point(params[4], params[5])
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
    return segments


def _parse_path_commands(raw):
    if isinstance(raw, str):
        return _parse_path_string(raw)
    if isinstance(raw, list):
        return [list(cmd) for cmd in raw if cmd]
    return []


def _extract_path_anchor_points(commands):
    """
    Pick the destination point of each M/L/Q/C command — enough to
    bracket the path's bbox without flattening every Bezier.
    """
    points = []
    for cmd in commands:
        op = cmd[0].upper()
        params = cmd[1:]
        if op in ("M", "L") and len(params) >= 2:
            points.append((params[0], params[1]))
        elif op == "Q" and len(params) >= 4:
            points.append((params[2], params[3]))
        elif op == "C" and len(params) >= 6:
            points.append((params[4], params[5]))
    return points


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
