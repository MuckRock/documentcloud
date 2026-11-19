# Lambda processing requirements

Pinned Python dependencies for the AWS Lambda processing functions, compiled with pip-tools. These are separate from the Django requirements in `requirements/` and are never compiled by `inv pip-compile`.

## Tiers

| File | Adds | Used by |
|---|---|---|
| `processing.in` | Shared packages (boto3, aioboto3, redis, sentry-sdk, etc.) | utils, document_conversion |
| `pdf.in` | Pillow, pymupdf | ocr |
| `info_and_image.in` | pdfplumber, pikepdf, listcrunch | info_and_image |

Each lower tier has `-r` on the one above it, to include its packages, and `-c` on its compiled `.txt`, so shared packages stay on the same version in every lambda. The compiled `.txt` files pin every package, dependencies included.

Each `build_*.sh` script in `config/aws/lambda/` copies its compiled file to `$CODE_DIR/requirements.txt`, which is what `sam build` installs.

## Updating dependencies

```
inv pip-compile-lambdas                              # compile without changing existing pins
inv pip-compile-lambdas --package pillow==13.0.0     # bump one package in every tier
inv pip-compile-lambdas --upgrade                    # upgrade everything
```

Commit the `.in` and `.txt` files together.

## Adding a package

- Needed by every lambda: add it to `processing.in`
- Needed by ocr and info_and_image: add it to `pdf.in`
- Needed by info_and_image only: add it to `info_and_image.in`

## Adding a lambda with its own extras

1. Create `<name>.in` with `-c <parent>.txt` and `-r <parent>.in`, followed by the extra packages
2. Add `pip-compile config/aws/lambda/requirements/<name>.in` to the `pip-compile-lambdas` task, after its parent tier
3. Point the lambda's build script at `requirements/<name>.txt`

## Things to know

- `aioboto3` is in `processing.in`, even though only info_and_image uses it, so that boto3, botocore and aiobotocore are always resolved together. aiobotocore caps botocore, so boto3 upgrades may have to wait for an aioboto3 release.
- The Lambda runtime and the Django container both run Python 3.12. If the Lambda runtime changes, compile with the matching Python version.
- Lambda limits a function to 250 MB unzipped. info_and_image and document_conversion (which includes the LibreOffice archive) are the largest, so check their size after big upgrades: run `sam build`, then `du -sh .aws-sam/build/*/`.
- `config/aws/lambda/libreoffice/lo.tar.gz` is stored in Git LFS. Run `git lfs pull` before deploying, or document_conversion fails with "not a gzip file".
