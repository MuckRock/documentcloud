#!/bin/bash

set -e

CODE_DIR=awsbin/sidekick

# Clear the code directory if it already exists
[ -d "$CODE_DIR" ] && rm -Rf $CODE_DIR
# Make the code directory if it does not exist
[ -d "$CODE_DIR" ] || mkdir -p $CODE_DIR

# Copy the code from the Django app
cp -Lr ../../../documentcloud/documents/processing/sidekick/* $CODE_DIR 2>/dev/null || :

# Set AWS requirements
cp sidekick-requirements.txt $CODE_DIR/cloud-requirements.txt
