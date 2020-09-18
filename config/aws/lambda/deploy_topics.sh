#!/bin/bash

# Deploy all the AWS topics needed. This should only have to be run once.

set -e

# Get all language bundles
languages=$(cat language_bundles.txt)
envs="staging prod"

for env in $envs
do
  for lang in $languages
  do
      topic=$(echo $lang | tr "|" "-")
      aws sns create-topic --name "ocr-${topic}-extraction-${env}"
  done
done
