# Updating functions

## process_pdf

A pipeline that kicks off when a PDF file is first uploaded

```bash
gcloud functions deploy process_pdf --runtime python37 --trigger-resource documentcloud-upload --trigger-event google.storage.object.finalize --memory=2048MB --timeout 540 --retry
```

## extract_image

A pipeline to go from a PDF file and page number to a page image (.gif)

```bash
# gcloud functions deploy extract_image --runtime python37 --trigger-http
gcloud functions deploy extract_image --runtime python37 --trigger-topic page-image-ready-for-extraction --memory=2048MB --timeout 540 --retry
```
