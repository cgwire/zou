import os
import tempfile
import unittest
from unittest import mock

from PIL import Image, ImageChops, ImageFont

from zou.app.utils import annotations as annotations_renderer


def _new_white_image(size=(200, 200)):
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    Image.new("RGB", size, (255, 255, 255)).save(path, "PNG")
    return path


class AnnotationsRendererTestCase(unittest.TestCase):
    def tearDown(self):
        for path in getattr(self, "_paths", []):
            if os.path.exists(path):
                os.remove(path)

    def _temp_image(self, size=(200, 200)):
        path = _new_white_image(size)
        self._paths = getattr(self, "_paths", []) + [path]
        return path

    # Assertions are tolerant because the renderer supersamples and
    # LANCZOS-downsamples, so edge pixels are anti-aliased.
    def assertPixelClose(self, actual, expected, tolerance=40, msg=None):
        diffs = [abs(int(a) - int(e)) for a, e in zip(actual[:3], expected)]
        if max(diffs) > tolerance:
            self.fail(
                msg
                or f"pixel {actual[:3]} too far from expected {expected} "
                f"(per-channel diffs {diffs}, tolerance {tolerance})"
            )

    def assertPixelWhite(self, actual, tolerance=20, msg=None):
        if any(c < 255 - tolerance for c in actual[:3]):
            self.fail(msg or f"expected white pixel, got {actual[:3]}")

    def assertPixelColored(self, actual, msg=None):
        if all(c > 230 for c in actual[:3]):
            self.fail(msg or f"expected coloured pixel, got {actual[:3]}")

    def test_empty_annotation_leaves_image_untouched(self):
        path = self._temp_image()
        before = Image.open(path).getpixel((100, 100))
        annotations_renderer.render_annotation_on_image(path, None)
        annotations_renderer.render_annotation_on_image(
            path, {"drawing": {"objects": []}}
        )
        after = Image.open(path).getpixel((100, 100))
        self.assertEqual(before, after)

    def test_draws_red_rectangle(self):
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 50,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "stroke": "#ff0000",
                        "strokeWidth": 4,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # A pixel on the rectangle's outline should be red.
        self.assertPixelClose(image.getpixel((50, 100)), (255, 0, 0))
        # A pixel well inside the rectangle (no fill) stays white.
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_scales_to_image_size(self):
        path = self._temp_image(size=(400, 400))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 50,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "stroke": "#00ff00",
                        "strokeWidth": 4,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Scaled rectangle outline should hit (100, 200) on a 400x400 image.
        self.assertPixelClose(image.getpixel((100, 200)), (0, 255, 0))

    def test_draws_ellipse(self):
        path = self._temp_image()
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "ellipse",
                        "left": 50,
                        "top": 50,
                        "rx": 50,
                        "ry": 50,
                        "stroke": "#0000ff",
                        "strokeWidth": 4,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Top of the ellipse should be blue.
        self.assertPixelClose(image.getpixel((100, 50)), (0, 0, 255))

    def test_path_array_draws_line(self):
        path = self._temp_image()
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "path",
                        "stroke": "#ff00ff",
                        "strokeWidth": 4,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "path": [
                            ["M", 50, 100],
                            ["L", 150, 100],
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        self.assertPixelClose(image.getpixel((100, 100)), (255, 0, 255))

    def test_path_with_realistic_fabric_data(self):
        """
        Real fabric.js paths carry left/top/width/height/pathOffset.
        The path commands are in path-local coords; fabric positions the
        path so its bbox center sits at (left + width/2, top + height/2).

        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "path",
                        "left": 60,
                        "top": 100,
                        "width": 40,
                        "height": 0,
                        "scaleX": 1,
                        "scaleY": 1,
                        "stroke": "#00ff00",
                        "strokeWidth": 4,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "pathOffset": {"x": 80, "y": 100},
                        "path": [
                            ["M", 60, 100],
                            ["L", 100, 100],
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Horizontal stroke expected from world x=60 to world x=100 at y=100.
        # The right end (x=99) must be green.
        self.assertPixelClose(image.getpixel((99, 100)), (0, 255, 0))
        # The left end (x=61) must be green.
        self.assertPixelClose(image.getpixel((61, 100)), (0, 255, 0))
        # A pixel well left of x=60 (which would be hit by the buggy
        # off-by-width/2 version) stays white.
        self.assertPixelWhite(image.getpixel((45, 100)))

    def test_arrow_uses_absolute_canvas_coords(self):
        """
        Real fabric.js Line/Arrow store x1,y1,x2,y2 in canvas-absolute
        coords. left/top are bbox metadata and must NOT be added on top.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "arrow",
                        "x1": 60,
                        "y1": 100,
                        "x2": 140,
                        "y2": 100,
                        "left": 60,
                        "top": 98,
                        "width": 80,
                        "height": 4,
                        "stroke": "#ff8800",
                        "strokeWidth": 4,
                        "arrowHeadSize": 0,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Arrow segment from x=60 to x=140 at y=100. The endpoints must be
        # orange, and pixels well past x=140 (where the buggy version
        # would have shifted the line) must stay white.
        # Sample 2 px inside the segment to clear the rounded cap's AA.
        self.assertPixelClose(image.getpixel((62, 100)), (255, 136, 0))
        self.assertPixelClose(image.getpixel((138, 100)), (255, 136, 0))
        self.assertPixelWhite(image.getpixel((180, 100)))

    def test_psstroke_renders_polyline_through_strokepoints(self):
        """
        PSStroke (pressure brush, the freehand tool in Kitsu) stores
        points under `strokePoints`, not `path`. Each point has x/y/pressure
        in canvas-absolute coords.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "PSStroke",
                        "stroke": "#00aaff",
                        "strokeWidth": 4,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "left": 60,
                        "top": 99,
                        "width": 80,
                        "height": 2,
                        "strokePoints": [
                            {"x": 60, "y": 100, "pressure": 0.5},
                            {"x": 100, "y": 100, "pressure": 0.5},
                            {"x": 140, "y": 100, "pressure": 0.5},
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Pixels along the stroke should be blue-ish.
        self.assertPixelClose(image.getpixel((80, 100)), (0, 170, 255))
        self.assertPixelClose(image.getpixel((120, 100)), (0, 170, 255))
        # A pixel well off the stroke stays white.
        self.assertPixelWhite(image.getpixel((180, 50)))

    def test_psstroke_applies_pressure_to_width(self):
        """
        PSBrush uses lineWidth = pressure * strokeWidth per segment.
        Low pressure must produce a noticeably thinner line — a pixel a
        few rows above the centerline should stay white at low pressure
        but be coloured at high pressure.
        """
        # Low-pressure stroke (0.1): rendered width ~ 0.1 * 20 = 2 px
        path_low = self._temp_image(size=(200, 200))
        low_ann = {
            "drawing": {
                "objects": [
                    {
                        "type": "PSStroke",
                        "stroke": "#000000",
                        "strokeWidth": 20,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "strokePoints": [
                            {"x": 40, "y": 100, "pressure": 0.1},
                            {"x": 160, "y": 100, "pressure": 0.1},
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path_low, low_ann)
        low_img = Image.open(path_low)
        # 5 px off centerline must be white at low pressure.
        self.assertPixelWhite(low_img.getpixel((100, 105)))

        # High-pressure stroke (1.0): rendered width ~ 20 px → 5 px off
        # centerline must be black.
        path_high = self._temp_image(size=(200, 200))
        high_ann = {
            "drawing": {
                "objects": [
                    {
                        "type": "PSStroke",
                        "stroke": "#000000",
                        "strokeWidth": 20,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "strokePoints": [
                            {"x": 40, "y": 100, "pressure": 1.0},
                            {"x": 160, "y": 100, "pressure": 1.0},
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path_high, high_ann)
        high_img = Image.open(path_high)
        self.assertPixelClose(high_img.getpixel((100, 105)), (0, 0, 0))

    def test_arrow_body_does_not_poke_past_tip(self):
        """
        Pillow's draw.line rounds endpoints with a disk of radius
        width/2; without compensation the body sticks out past the
        triangular head. We shorten the body so the head fully covers
        the tip.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "arrow",
                        "x1": 40,
                        "y1": 100,
                        "x2": 100,
                        "y2": 100,
                        "stroke": "#000000",
                        "strokeWidth": 8,
                        "arrowHeadSize": 20,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # The geometric tip is at (100, 100). A pixel a couple px past
        # the tip in the line's direction must stay white — without the
        # fix, Pillow's rounded line cap (radius=4) would colour up to
        # x=104.
        self.assertPixelWhite(image.getpixel((103, 100)))
        # The tip itself stays coloured (head's apex). AA softens it.
        self.assertPixelColored(image.getpixel((100, 100)))

    def test_whiteboard_rect_renders_translucent_white_without_outline(
        self,
    ):
        """
        Kitsu's whiteboard sticker (annotation.js:212) is a fabric.Rect
        with `stroke: undefined`, `strokeWidth: 0`, fill=
        `rgba(255, 255, 255, 0.7)`. The renderer must:
        - not paint a red default outline,
        - parse the CSS-style rgba (alpha 0..1),
        - blend the translucent white so the underlying image still shows.

        """
        # Start from a black image so the white whiteboard is visible.
        path = self._temp_image()
        from PIL import Image as PILImage

        PILImage.new("RGB", (200, 200), (0, 0, 0)).save(path, "PNG")
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 50,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "strokeWidth": 0,
                        "fill": "rgba(255, 255, 255, 0.7)",
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # A pixel inside the whiteboard must NOT be black (the fill is
        # there) and must NOT be pure red (no default outline).
        inside = image.getpixel((100, 100))[:3]
        self.assertGreater(
            inside[0],
            100,
            f"interior should be lit by whiteboard, got {inside}",
        )
        # On a black base, 70% white blends to roughly (178, 178, 178).
        self.assertLess(abs(inside[0] - inside[1]), 30)
        # A pixel just outside the rectangle stays black (no red outline).
        outside = image.getpixel((30, 100))[:3]
        self.assertLess(
            max(outside), 60, f"outside should be black, got {outside}"
        )

    def test_rect_rotated_90_degrees(self):
        """
        A 100x20 rect rotated 90° around its bbox centre ends up
        looking like a 20x100 rect. Fabric's UI rotation updates
        `left`/`top` so the bbox centre stays put visually — the JSON
        therefore stores left=110, top=50 for a rect that was originally
        at left=50, top=90 (centre (100, 100)).
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        # Post-rotation values fabric would emit.
                        "left": 110,
                        "top": 50,
                        "width": 100,
                        "height": 20,
                        "angle": 90,
                        "fill": "#ff0000",
                        "strokeWidth": 0,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # The rotated rect spans roughly (90, 50)–(110, 150).
        self.assertPixelClose(image.getpixel((100, 60)), (255, 0, 0))
        self.assertPixelClose(image.getpixel((100, 140)), (255, 0, 0))
        # A pixel that used to be inside the un-rotated bbox but is now
        # outside the rotated one stays white.
        self.assertPixelWhite(image.getpixel((140, 100)))

    def test_rect_scaled(self):
        """
        A rect with scaleX=2, scaleY=1.5 should render as if its
        width/height were doubled / 1.5×'d, centered on its bbox.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 80,
                        "top": 80,
                        "width": 40,
                        "height": 40,
                        "scaleX": 2,
                        "scaleY": 1.5,
                        "fill": "#00aa00",
                        "strokeWidth": 0,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Bbox after scale: (80, 80)–(160, 140). Centre (120, 110).
        self.assertPixelClose(image.getpixel((155, 110)), (0, 170, 0))
        self.assertPixelClose(image.getpixel((120, 135)), (0, 170, 0))
        # Just past the scaled bbox stays white.
        self.assertPixelWhite(image.getpixel((165, 110)))

    def test_arrow_rotated(self):
        """
        An arrow pointing right rotated 90° (fabric UI: rotate
        around bbox centre, then store new left/top) should point down.
        Fabric stores left=104, top=60 for an arrow originally at
        left=60, top=96 (centre (100, 100)).
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "arrow",
                        "x1": 60,
                        "y1": 100,
                        "x2": 140,
                        "y2": 100,
                        # Post-rotation values fabric emits.
                        "left": 104,
                        "top": 60,
                        "width": 80,
                        "height": 8,
                        "angle": 90,
                        "stroke": "#000000",
                        "strokeWidth": 4,
                        "arrowHeadSize": 0,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Vertical at x=100 from y≈60 to y≈140.
        self.assertPixelColored(image.getpixel((100, 70)))
        self.assertPixelColored(image.getpixel((100, 130)))
        self.assertPixelWhite(image.getpixel((75, 100)))

    def test_psstroke_translated_after_creation(self):
        """
        A PSStroke whose `left` has shifted (the user dragged it
        right) must render at the new position even when strokeOffset
        is not in the JSON. Pivot must come from the strokePoints'
        bbox, not the moved bbox centre.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "PSStroke",
                        "stroke": "#000000",
                        "strokeWidth": 8,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        # Original stroke ran from x=40..80 at y=100.
                        # User dragged it +60 → left = 100 (was 40).
                        "left": 100,
                        "top": 96,
                        "width": 40,
                        "height": 8,
                        "strokePoints": [
                            {"x": 40, "y": 100, "pressure": 1.0},
                            {"x": 80, "y": 100, "pressure": 1.0},
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # The stroke should now sit between x=100 and x=140 (its
        # original 40-pixel length shifted right by 60). The middle
        # should be black, and the original (now empty) location stays
        # white.
        self.assertPixelColored(image.getpixel((120, 100)))
        self.assertPixelWhite(image.getpixel((60, 100)))

    def test_path_translated_after_creation(self):
        """
        Same scenario for a fabric.Path: the user moved it but the
        path commands themselves stayed in their original calcDim
        space. With no pathOffset in the JSON, the pivot must fall back
        to the path's own bbox so the new `left` actually shifts the
        rendering.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "path",
                        "stroke": "#ff00ff",
                        "strokeWidth": 6,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        # Original path spanned x=40..80 at y=100. User
                        # dragged it +60 → left = 100 (was 40).
                        "left": 100,
                        "top": 96,
                        "width": 40,
                        "height": 8,
                        "path": [
                            ["M", 40, 100],
                            ["L", 80, 100],
                        ],
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        self.assertPixelClose(image.getpixel((120, 100)), (255, 0, 255))
        self.assertPixelWhite(image.getpixel((60, 100)))

    def test_rotated_and_translated_strokes_stay_independent(self):
        """
        When the same drawing contains one rotated PSStroke and one
        translated PSStroke, each must use its OWN bbox metadata — the
        translation of stroke B must not shift the rendering of stroke
        A. Regression for a state-leakage bug across objects.
        """
        path = self._temp_image(size=(300, 200))
        annotation = {
            "drawing": {
                "objects": [
                    # Stroke A: horizontal at y=100 from x=40..60,
                    # rotated 90° by fabric UI around bbox centre
                    # (50, 100) → fabric updates left/top to (50, 90).
                    {
                        "type": "PSStroke",
                        "stroke": "#ff0000",
                        "strokeWidth": 8,
                        "canvasWidth": 300,
                        "canvasHeight": 200,
                        "left": 50,
                        "top": 90,
                        "width": 20,
                        "height": 0,
                        "angle": 90,
                        "strokePoints": [
                            {"x": 40, "y": 100, "pressure": 1.0},
                            {"x": 60, "y": 100, "pressure": 1.0},
                        ],
                    },
                    # Stroke B: original strokePoints at x=100..160,
                    # then user translated it +60 → left=160.
                    {
                        "type": "PSStroke",
                        "stroke": "#0000ff",
                        "strokeWidth": 8,
                        "canvasWidth": 300,
                        "canvasHeight": 200,
                        "left": 160,
                        "top": 100,
                        "width": 60,
                        "height": 0,
                        "strokePoints": [
                            {"x": 100, "y": 100, "pressure": 1.0},
                            {"x": 160, "y": 100, "pressure": 1.0},
                        ],
                    },
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Stroke A (rotated 90° around 50, 100): a pixel above the
        # original horizontal segment is now red.
        self.assertPixelColored(image.getpixel((50, 95)))
        # Stroke B (translated +60): now spans x=160..220 at y=100.
        self.assertPixelColored(image.getpixel((190, 100)))
        # A pixel WAY past stroke A (the contaminated rendering would
        # have shifted A to x=110, dragging it past its original area
        # without rotation). At x=110 should be white.
        self.assertPixelWhite(image.getpixel((110, 100)))

    def test_real_psstroke_rotate_plus_translate_user_report(self):
        """
        Render the annotation of a user report: one PSStroke is moved,
        the other is rotated by 24.35 degrees and moved. Each stroke
        must render at its own fabric position.
        """
        path = self._temp_image(size=(1080, 605))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "PSStroke",
                        "stroke": "#ff3860",
                        "strokeWidth": 10,
                        "canvasWidth": 1077.05,
                        "canvasHeight": 605,
                        "left": 218.08,
                        "top": 260.06,
                        "width": 712.64,
                        "height": 22.59,
                        "angle": 0,
                        "scaleX": 1,
                        "scaleY": 1,
                        "strokePoints": [
                            {"x": 214.28, "y": 460.0, "pressure": 1.0},
                            {"x": 926.92, "y": 480.0, "pressure": 1.0},
                        ],
                    },
                    {
                        "type": "PSStroke",
                        "stroke": "#ff3860",
                        "strokeWidth": 10,
                        "canvasWidth": 1077.05,
                        "canvasHeight": 605,
                        "left": 220.67,
                        "top": -44.86,
                        "width": 771.03,
                        "height": 31.89,
                        "angle": 24.35,
                        "scaleX": 1,
                        "scaleY": 1,
                        "strokePoints": [
                            {"x": 182.28, "y": 119.31, "pressure": 1.0},
                            {"x": 953.31, "y": 150.50, "pressure": 1.0},
                        ],
                    },
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)

        # Stroke A is moved up: it renders from y=261 to y=281, and
        # nothing stays at its old position (y=468).
        self.assertPixelColored(image.getpixel((500, 270)))
        self.assertPixelWhite(image.getpixel((500, 468)))

        # Stroke B is rotated by 24.35 degrees. If the angle is wrong
        # (snapped to 0 or 90), this pixel stays white.
        self.assertPixelColored(image.getpixel((600, 150)))

    def test_eraser_punches_hole_in_filled_rect(self):
        """
        A filled red rect with a horizontal eraser path through the
        middle should keep the top and bottom bands red and clear a
        transparent band in the centre.

        Path geometry: the eraser group is layout=fixed at origin
        (0, 0) with the parent's local dimensions (100x100). A path
        child with left=-30, top=-20, width=60, height=40 puts its
        bbox-top-left at (-30, -20) in eraser-centered coords. The
        path commands draw a horizontal line at y=20 in path-local
        coords → spans (-30, 0) to (30, 0) in eraser-centered →
        (70, 100) to (130, 100) in canvas, stroked 40px → covers
        the band y≈80..120, x≈70..130 of the rect.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 50,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "fill": "#ff0000",
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "eraser": {
                            "type": "eraser",
                            "width": 100,
                            "height": 100,
                            "objects": [
                                {
                                    "type": "path",
                                    "left": -30,
                                    "top": -20,
                                    "width": 60,
                                    "height": 40,
                                    "scaleX": 1,
                                    "scaleY": 1,
                                    "angle": 0,
                                    "stroke": "#000",
                                    "strokeWidth": 40,
                                    "pathOffset": {"x": 30, "y": 20},
                                    "path": [
                                        ["M", 0, 20],
                                        ["L", 60, 20],
                                    ],
                                }
                            ],
                        },
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Top of the rect stays red.
        self.assertPixelClose(image.getpixel((100, 60)), (255, 0, 0))
        # Bottom of the rect stays red.
        self.assertPixelClose(image.getpixel((100, 140)), (255, 0, 0))
        # Centre of the rect is erased → background shows through (white).
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_eraser_follows_rotated_parent(self):
        """
        Eraser paths are stored in the parent's local centered frame:
        rotating the parent rotates the erased band with it. A 90°
        rotation of the rect above should turn the horizontal erased
        band into a vertical erased band.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        # 90° rotation around the original bbox centre
                        # leaves the centre at (100, 100); fabric stores
                        # the post-rotation left/top so that the rotated
                        # bbox lines up with the centre.
                        "left": 150,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "angle": 90,
                        "fill": "#ff0000",
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "eraser": {
                            "type": "eraser",
                            "width": 100,
                            "height": 100,
                            "objects": [
                                {
                                    "type": "path",
                                    "left": -30,
                                    "top": -20,
                                    "width": 60,
                                    "height": 40,
                                    "scaleX": 1,
                                    "scaleY": 1,
                                    "angle": 0,
                                    "stroke": "#000",
                                    "strokeWidth": 40,
                                    "pathOffset": {"x": 30, "y": 20},
                                    "path": [
                                        ["M", 0, 20],
                                        ["L", 60, 20],
                                    ],
                                }
                            ],
                        },
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # After 90° rotation the erased band runs vertically through the
        # centre. Top of the band is now erased…
        self.assertPixelWhite(image.getpixel((100, 80)))
        # …bottom too.
        self.assertPixelWhite(image.getpixel((100, 120)))
        # …and the left/right of the rect (now top/bottom in the rotated
        # frame) stay red.
        self.assertPixelClose(image.getpixel((75, 100)), (255, 0, 0))
        self.assertPixelClose(image.getpixel((125, 100)), (255, 0, 0))

    def test_eraser_on_one_object_does_not_affect_siblings(self):
        """
        Two filled rects side by side. Only the left one carries an
        eraser; the right one must stay fully red.
        """
        path = self._temp_image(size=(300, 200))
        eraser_payload = {
            "type": "eraser",
            "width": 80,
            "height": 80,
            "objects": [
                {
                    "type": "path",
                    "left": -30,
                    "top": -15,
                    "width": 60,
                    "height": 30,
                    "scaleX": 1,
                    "scaleY": 1,
                    "angle": 0,
                    "stroke": "#000",
                    "strokeWidth": 30,
                    "pathOffset": {"x": 30, "y": 15},
                    "path": [["M", 0, 15], ["L", 60, 15]],
                }
            ],
        }
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 40,
                        "top": 60,
                        "width": 80,
                        "height": 80,
                        "fill": "#ff0000",
                        "canvasWidth": 300,
                        "canvasHeight": 200,
                        "eraser": eraser_payload,
                    },
                    {
                        "type": "rect",
                        "left": 180,
                        "top": 60,
                        "width": 80,
                        "height": 80,
                        "fill": "#ff0000",
                        "canvasWidth": 300,
                        "canvasHeight": 200,
                    },
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Left rect centre is erased.
        self.assertPixelWhite(image.getpixel((80, 100)))
        # Right rect centre is intact.
        self.assertPixelClose(image.getpixel((220, 100)), (255, 0, 0))

    def test_eraser_on_psstroke_clears_segment(self):
        """
        A freehand stroke crossing the centre of the canvas with an
        eraser path clipping its middle should keep its ends and lose
        its centre.
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "PSStroke",
                        "stroke": "#0000ff",
                        "strokeWidth": 10,
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "left": 30,
                        "top": 95,
                        "width": 140,
                        "height": 10,
                        "strokePoints": [
                            {"x": 30, "y": 100, "pressure": 1.0},
                            {"x": 170, "y": 100, "pressure": 1.0},
                        ],
                        "eraser": {
                            "type": "eraser",
                            "width": 140,
                            "height": 10,
                            "objects": [
                                {
                                    "type": "path",
                                    "left": -25,
                                    "top": -10,
                                    "width": 50,
                                    "height": 20,
                                    "scaleX": 1,
                                    "scaleY": 1,
                                    "angle": 0,
                                    "stroke": "#000",
                                    "strokeWidth": 30,
                                    "pathOffset": {"x": 25, "y": 10},
                                    "path": [
                                        ["M", 0, 10],
                                        ["L", 50, 10],
                                    ],
                                }
                            ],
                        },
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        # Left end of the stroke is still blue.
        self.assertPixelClose(image.getpixel((40, 100)), (0, 0, 255))
        # Right end is still blue.
        self.assertPixelClose(image.getpixel((160, 100)), (0, 0, 255))
        # Middle of the stroke has been erased.
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_empty_eraser_leaves_object_intact(self):
        """
        An object with an eraser carrying no paths should render
        normally (no false-positive erasing of the whole shape).
        """
        path = self._temp_image(size=(200, 200))
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "rect",
                        "left": 50,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "fill": "#ff0000",
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                        "eraser": {
                            "type": "eraser",
                            "width": 100,
                            "height": 100,
                            "objects": [],
                        },
                    }
                ]
            }
        }
        annotations_renderer.render_annotation_on_image(path, annotation)
        image = Image.open(path)
        self.assertPixelClose(image.getpixel((100, 100)), (255, 0, 0))

    def test_unknown_type_does_not_raise(self):
        path = self._temp_image()
        before = Image.open(path).getpixel((100, 100))
        annotations_renderer.render_annotation_on_image(
            path,
            {"drawing": {"objects": [{"type": "spaceship"}]}},
        )
        after = Image.open(path).getpixel((100, 100))
        self.assertEqual(before, after)

    def _render_text(self, text, font_path):
        path = self._temp_image()
        annotation = {
            "drawing": {
                "objects": [
                    {
                        "type": "i-text",
                        "text": text,
                        "left": 20,
                        "top": 20,
                        "fontSize": 30,
                        "fill": "#ff0000",
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ]
            }
        }
        with mock.patch.object(
            annotations_renderer, "DEFAULT_FONT_PATHS", [font_path]
        ):
            annotations_renderer.render_annotation_on_image(path, annotation)
        return Image.open(path)

    def assertSameImage(self, actual, expected):
        self.assertIsNone(ImageChops.difference(actual, expected).getbbox())

    def test_text_breaks_its_lines_like_the_kitsu_canvas(self):
        # Pillow's default font always skips raqm, the layout library at
        # fault here: load the same face from a file instead.
        fd, font_path = tempfile.mkstemp(suffix=".ttf")
        with os.fdopen(fd, "wb") as font_file:
            font_file.write(ImageFont.load_default(10).font_bytes)
        self._paths = getattr(self, "_paths", []) + [font_path]
        two_lines = self._render_text("Kitsu\nZou", font_path)
        one_line = self._render_text("Kitsu Zou", font_path)
        blank = Image.open(self._temp_image())
        self.assertIsNotNone(ImageChops.difference(two_lines, blank).getbbox())

        self.assertSameImage(
            self._render_text("Kitsu\r\nZou", font_path), two_lines
        )
        for separator in ("\r", "\x1c", "\x1d", "\x1e", "\x85", "\u2029"):
            with self.subTest(separator=separator):
                self.assertSameImage(
                    self._render_text(f"Kitsu{separator}Zou", font_path),
                    one_line,
                )

    def _render(self, *objects, size=(200, 200)):
        path = self._temp_image(size)
        canvas = {"canvasWidth": size[0], "canvasHeight": size[1]}
        objects = [
            {**canvas, **obj} if isinstance(obj, dict) else obj
            for obj in objects
        ]
        annotations_renderer.render_annotation_on_image(
            path, {"drawing": {"objects": objects}}
        )
        return Image.open(path)

    def test_non_dict_objects_are_skipped(self):
        image = self._render(
            "junk",
            {
                "type": "rect",
                "left": 50,
                "top": 50,
                "width": 100,
                "height": 100,
                "stroke": "#ff0000",
                "strokeWidth": 4,
            },
        )
        self.assertPixelClose(image.getpixel((50, 100)), (255, 0, 0))

    def test_broken_object_does_not_stop_the_next_ones(self):
        image = self._render(
            {"type": "rect", "width": "wide", "height": 10},
            {
                "type": "rect",
                "left": 50,
                "top": 50,
                "width": 100,
                "height": 100,
                "stroke": "#ff0000",
                "strokeWidth": 4,
            },
        )
        self.assertPixelClose(image.getpixel((50, 100)), (255, 0, 0))

    def test_group_draws_its_children(self):
        image = self._render(
            {
                "type": "group",
                "objects": [
                    {
                        "type": "rect",
                        "left": 50,
                        "top": 50,
                        "width": 100,
                        "height": 100,
                        "fill": "#0000ff",
                        "canvasWidth": 200,
                        "canvasHeight": 200,
                    }
                ],
            }
        )
        self.assertPixelClose(image.getpixel((100, 100)), (0, 0, 255))
        self.assertPixelWhite(image.getpixel((20, 20)))

    def test_rect_without_stroke_width_gets_a_thin_outline(self):
        image = self._render(
            {
                "type": "rect",
                "left": 50,
                "top": 50,
                "width": 100,
                "height": 100,
                "stroke": "#ff0000",
                "strokeWidth": None,
            }
        )
        self.assertPixelColored(image.getpixel((50, 100)))
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_flat_rect_and_ellipse_draw_nothing(self):
        image = self._render(
            {
                "type": "rect",
                "left": 100,
                "top": 50,
                "width": 0,
                "height": 100,
                "stroke": "#ff0000",
                "strokeWidth": 4,
            },
            {
                "type": "ellipse",
                "left": 50,
                "top": 60,
                "rx": 0,
                "ry": 40,
                "stroke": "#0000ff",
                "strokeWidth": 4,
            },
        )
        self.assertPixelWhite(image.getpixel((100, 100)))
        self.assertPixelWhite(image.getpixel((50, 100)))

    def test_draws_filled_circle_from_radius(self):
        image = self._render(
            {
                "type": "circle",
                "left": 50,
                "top": 50,
                "radius": 50,
                "fill": "#0000ff",
            }
        )
        self.assertPixelClose(image.getpixel((100, 100)), (0, 0, 255))
        self.assertPixelWhite(image.getpixel((20, 20)))

    def test_draws_ellipse_from_width_and_height(self):
        image = self._render(
            {
                "type": "ellipse",
                "left": 50,
                "top": 70,
                "width": 100,
                "height": 60,
                "stroke": "#ff0000",
                "strokeWidth": 4,
            }
        )
        # Top and left of the ellipse, its centre has no fill.
        self.assertPixelClose(image.getpixel((100, 71)), (255, 0, 0))
        self.assertPixelClose(image.getpixel((51, 100)), (255, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_draws_line(self):
        image = self._render(
            {
                "type": "line",
                "x1": 40,
                "y1": 100,
                "x2": 160,
                "y2": 100,
                "stroke": "rgb(0, 128, 0)",
                "strokeWidth": 4,
            }
        )
        self.assertPixelClose(image.getpixel((100, 100)), (0, 128, 0))
        self.assertPixelWhite(image.getpixel((100, 150)))

    def test_polyline_stays_open(self):
        image = self._render(
            {
                "type": "polyline",
                "stroke": "#0000ff",
                "strokeWidth": 4,
                "points": [
                    {"x": 40, "y": 60},
                    {"x": 100, "y": 140},
                    {"x": 160, "y": 60},
                ],
            }
        )
        self.assertPixelClose(image.getpixel((70, 100)), (0, 0, 255))
        self.assertPixelClose(image.getpixel((130, 100)), (0, 0, 255))
        # The gap between the first and the last point is not closed.
        self.assertPixelWhite(image.getpixel((100, 60)))

    def test_draws_filled_polygon_with_outline(self):
        image = self._render(
            {
                "type": "polygon",
                "fill": "#00ff00",
                "stroke": "#000000",
                "strokeWidth": 4,
                "points": [
                    {"x": 40, "y": 160},
                    {"x": 160, "y": 160},
                    {"x": 100, "y": 40},
                ],
            }
        )
        self.assertPixelClose(image.getpixel((100, 120)), (0, 255, 0))
        self.assertPixelClose(image.getpixel((100, 160)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((20, 20)))

    def test_a_gradient_fill_keeps_the_outline(self):
        """
        Fabric serializes a gradient fill as a dict. The rect is drawn
        without a fill, with its outline.
        """
        image = self._render(
            {
                "type": "rect",
                "left": 40,
                "top": 40,
                "width": 120,
                "height": 120,
                "fill": {"type": "linear", "colorStops": []},
                "stroke": "#ff0000",
                "strokeWidth": 4,
            }
        )
        self.assertPixelClose(image.getpixel((40, 100)), (255, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_arrow_with_negative_head_size_draws_only_the_body(self):
        image = self._render(
            {
                "type": "arrow",
                "x1": 40,
                "y1": 100,
                "x2": 160,
                "y2": 100,
                "stroke": "#000000",
                "strokeWidth": 4,
                "arrowHeadSize": -30,
            }
        )
        self.assertPixelClose(image.getpixel((157, 100)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((178, 100)))

    def test_text_background_is_painted(self):
        image = self._render(
            {
                "type": "text",
                "text": "Hi",
                "left": 50,
                "top": 50,
                "fontSize": 40,
                "fill": "#000000",
                "backgroundColor": "#ff0000",
            }
        )
        red_pixels = [
            p
            for p in image.getdata()
            if p[0] > 200 and p[1] < 60 and p[2] < 60
        ]
        self.assertGreater(len(red_pixels), 100)

    def test_rotated_text_turns_upright(self):
        text = {
            "type": "text",
            "text": "IIIIIIIIII",
            "left": 60,
            "top": 60,
            "fontSize": 30,
            "fill": "#000000",
        }
        blank = Image.open(self._temp_image())
        flat = ImageChops.difference(self._render(text), blank).getbbox()
        upright = ImageChops.difference(
            self._render({**text, "angle": 90}), blank
        ).getbbox()
        self.assertGreater(flat[2] - flat[0], flat[3] - flat[1])
        self.assertGreater(upright[3] - upright[1], upright[2] - upright[0])

    def test_load_font_skips_missing_and_broken_files(self):
        fd, good_path = tempfile.mkstemp(suffix=".ttf")
        with os.fdopen(fd, "wb") as font_file:
            font_file.write(ImageFont.load_default(10).font_bytes)
        fd, broken_path = tempfile.mkstemp(suffix=".ttf")
        with os.fdopen(fd, "wb") as font_file:
            font_file.write(b"not a font")
        self._paths = getattr(self, "_paths", []) + [good_path, broken_path]
        candidates = ["/nonexistent/font.ttf", broken_path, good_path]
        with mock.patch.object(
            annotations_renderer, "DEFAULT_FONT_PATHS", candidates
        ):
            font = annotations_renderer._load_font(12)
        self.assertEqual(font.path, good_path)

    def test_load_font_falls_back_to_the_default_font(self):
        with mock.patch.object(
            annotations_renderer,
            "DEFAULT_FONT_PATHS",
            ["/nonexistent/font.ttf"],
        ):
            font = annotations_renderer._load_font(12)
        self.assertIsNotNone(font.getbbox("A"))

    def test_psstroke_uses_its_stroke_offset_as_pivot(self):
        image = self._render(
            {
                "type": "PSStroke",
                "stroke": "#000000",
                "strokeWidth": 6,
                "left": 60,
                "top": 99,
                "width": 80,
                "height": 2,
                "strokeOffset": {"x": 40, "y": -50},
                "strokePoints": [
                    {"x": 0, "y": 0, "pressure": 1},
                    {"x": 80, "y": 0, "pressure": 1},
                ],
            }
        )
        # Without the offset, the pivot is the centre of the points and
        # the stroke lands on y=100.
        self.assertPixelClose(image.getpixel((100, 150)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 100)))

    def test_psstroke_without_pressure_uses_full_width(self):
        image = self._render(
            {
                "type": "PSStroke",
                "stroke": "#000000",
                "strokeWidth": 10,
                "strokePoints": [{"x": 40, "y": 100}, {"x": 160, "y": 100}],
            }
        )
        self.assertPixelClose(image.getpixel((100, 103)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 110)))

    def test_path_string_closes_on_z(self):
        image = self._render(
            {
                "type": "path",
                "stroke": "#000000",
                "strokeWidth": 4,
                "path": "M 40 40 L 160 40 L 160 160 Z",
            }
        )
        # (100, 100) is on the closing edge from (160, 160) to (40, 40).
        self.assertPixelClose(image.getpixel((100, 100)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((60, 140)))

    def test_path_quadratic_curve_bends_to_its_control_point(self):
        image = self._render(
            {
                "type": "path",
                "stroke": "#000000",
                "strokeWidth": 4,
                "path": [["M", 40, 150], ["Q", 100, 30, 160, 150]],
            }
        )
        # The curve passes through (100, 90) at t=0.5.
        self.assertPixelClose(image.getpixel((100, 90)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 150)))

    def test_path_cubic_curve_bends_to_its_control_points(self):
        image = self._render(
            {
                "type": "path",
                "stroke": "#000000",
                "strokeWidth": 4,
                "path": [["M", 40, 150], ["C", 40, 50, 160, 50, 160, 150]],
            }
        )
        # The curve passes through (100, 75) at t=0.5.
        self.assertPixelClose(image.getpixel((100, 75)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 150)))

    def test_path_without_move_starts_at_its_first_point(self):
        stroke = {"type": "path", "stroke": "#000000", "strokeWidth": 4}
        image = self._render(
            {**stroke, "path": [["L", 40, 60], ["L", 160, 60]]},
            {**stroke, "path": [["Q", 40, 100, 160, 100]]},
            {**stroke, "path": [["C", 40, 140, 100, 140, 160, 140]]},
        )
        for y in (60, 100, 140):
            self.assertPixelClose(image.getpixel((100, y)), (0, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 80)))
        self.assertPixelWhite(image.getpixel((100, 120)))

    def test_eraser_skips_children_that_are_not_paths(self):
        image = self._render(
            {
                "type": "rect",
                "left": 50,
                "top": 50,
                "width": 100,
                "height": 100,
                "fill": "#ff0000",
                "eraser": {
                    "type": "eraser",
                    "width": 100,
                    "height": 100,
                    "objects": [
                        "junk",
                        {"type": "rect", "width": 10, "height": 10},
                        {
                            "type": "path",
                            "left": -30,
                            "top": -20,
                            "width": 60,
                            "height": 40,
                            "strokeWidth": 40,
                            "pathOffset": {"x": 30, "y": 20},
                            "path": [["M", 0, 20], ["L", 60, 20]],
                        },
                    ],
                },
            }
        )
        self.assertPixelClose(image.getpixel((100, 60)), (255, 0, 0))
        self.assertPixelWhite(image.getpixel((100, 100)))


class ParsePathStringTestCase(unittest.TestCase):
    def test_exponents_and_leading_dots_are_one_number_each(self):
        commands = annotations_renderer._parse_path_string(
            "M 1e-5 .5 L 2.5E2 -.25"
        )

        self.assertEqual(commands, [["M", 1e-5, 0.5], ["L", 250.0, -0.25]])

    def test_path_that_is_not_a_string_or_a_list_has_no_commands(self):
        self.assertEqual(annotations_renderer._parse_path_commands(42), [])

    def test_lone_move_is_dropped(self):
        segments = annotations_renderer._path_to_segments(
            [["M", 1, 1], ["M", 2, 2], ["L", 3, 3]], lambda x, y: (x, y)
        )

        self.assertEqual(segments, [[(2, 2), (3, 3)]])


class ParseColorTestCase(unittest.TestCase):
    def test_rgba_alpha_above_one_is_a_0_to_255_value(self):
        parse = annotations_renderer._parse_color

        self.assertEqual(parse("rgba(10, 20, 30, 128)"), (10, 20, 30, 128))
        self.assertEqual(parse("rgba(10, 20, 30, 300)"), (10, 20, 30, 255))

    def test_hex_color_keeps_its_alpha(self):
        self.assertEqual(
            annotations_renderer._parse_color("#ff000080"), (255, 0, 0, 128)
        )

    def test_unknown_color_returns_the_default(self):
        self.assertEqual(
            annotations_renderer._parse_color("not-a-color", default="d"),
            "d",
        )


if __name__ == "__main__":
    unittest.main()
