import os
import tempfile
import unittest

from PIL import Image

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
        """Real fabric.js paths carry left/top/width/height/pathOffset.
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
        """Real fabric.js Line/Arrow store x1,y1,x2,y2 in canvas-absolute
        coords. left/top are bbox metadata and must NOT be added on top."""
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
        """PSStroke (pressure brush, the freehand tool in Kitsu) stores
        points under `strokePoints`, not `path`. Each point has x/y/pressure
        in canvas-absolute coords."""
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
        """PSBrush uses lineWidth = pressure * strokeWidth per segment.
        Low pressure must produce a noticeably thinner line — a pixel a
        few rows above the centerline should stay white at low pressure
        but be coloured at high pressure."""
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
        """Pillow's draw.line rounds endpoints with a disk of radius
        width/2; without compensation the body sticks out past the
        triangular head. We shorten the body so the head fully covers
        the tip."""
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
        """Kitsu's whiteboard sticker (annotation.js:212) is a fabric.Rect
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

    def test_unknown_type_does_not_raise(self):
        path = self._temp_image()
        before = Image.open(path).getpixel((100, 100))
        annotations_renderer.render_annotation_on_image(
            path,
            {"drawing": {"objects": [{"type": "spaceship"}]}},
        )
        after = Image.open(path).getpixel((100, 100))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
