#!/bin/bash

set -e

LANGUAGES=$@
LANGUAGES_FN=$(echo $LANGUAGES | tr ' ' '_')
CODE_DIR="awsbin/ocr_${LANGUAGES_FN}"
OCR_DIRECTORY="../../../documentcloud/documents/processing/ocr"

# Clear the code directory if it already exists
[ -d "$CODE_DIR" ] && rm -Rf $CODE_DIR
# Make the code directory if it does not exist
[ ! -d "$CODE_DIR" ] || mkdir -p $CODE_DIR

# Fetch OCR language if not already present
for LANG in $LANGUAGES
do
    OCR_FILE="${OCR_DIRECTORY}/tesseract/tessdata/${LANG}.traineddata"
    if [ ! -f "$OCR_FILE" ]; then
        mkdir -p "$(dirname $OCR_FILE)"
        TESSDATA_URL="https://github.com/tesseract-ocr/tessdata/raw/4.00/${LANG}.traineddata"
        wget -O "${OCR_FILE}" "${TESSDATA_URL}"
    fi
done

# Copy the code from the Django app, excluding tesseract data
rsync -aL "${OCR_DIRECTORY}/" $CODE_DIR --exclude tesseract

# Sub in Amazon Linux compiled Tesseract libraries
[ -f $CODE_DIR/tesseract ] && rm -r $CODE_DIR/tesseract
cp -r ocr_libraries/ $CODE_DIR/tesseract 2>/dev/null || :
mkdir $CODE_DIR/tesseract/tessdata

# Copy in just the desired tessdata language
for LANG in $LANGUAGES
do
    OCR_FILE="${OCR_DIRECTORY}/tesseract/tessdata/${LANG}.traineddata"
    cp "${OCR_FILE}" "${CODE_DIR}/tesseract/tessdata/${LANG}.traineddata"
done

# Set AWS requirements
cp cloud-requirements.txt $CODE_DIR/cloud-requirements.txt
