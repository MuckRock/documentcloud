#!/usr/bin/env python
# Standard Library
import re

non_word_pattern = re.compile(r"\W+")

file_ = open("./languages.tsv")
next(file_)  # skip headers

for line in file_:
    iso, ocr_code, name = line.strip().split("\t", 2)
    attr_name = non_word_pattern.sub("_", name.lower())
    print(
        '    {} = ChoiceItem("{}", _("{}"), ocr_code="{}")'.format(
            attr_name, iso, name, ocr_code
        )
    )
