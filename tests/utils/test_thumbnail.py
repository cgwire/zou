import unittest
import os

from PIL import Image, ImageCms

from werkzeug.datastructures import FileStorage

from zou.app.services.exception import WrongParameterException
from zou.app.utils import thumbnail, fs

TEST_FOLDER = os.path.join("tests", "tmp")


class ThumbnailTestCase(unittest.TestCase):
    def get_fixture_file_path(self, relative_path):
        current_path = os.getcwd()
        file_path_fixture = os.path.join(
            current_path, "tests", "fixtures", relative_path
        )
        return file_path_fixture

    def setUp(self):
        super().setUp()
        fs.mkdir_p(TEST_FOLDER)
        self.folder_name = os.path.join(TEST_FOLDER, "persons")

    def tearDown(self):
        super().tearDown()
        fs.rm_rf(self.folder_name)
        # Only remove what these tests create (everything lives in
        # TEST_FOLDER). Never touch PREVIEW_FOLDER: outside CI it can
        # resolve to a live development preview store.
        fs.rm_rf(TEST_FOLDER)

    def test_turn_into_thumbnail(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/th01.png")
        full_path = os.path.join(
            TEST_FOLDER, thumbnail.get_file_name("instance-id")
        )
        fs.copyfile(file_path_fixture, full_path)

        thumbnail.turn_into_thumbnail(full_path)
        im = Image.open(full_path)
        width, height = im.size
        self.assertEqual(width, 180)
        self.assertEqual(height, 101)

        thumbnail.turn_into_thumbnail(full_path, thumbnail.RECTANGLE_SIZE)
        im = Image.open(full_path)
        width, height = im.size
        self.assertEqual(width, 150)
        self.assertEqual(height, 100)

    def test_convert_jpg_to_png(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/th04.jpg")
        file_name = "th04.jpg"
        file_path = os.path.join(TEST_FOLDER, file_name)
        fs.copyfile(file_path_fixture, file_path)
        im = Image.open(file_path)

        thumbnail.convert_jpg_to_png(file_path)
        result_path = os.path.join(TEST_FOLDER, "th04.png")
        im = Image.open(result_path)
        self.assertEqual(dict(im.info), {})
        self.assertTrue(os.path.exists(result_path))

    def test_save_file(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/th01.png")
        th_file = FileStorage(
            stream=open(file_path_fixture, "rb"), filename="th01.png"
        )
        full_path = thumbnail.save_file(TEST_FOLDER, "instance-id", th_file)

        thumbnail.turn_into_thumbnail(full_path, thumbnail.RECTANGLE_SIZE)
        im = Image.open(full_path)
        width, height = im.size
        self.assertEqual(width, 150)
        self.assertEqual(height, 100)

    def test_save_file_rejects_a_file_that_is_not_a_picture(self):
        source_path = os.path.join(TEST_FOLDER, "not-a-picture.png")
        with open(source_path, "w") as source:
            source.write("<svg xmlns='http://www.w3.org/2000/svg'/>")

        with open(source_path, "rb") as stream:
            th_file = FileStorage(stream=stream, filename="logo.png")
            with self.assertLogs(thumbnail.logger, "WARNING") as logs:
                with self.assertRaises(WrongParameterException) as refusal:
                    thumbnail.save_file(TEST_FOLDER, "instance-id", th_file)

        # The Pillow error and the temporary path go to the log, the
        # response only says the file is not a picture.
        self.assertIn("instance-id.png", logs.output[0])
        self.assertNotIn("instance-id", str(refusal.exception))

        # The temporary file must not survive the failure.
        self.assertFalse(
            os.path.exists(os.path.join(TEST_FOLDER, "instance-id.png"))
        )

    def test_url_path(self):
        url_path = thumbnail.url_path("shots", "instance-id")
        self.assertEqual(url_path, "pictures/thumbnails/shots/instance-id.png")
        url_path = thumbnail.url_path("working_files", "instance-id")
        self.assertEqual(
            url_path, "pictures/thumbnails/working-files/instance-id.png"
        )

    def test_flat(self):
        flatten_tupple = thumbnail.flat(1.2, 3.1, 4.2)
        self.assertEqual(flatten_tupple, (1, 3, 4))

    def test_get_full_size_from_width(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/th01.png")
        im = Image.open(file_path_fixture)
        size = thumbnail.get_full_size_from_width(im, 1200)
        self.assertEqual(size, (1200, 674))

    def test_prepare_image_for_thumbnail(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/th01.png")
        im = Image.open(file_path_fixture)
        im = thumbnail.prepare_image_for_thumbnail(im, thumbnail.SQUARE_SIZE)
        self.assertEqual(im.size, (101, 101))

        file_path_fixture = self.get_fixture_file_path("thumbnails/th02.png")
        im = Image.open(file_path_fixture)
        im = thumbnail.prepare_image_for_thumbnail(
            im, thumbnail.RECTANGLE_SIZE
        )
        self.assertEqual(im.size, (152, 101))

        file_path_fixture = self.get_fixture_file_path("thumbnails/th03.png")
        im = Image.open(file_path_fixture)
        im = thumbnail.prepare_image_for_thumbnail(
            im, thumbnail.RECTANGLE_SIZE
        )
        self.assertEqual(im.size, (180, 120))

    def test_generate_preview_variants(self):
        preview_id = "123413-12312"
        file_path_fixture = self.get_fixture_file_path("thumbnails/th01.png")
        file_name = thumbnail.get_file_name(preview_id)
        original_path = os.path.join(TEST_FOLDER, file_name)
        fs.copyfile(file_path_fixture, original_path)
        thumbnail.generate_preview_variants(original_path, preview_id)

        file_path = os.path.join(TEST_FOLDER, f"previews-{preview_id}.png")
        self.assertTrue(os.path.exists(file_path))
        self.assertTrue(Image.open(file_path).size, thumbnail.PREVIEW_SIZE)

        file_path = os.path.join(TEST_FOLDER, f"thumbnails-{preview_id}.png")
        self.assertTrue(os.path.exists(file_path))
        self.assertTrue(Image.open(file_path).size, thumbnail.RECTANGLE_SIZE)

        file_path = os.path.join(
            TEST_FOLDER, f"thumbnails-square-{preview_id}.png"
        )
        self.assertTrue(os.path.exists(file_path))
        self.assertTrue(Image.open(file_path).size, thumbnail.SQUARE_SIZE)

    def test_to_srgb(self):
        profile = ImageCms.ImageCmsProfile(
            ImageCms.createProfile("sRGB")
        ).tobytes()

        im = Image.new("RGB", (4, 4), (200, 30, 30))
        im.info["icc_profile"] = profile
        self.assertEqual(thumbnail.to_srgb(im).tobytes(), im.tobytes())

        im = Image.new("RGBA", (4, 4), (200, 30, 30, 128))
        im.info["icc_profile"] = profile
        converted = thumbnail.to_srgb(im)
        self.assertEqual(converted.mode, "RGBA")
        self.assertEqual(converted.getpixel((0, 0)), (200, 30, 30, 128))

        im = Image.new("CMYK", (4, 4), (0, 255, 255, 0))
        self.assertEqual(thumbnail.to_srgb(im).mode, "RGB")
        self.assertEqual(thumbnail.to_srgb(im, "RGBA").mode, "RGBA")
        self.assertEqual(
            thumbnail.to_srgb(im, "RGBA").getpixel((0, 0))[3], 255
        )

        im.info["icc_profile"] = b"not a profile"
        self.assertEqual(thumbnail.to_srgb(im).mode, "RGB")

        im = Image.new("L", (4, 4))
        self.assertEqual(thumbnail.to_srgb(im).mode, "L")

        im = Image.new("RGB", (4, 4), (0, 0, 0))
        im.info["transparency"] = (0, 0, 0)
        im.info["icc_profile"] = profile
        converted = thumbnail.to_srgb(im)
        self.assertEqual(converted.mode, "RGBA")
        self.assertEqual(converted.getpixel((0, 0))[3], 0)

        im = Image.new("I;16", (4, 4), 32768)
        converted = thumbnail.to_srgb(im)
        self.assertEqual(converted.mode, "L")
        self.assertEqual(converted.getpixel((0, 0)), 128)

    def test_thumbnail_keeps_transparency(self):
        profile = ImageCms.ImageCmsProfile(
            ImageCms.createProfile("sRGB")
        ).tobytes()

        rgba = Image.new("RGBA", (600, 300), (0, 0, 0, 0))
        rgba.paste((30, 120, 200, 255), (100, 100, 500, 200))
        rgb = Image.new("RGB", (600, 300), (0, 0, 0))
        rgb.paste((30, 120, 200), (100, 100, 500, 200))

        # A PNG carries its transparency either as an alpha channel or, once
        # it went through a converter such as ImageMagick, as a tRNS colour
        # key on a truecolour picture. Both must survive the upload, with or
        # without an embedded ICC profile.
        sources = [
            (rgba, {}),
            (rgba, {"icc_profile": profile}),
            (rgb, {"transparency": (0, 0, 0)}),
            (rgb, {"transparency": (0, 0, 0), "icc_profile": profile}),
        ]

        for index, (im, params) in enumerate(sources):
            source_path = os.path.join(TEST_FOLDER, f"logo-{index}.png")
            im.save(source_path, **params)
            with open(source_path, "rb") as stream:
                logo_file = FileStorage(stream=stream, filename="logo.png")
                file_path = thumbnail.save_file(
                    TEST_FOLDER, f"instance-id-{index}", logo_file
                )
            thumbnail.turn_into_thumbnail(file_path, thumbnail.BIG_SQUARE_SIZE)

            # The source is letterboxed to 400x200 pasted at y=100, so both
            # pixels sit inside the picture and not in the empty bands.
            result = Image.open(file_path).convert("RGBA")
            self.assertEqual(result.getpixel((5, 200))[3], 0, params)
            self.assertEqual(result.getpixel((200, 200))[3], 255, params)

    def test_thumbnail_keeps_ratio_when_scaling_up(self):
        # A picture smaller than the target box in both dimensions is
        # scaled up to it. Doing that without keeping the ratio squashed
        # every logo under 400x400.
        cases = [
            ((200, 100), (0, 100, 400, 300)),
            ((100, 200), (100, 0, 300, 400)),
            ((100, 100), (0, 0, 400, 400)),
        ]
        for index, (source_size, expected_box) in enumerate(cases):
            file_path = os.path.join(TEST_FOLDER, f"small-{index}.png")
            Image.new("RGBA", source_size, (30, 120, 200, 255)).save(file_path)
            thumbnail.turn_into_thumbnail(file_path, thumbnail.BIG_SQUARE_SIZE)

            result = Image.open(file_path)
            self.assertEqual(result.size, thumbnail.BIG_SQUARE_SIZE)
            self.assertEqual(
                result.getchannel("A").getbbox(), expected_box, source_size
            )

    def test_thumbnail_scales_a_16_bit_greyscale_picture(self):
        # A greyscale PNG at depth 16 reads as mode I;16, which
        # Image.convert() clamps at 255 instead of scaling: the picture used
        # to come back solid white.
        file_path = os.path.join(TEST_FOLDER, "grey-16-bit.png")
        Image.new("I;16", (200, 100), 32768).save(file_path)
        thumbnail.turn_into_thumbnail(file_path, thumbnail.BIG_SQUARE_SIZE)

        result = Image.open(file_path).convert("RGBA")
        self.assertEqual(result.getpixel((200, 200)), (128, 128, 128, 255))

    def test_turn_hdr_into_thumbnail(self):
        file_path_fixture = self.get_fixture_file_path("thumbnails/sample.hdr")
        full_path = os.path.join(TEST_FOLDER, "sample.hdr")
        fs.copyfile(file_path_fixture, full_path)

        thumbnail_path = thumbnail.turn_hdr_into_thumbnail(full_path)
        im = Image.open(thumbnail_path)
        width, height = im.size
        self.assertEqual(width, 300)
        self.assertEqual(height, 200)
