#!/bin/bash

set -e

# Run info_and_image build script
./build_info_and_image.sh

# Run ocr build script
./build_ocr.sh

# Run document conversion build script
./build_document_conversion.sh

# Run sidekick build script
./build_sidekick.sh

# Run utils build script
./build_utils.sh
