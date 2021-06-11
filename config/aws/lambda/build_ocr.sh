#!/bin/bash

set -e

CODE_DIR="awsbin/ocr"
OCR_DIRECTORY="../../../documentcloud/documents/processing/ocr"

# Clear the code directory if it already exists
[ -d "$CODE_DIR" ] && rm -Rf $CODE_DIR
# Make the code directory if it does not exist
[ ! -d "$CODE_DIR" ] || mkdir -p $CODE_DIR

# Copy the code from the Django app, excluding tesseract data
rsync -aL "${OCR_DIRECTORY}/" $CODE_DIR --exclude tesseract

# Sub in Amazon Linux compiled Tesseract libraries
[ -f $CODE_DIR/tesseract ] && rm -r $CODE_DIR/tesseract
cp -r ocr_libraries/ $CODE_DIR/tesseract 2>/dev/null || :
mkdir $CODE_DIR/tesseract/tessdata

# Set AWS requirements
cp cloud-requirements.txt $CODE_DIR/cloud-requirements.txt
