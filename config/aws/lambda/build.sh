#!/bin/bash

set -e

# Run info_and_image build script
./build_info_and_image.sh

# Get all languages
languages=$(cat ../../languages/languages.tsv | tail -n +2 | cut -f2 | tr "\n" " ")
# Run ocr build script for each language
for lang in $languages
do
    ./build_ocr.sh $lang
done

# Run utils build script
./build_utils.sh
