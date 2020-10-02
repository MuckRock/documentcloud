#!/bin/bash

set -e

# Run info_and_image build script
./build_info_and_image.sh

# Get all language bundles
languages=$(cat language_bundles.txt)
# Run ocr build script for each language bundle
for lang in $languages
do
    ./build_ocr.sh $(echo $lang | tr '|' ' ')
done

# Run document conversion build script
./build_document_conversion.sh

# Run utils build script
./build_utils.sh
