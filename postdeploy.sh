#!/bin/bash
set -e

# Always run migrations
python manage.py migrate --noinput
