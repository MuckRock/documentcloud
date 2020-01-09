#!/bin/bash

set -e

# Build and deploy the lambda function
./build.sh && \
sam build && \
sam package --output-template packaged.yaml --s3-bucket cloud-functions-test && \
sam deploy --template-file packaged.yaml --region us-east-1 --capabilities CAPABILITY_IAM --stack-name info-and-image-staging
