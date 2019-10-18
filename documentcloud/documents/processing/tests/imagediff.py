"""Functions to evaluate whether two images are perceptually identical.

Uses a cross-correlation method with Gaussian blur noise-reduction to evaluate the
alignment similarity of image files. This similarity method should be robust to
equating the same images at different resolutions, while finding images with minor
alterations (e.g. a small red square placed somewhere within) not similar.
"""
# Standard Library
import os
import tempfile
from typing import Optional

# Third Party
import cv2
import numpy as np

# Local
from .report_generator import ReportGenerator


def same_images(
    test_image: str,
    expected_image: str,
    report_generator: Optional[ReportGenerator] = None,
    resize_width: int = 600,
    blur_amount: int = 5,
    median_blur_amount: int = 7,
    threshold: int = 0,
) -> bool:
    """Returns whether the two specified images have identical contents.

    Returns whether two specified images are identical. The matching algorithm looks for
    perfectly aligned images without significant blemishes while accommodating for
    slight text rendering or resizing differences.

    Borrows techniques from:
      https://docs.opencv.org/3.4.0/d7/d4d/tutorial_py_thresholding.html
    
    Arguments:
      test_image {str} -- The file name of the first image.
      expected_image {str} -- The file name of the second image.
    
    Keyword Arguments:
      report_generator {Optional[ReportGenerator]} -- An HTML test output report
          generator. If one is specified, results from the image comparison task are
          outputted in the report, allowing the user to visualize the internal process.
          (default: {None})
      resize_width {int} -- The width to resize both images to. The resizing is done in
          equal proportions. This function will fail if images are different aspect
          ratios. (default: {1200})
      blur_amount {int} -- The number of pixels of Gaussian blur to apply to the image
          precomparison. This has the effect of reducing overall noise that could cause
          alignment issues. (default: {10})
      median_blur_amount {int} -- The number of pixels of median blur to apply to the
          difference image.
      threshold {int} -- The number of differing pixels that are acceptable to consider
          two images matching. (default: {0})
    
    Returns:
      bool -- Whether the two images are identical (True) or not (False)
    """
    # Read the images from file names.
    im1 = cv2.imread(test_image)
    im2 = cv2.imread(expected_image)

    # Obtain the desired resize dimensions based off the expectation image.
    resize_dimensions = (
        resize_width,
        int(round(float(im2.shape[0]) / (float(im2.shape[1]) / resize_width))),
    )

    # Resize both images.
    im1 = cv2.resize(im1, resize_dimensions)
    im2 = cv2.resize(im2, resize_dimensions)

    # Convert images to grayscale.
    im1 = cv2.cvtColor(im1, cv2.COLOR_BGR2GRAY)
    im2 = cv2.cvtColor(im2, cv2.COLOR_BGR2GRAY)

    # Blur images.
    im1 = cv2.blur(im1, (blur_amount, blur_amount))
    im2 = cv2.blur(im2, (blur_amount, blur_amount))

    # Apply Otsu thresholding.
    _, im1 = cv2.threshold(im1, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, im2 = cv2.threshold(im2, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Median blur the difference between the two images.
    full = cv2.medianBlur(im1 - im2, median_blur_amount)

    # Quantify difference as number of pixels that don't match a color threshold.
    diff_pix = np.sum(full > 50)

    # The method passes if the number of differing pixels is less than a threshold
    # quantity.
    passes = diff_pix <= threshold

    if report_generator is not None:
        report_generator.add_images(
            [test_image, expected_image],
            ["Test image", f"Expected image: {os.path.split(expected_image)[-1]}"],
        )

        # Show the processed images.
        with tempfile.NamedTemporaryFile(suffix=".png") as f1:
            with tempfile.NamedTemporaryFile(suffix=".png") as f2:
                # Show the difference image.
                with tempfile.NamedTemporaryFile(suffix=".png") as f3:
                    cv2.imwrite(f1.name, im1)
                    cv2.imwrite(f2.name, im2)
                    cv2.imwrite(f3.name, full)

                    report_generator.add_images(
                        [f1.name, f2.name, f3.name],
                        [
                            "Processed test image",
                            "Processed expected image",
                            "Difference",
                        ],
                    )

        report_generator.add_text(
            "Difference pixels: %d (%d or fewer desired)" % (diff_pix, threshold),
            "color: green;" if passes else "font-weight: bold; color: red;",
        )
        report_generator.add_horizontal_rule()

    return passes
