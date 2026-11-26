import logging
import math
import os
import shutil
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageCms, ImageFile, UnidentifiedImageError

from zou.app import config
from zou.app.exceptions import WrongParameterException
from zou.app.utils import fs

logger = logging.getLogger(__name__)

ImageFile.LOAD_TRUNCATED_IMAGES = True

Image.MAX_IMAGE_PIXELS = config.MAX_IMAGE_PIXELS
RECTANGLE_SIZE = 150, 100
SQUARE_SIZE = 100, 100
PREVIEW_SIZE = 1200, 0
BIG_SQUARE_SIZE = 400, 400
BIG_RECTANGLE_SIZE = 300, 200
SRGB_PROFILE = ImageCms.createProfile("sRGB")
# Image.point() scales only I, I;16 and F. The byte order variants
# (I;16B and the others) make it raise an error. A refused upload because
# of a colour problem is worse than a picture left as it was.
HIGH_DEPTH_GREY_MODES = "I", "I;16"


def to_srgb(im, mode="RGB"):
    """
    Convert the given picture to sRGB with its embedded ICC profile.

    Image.convert() ignores that profile: it turns CMYK into RGB with a
    plain arithmetic formula, which oversaturates pictures made for print.
    Wide gamut pictures (Adobe RGB, Display P3) have the same problem when
    a browser reads their pixels as sRGB.

    Return the picture in `mode`, or in RGBA if it has an alpha channel.
    Greyscale pictures in I or I;16 mode come back as L. Other modes
    than CMYK, RGB and RGBA (L, LA, P...) come back without conversion.
    """
    if im.mode in HIGH_DEPTH_GREY_MODES:
        # A greyscale picture deeper than 8 bits (PNG colour type 0 at
        # depth 16). Image.convert() clamps these samples at 255 and does
        # not scale them, so all values above 1/256th of the range come
        # back solid white. Thus scale them down explicitly.
        im = im.point(lambda value: value / 256).convert("L")
    if im.mode not in ("CMYK", "RGB", "RGBA"):
        return im
    if im.mode == "RGB" and im.info.get("transparency") is not None:
        # A tRNS colour key is only in im.info, and littleCMS gives back a
        # new picture whose info does not keep it. Thus turn the key into a
        # real alpha channel first. Else the colour that the key makes
        # transparent (usually black) comes back as an opaque background.
        im = im.convert("RGBA")
    if im.mode == "RGBA":
        mode = "RGBA"
    icc_profile = im.info.get("icc_profile")
    if icc_profile:
        try:
            im = ImageCms.profileToProfile(
                im,
                ImageCms.ImageCmsProfile(BytesIO(icc_profile)),
                SRGB_PROFILE,
                # If the source has no alpha channel, littleCMS fills the
                # alpha channel with zeroes. Thus never ask it for RGBA
                # from CMYK.
                outputMode="RGBA" if im.mode == "RGBA" else "RGB",
            )
        except (ImageCms.PyCMSError, OSError):
            # Do not fail an upload because of a broken or unreadable
            # profile.
            pass
    return im.convert(mode) if im.mode != mode else im


def save_file(tmp_folder, instance_id, file_to_save):
    """
    Save the uploaded picture in the given folder. The function converts
    it to sRGB and writes it as PNG data under the extension of the
    upload. Use this function only for a temporary save of the file. If
    the upload is not a readable picture, raise WrongParameterException.
    On any failure, remove the file.
    """
    extension = "." + file_to_save.filename.split(".")[-1].lower()
    file_name = instance_id + extension.lower()
    file_path = os.path.join(tmp_folder, file_name)
    try:
        file_to_save.save(file_path)
        try:
            im = Image.open(file_path)
            # Image.open() reads only the header. Decode the pixels now,
            # so that a broken picture fails here and not at save() below.
            im.load()
            im = to_srgb(im)
        except (
            UnidentifiedImageError,
            Image.DecompressionBombError,
            OSError,
            ValueError,
            SyntaxError,
        ) as exception:
            # The upload is not a picture that Pillow can read (a SVG or a
            # PDF with a .png name), is too broken for
            # LOAD_TRUNCATED_IMAGES, or is far above MAX_IMAGE_PIXELS.
            # Pillow reports these errors as any exception from OSError
            # to SyntaxError: this depends on the plugin that claimed the
            # header. The file is the problem, not the server, so answer
            # 400 and not 500. The Pillow message contains the temporary
            # path: it goes to the log, where support can read it, and
            # not to the response.
            logger.warning(
                f"Refusing upload {file_path}, not a readable picture: "
                f"{type(exception).__name__}: {exception}"
            )
            raise WrongParameterException(
                "Uploaded file is not a readable picture."
            )
        im.save(file_path, "PNG")
    except Exception:
        # A failed write of the upload or of the converted picture stays
        # a server failure and keeps its 500. But no path leaves a
        # temporary file behind.
        fs.rm_file(file_path)
        raise
    return file_path


def convert_jpg_to_png(file_source_path):
    """
    Convert the .jpg file at the given path into a sRGB .png file with
    the same name. Remove the source file and return the new path (a
    Path).
    """
    file_target_path = Path(file_source_path).with_suffix(".png")

    im = to_srgb(Image.open(file_source_path))
    im.save(file_target_path, "PNG")
    fs.rm_file(file_source_path)
    return file_target_path


def get_file_name(instance_id):
    """
    Build the thumbnail file name for the given ID.
    """
    return f"{instance_id}.png"


def get_full_size_from_width(im, width):
    """
    Return (width, height), with the height that keeps the picture ratio.
    """
    im_width, im_height = im.size
    ratio = float(im_height) / float(im_width)
    height = int(math.ceil(width * ratio))
    return (width, height)


def make_im_bigger_if_needed(im, size):
    """
    Enlarge a picture smaller than the target box to the box, and keep
    its ratio.

    A direct resize to the target size stretches the picture: a 300x100
    logo would come back square. Thus scale by the smaller of the two
    factors, so that the result fits in the box and fit_to_target_size
    has nothing to make shorter.
    """
    im_width, im_height = im.size
    width, height = size
    if im_width < width and im_height < height:
        ratio = min(width / im_width, height / im_height)
        im = im.resize(
            (
                max(1, round(im_width * ratio)),
                max(1, round(im_height * ratio)),
            ),
            Image.Resampling.LANCZOS,
        )
    return im


def fit_to_target_size(im, size):
    """
    Make sure that the image fits in the given size (make the width, the
    height or both shorter, in proportion to the expected ratio).
    """
    im_width, im_height = im.size
    width, height = size
    w = width
    h = height
    original_ratio = float(im_width) / float(im_height)
    target_ratio = float(width) / float(height)
    if target_ratio != original_ratio:
        w = math.ceil(height * original_ratio)
        if w > width:
            w = width
            h = int(math.ceil(float(width) / original_ratio))
        if (w, h) != (im_width, im_height):
            im = im.resize((w, h), Image.Resampling.LANCZOS)
    return im


def get_dimensions(file_path):
    """
    Return the dimensions of the given picture (width and height).
    """
    im = Image.open(file_path)
    return im.size


def turn_into_thumbnail(file_path, size=None):
    """
    Turn the given picture into a thumbnail of exactly `size`, in place.
    The thumbnail is a sRGB RGBA PNG, with the picture fitted in the box
    and centred on a transparent background. If the height is 0, it
    follows the picture ratio. If there is no size, the thumbnail keeps
    the picture size. Return file_path.
    """
    im = to_srgb(Image.open(file_path), "RGBA")

    if size is not None:
        width, height = size
        if height == 0:
            size = get_full_size_from_width(im, width)
    else:
        size = im.size

    im = make_im_bigger_if_needed(im, size)
    im = fit_to_target_size(im, size)

    im.thumbnail(size, Image.Resampling.LANCZOS)
    final = Image.new("RGBA", size, (0, 0, 0, 0))
    final.paste(
        im, (int((size[0] - im.size[0]) / 2), int((size[1] - im.size[1]) / 2))
    )
    final.save(file_path, "PNG")
    return file_path


def resize(file_path, size, crop=False):
    """
    Resize the given picture to `size`, in place, as a sRGB PNG. If
    `crop` is set, first crop the picture to the target ratio, and do not
    stretch it.
    """
    im = to_srgb(Image.open(file_path))
    if crop:
        im = prepare_image_for_thumbnail(im, size)
    im = im.resize(size, Image.Resampling.LANCZOS)
    im.save(file_path, "PNG")
    return file_path


def prepare_image_for_thumbnail(im, size):
    """
    Crop the image to prevent a deformation in the target thumbnail.
    """
    im_width, im_height = im.size
    width, height = size
    original_ratio = float(im_width) / float(im_height)
    target_ratio = float(width) / float(height)
    if target_ratio > original_ratio:
        # The image is too tall: remove some of the top and bottom
        scale_factor = float(target_ratio) / float(original_ratio)
        crop_width = im_width
        crop_height = math.floor(float(im_height) / scale_factor)
        top_cut_line = (im_height - crop_height) / 2
        im = im.crop(
            flat(0, top_cut_line, crop_width, top_cut_line + crop_height)
        )
    else:
        # The image is too wide: remove some of the sides
        scale_factor = float(original_ratio) / float(target_ratio)
        crop_width = math.ceil(float(im_width) / scale_factor)
        crop_height = im_height
        side_cut_line = int(float(im_width - crop_width) / 2)
        im = im.crop(
            flat(side_cut_line, 0, side_cut_line + crop_width, crop_height)
        )
    return im


def generate_preview_variants(original_path, instance_id):
    """
    Generate three thumbnails for the given picture path, next to it.
    Return a list of (picture type, path) tuples.

    1. Rectangle thumbnail
    2. Square thumbnail
    3. Preview (1200 pixels wide)
    """
    file_name = get_file_name(instance_id)
    variants = [
        ("thumbnails", RECTANGLE_SIZE),
        ("thumbnails-square", SQUARE_SIZE),
        ("previews", PREVIEW_SIZE),
    ]

    result = []
    # The paths come from the original path, which has its own unique
    # suffix. Two concurrent generations for the same preview (a double
    # click on "set as thumbnail", a CLI pass during an upload) must not
    # write and remove the files of each other.
    folder_path = os.path.dirname(original_path)
    original_name = os.path.basename(original_path)
    for picture_data in variants:
        picture_type, size = picture_data
        picture_path = os.path.join(
            folder_path, f"{picture_type}-{original_name}"
        )
        shutil.copyfile(original_path, picture_path)
        turn_into_thumbnail(picture_path, size)
        result.append((picture_type, picture_path))
    return result


def url_path(data_type, instance_id):
    """
    Build the thumbnail download path for the given data type and
    instance ID.
    """
    data_type = data_type.replace("_", "-")
    return f"pictures/thumbnails/{data_type}/{instance_id}.png"


def flat(*nums):
    """
    Turn the given numbers into a tuple of rounded ints.
    """
    return tuple(int(round(n)) for n in nums)


def turn_hdr_into_thumbnail(original_path, size=BIG_RECTANGLE_SIZE):
    """
    Turn an HDR file into a thumbnail.
    """
    import cv2
    import numpy

    file_target_path = Path(original_path).with_suffix(".png")
    hdr = cv2.imread(original_path, flags=cv2.IMREAD_ANYDEPTH)
    # Clamp the values to a 0-1 range for the tone-mapping
    ldr = numpy.clip(hdr, 0, 1)
    # Color space conversion
    ldr = ldr ** (1 / 2.2)
    # Remap to 0-255 for the bit-depth conversion
    ldr = 255.0 * ldr
    cv2.imwrite(str(file_target_path), ldr)
    turn_into_thumbnail(file_target_path, size)
    return file_target_path
