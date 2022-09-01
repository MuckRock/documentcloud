# Standard Library
import re
from typing import Optional

# Third Party
import Levenshtein
from unidecode import unidecode

# Local
from .report_generator import ReportGenerator


def same_text(
    test_text: str,
    expected_text: str,
    report_generator: Optional[ReportGenerator] = None,
    ignore_whitespace: bool = True,
    threshold: float = 0.95,
) -> bool:
    """Returns whether two specified text strings have mostly the same content.

    Uses the Levenshtein distance to align and compare two passages of text. The
    reported similarity score is based on the Levenshtein distance divided by the
    maximum length of the input texts. Anything above a certain threshold is reported as
    having the same content.

    Arguments:
        test_text {str} -- The first string.
        expected_text {str} -- The expected content.

    Keyword Arguments:
        report_generator {Optional[ReportGenerator]} -- An HTML test output report
            generator. If one is specified, results from the text comparison task are
            outputted in the report, allowing the user to visualize the internal
            process. (default: {None})
        ignore_whitespace {bool} -- If true, treats any run of whitespace as a single
            space character across both texts to make the comparison
            whitespace-invariant. (default: {True})
        threshold {float} -- The Levenshtein similarity quotient threshold. Anything at
            or above this treshhold will be considered similar. (default: {0.95})

    Returns:
        bool -- Whether the two texts are identical enough (True) or not (False).
    """

    if ignore_whitespace:
        # Replace whitespace if specified.
        test_text = unidecode(re.sub(r"\s+", " ", test_text).strip())
        expected_text = unidecode(re.sub(r"\s+", " ", expected_text).strip())

    # Calculate the Levenshtein distance and similarity quotient.
    distance = Levenshtein.distance(test_text, expected_text)
    similarity = 1 - float(distance) / float(max(len(test_text), len(expected_text)))

    # The test passes if above the specified threshold.
    passes = similarity >= threshold

    if report_generator is not None:
        # Show the test and expected texts along with similarity metrics.
        report_generator.add_bold("Test text")
        report_generator.add_text(test_text)
        report_generator.add_bold("Expected text")
        report_generator.add_text(expected_text)
        report_generator.add_bold("Distances")
        report_generator.add_text(f"Levenshtein distance: {distance}")
        report_generator.add_text(
            f"Similarity score: {similarity:0.4f}",
            "color: green;" if passes else "font-weight: bold; color: red;",
        )

    return passes
