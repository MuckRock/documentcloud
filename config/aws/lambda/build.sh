#!/bin/bash

set -e

# Run info_and_image build script
./build_info_and_image.sh

# Run ocr build script
./build_ocr.sh

# Run utils build script
./build_utils.sh
