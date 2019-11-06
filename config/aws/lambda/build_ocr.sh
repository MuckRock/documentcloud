#!/bin/bash

set -e

CODE_DIR=awsbin/ocr

# Clear the code directory if it already exists
[ -d "$CODE_DIR" ] && rm -Rf $CODE_DIR
# Make the code directory if it does not exist
[ -d "$CODE_DIR" ] || mkdir -p $CODE_DIR

# Copy the code from the Django app
cp -Lr ../../../documentcloud/documents/processing/ocr/* $CODE_DIR

# Sub in Amazon Linux compiled Tesseract libraries
rm -r $CODE_DIR/tesseract
cp -r ocr_libraries/ $CODE_DIR/tesseract

# Set AWS requirements
cp cloud-requirements.txt $CODE_DIR/cloud-requirements.txt
