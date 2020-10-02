#!/bin/bash

set -e

CODE_DIR=awsbin/document_conversion

# Clear the code directory if it already exists
[ -d "$CODE_DIR" ] && rm -Rf $CODE_DIR
# Make the code directory if it does not exist
[ -d "$CODE_DIR" ] || mkdir -p $CODE_DIR

# Copy the code from the Django app
cp -Lr ../../../documentcloud/documents/processing/document_conversion/* $CODE_DIR 2>/dev/null || :

# Copy in LibreOffice binary compiled for AWS
cp libreoffice/lo.tar.gz $CODE_DIR/libreoffice/lo.tar.gz

# Set AWS requirements
cp cloud-requirements.txt $CODE_DIR/cloud-requirements.txt
