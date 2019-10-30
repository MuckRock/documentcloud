# Deploying

```bash
gcloud functions deploy run_tesseract_001 --runtime python37 --trigger-topic page-image-extracted --memory=2048MB --timeout 540
gcloud functions deploy run_tesseract2 --runtime python37 --trigger-topic page-image-extracted --memory=2048MB --timeout 540
gcloud functions deploy run_tesseract3 --runtime python37 --trigger-topic page-image-extracted --memory=2048MB --timeout 540
gcloud functions deploy run_tesseract4 --runtime python37 --trigger-topic page-image-extracted --memory=2048MB --timeout 540
```

Run the function with a file name

```bash
FN=$(python -c "import json; import base64; print(base64.b64encode(json.dumps({'paths': ['mueller/275.gif']}).encode('utf-8')).decode('utf-8'))"); time gcloud functions call run_tesseract --data "{\"data\": \"$FN\"}"
FN=$(python -c "import json; import base64; print(base64.b64encode(json.dumps({'paths': ['mueller/275.gif']}).encode('utf-8')).decode('utf-8'))"); time gcloud functions call run_tesseract2 --data "{\"data\": \"$FN\"}"
FN=$(python -c "import json; import base64; print(base64.b64encode(json.dumps({'paths': ['mueller/275.gif']}).encode('utf-8')).decode('utf-8'))"); time gcloud functions call run_tesseract3 --data "{\"data\": \"$FN\"}"
FN=$(python -c "import json; import base64; print(base64.b64encode(json.dumps({'paths': ['mueller/275.gif']}).encode('utf-8')).decode('utf-8'))"); time gcloud functions call run_tesseract4 --data "{\"data\": \"$FN\"}"
```

```bash
FN=$(python -c "import json; import base64; print(base64.b64encode(json.dumps({'paths': ['mueller-test4/97.gif'], 'queue': 'ocr-queue-001'}).encode('utf-8')).decode('utf-8'))"); time gcloud functions call run_tesseract_001 --data "{\"data\": \"$FN\"}"
```

```bash
gcloud logging read 'resource.type="cloud_function" resource.labels.region="us-central1" "OVERALL_TIME" timestamp>="2019-04-26T17:55:54.907Z"' --limit 280000 --format json > logs_100m_2.json
```

```bash
time=0; while :; do echo $(echo "scale=1;$time/2"|bc -l); time=$((time+1)); sleep 30s & gsutil du gs://documentcloud-upload/100muellers | sed 's/.*\.//' | sort | uniq -c; wait; done
```
