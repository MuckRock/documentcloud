"""
A script to come up with groupings of Tesseract language data files that fit
within AWS lambda's size limits. The script takes into account important
languages, which can be separated.

Make sure you've downloaded all the Tesseract data files first.
"""

import random
import os

directory = "../../../documentcloud/documents/processing/ocr/tesseract/tessdata"
size_limit = 76 * 1024 * 1024  # megabytes


def run_all():
    # Languages that end up in their own function
    vip_languages = [
        "eng",
        "spa",
        # "nld",
        # "ita",
        # "ukr",
        # "rus",
        # "kor",
        # "deu",
        # "por",
        # "fra",
        # "dan",
        # "ara",
        # "ron",
        # "zho",
    ]

    tessdata = os.listdir(directory)
    language_sizes = []
    bundles = []
    current_bundle = []
    current_bundle_size = 0
    for language in tessdata:
        name = language.split(".")[0]
        size = os.stat(os.path.join(directory, language)).st_size
        if name in vip_languages:
            bundles.append([name])
        else:
            language_sizes.append((name, size))

    # Run a random process of adding things until nothing else can be added
    num_iterations = 1000
    iterations = num_iterations  # Try this many iterations before giving up

    while language_sizes:
        idx = random.randrange(0, len(language_sizes))
        name, size = language_sizes[idx]
        if current_bundle_size + size < size_limit:
            current_bundle.append(name)
            current_bundle_size += size
            del language_sizes[idx]
            iterations = num_iterations
        else:
            iterations -= 1
            if iterations <= 0:
                bundles.append(current_bundle)
                current_bundle = []
                current_bundle_size = 0
                iterations = num_iterations

    if current_bundle:
        bundles.append(current_bundle)

    result = " ".join(["|".join(bundle) for bundle in bundles])
    return (result, len(bundles))


min_result = None
for i in range(1000):
    result, size = run_all()
    if min_result is None or size < min_result[1]:
        min_result = (result, size)
    if i % 100 == 0:
        print(i, min_result[1])

print(min_result[0])
print(min_result[1])
