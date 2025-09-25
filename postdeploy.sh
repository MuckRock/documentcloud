#!/bin/bash
set -e

# Always run migrations
python manage.py migrate --noinput

# Deploy corresponding lambda update depending on which app just deployed
case "$HEROKU_APP_NAME" in
  documentcloud-staging)
    echo "Running staging Lambda update..."
    bash "$(dirname "$0")/config/aws/lambda/codeship_deploy_lambdas.sh" staging-lambda --staging
    ;;
  documentcloud-prod)
    echo "Running production Lambda update..."
    bash "$(dirname "$0")/config/aws/lambda/codeship_deploy_lambdas.sh" prod-lambda
    ;;
  *)
    echo "No matching Lambda update for app: $HEROKU_APP_NAME"
    ;;
esac
