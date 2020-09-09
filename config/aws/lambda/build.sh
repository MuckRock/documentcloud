#!/bin/bash

set -e

# Run info_and_image build script
./build_info_and_image.sh

# Get all languages
languages=($(DJANGO_SETTINGS_MODULE=config.settings.local python -c "from django.core.wsgi import get_wsgi_application;application = get_wsgi_application();from documentcloud.core.choices import Language;print(*[Language.ocr_name(x[0]) for x in Language.choices])"))
# Run ocr build script for each language
for lang in $languages
do
    ./build_ocr.sh $lang
done

# Run utils build script
./build_utils.sh
