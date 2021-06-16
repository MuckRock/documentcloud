#!/bin/bash

# Deploy all the AWS topics needed. This should only have to be run once.

set -e

# Get all language bundles
envs="staging prod"

for env in $envs
do
    topic=$(echo $lang | tr "|" "-")
    aws sns create-topic --name "ocr-extraction-${env}"
done
