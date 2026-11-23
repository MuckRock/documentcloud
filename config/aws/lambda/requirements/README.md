# Lambda processing requirements

Pinned Python dependencies for the AWS Lambda processing functions, compiled with pip-tools. These are separate from the Django requirements in `requirements/` and are never compiled by `inv pip-compile`.

## Tiers

| File | Adds | Used by |
|---|---|---|
| `processing.in` | Shared packages (boto3, redis, sentry-sdk, etc.) | utils, document_conversion |
| `pdf.in` | Pillow, pymupdf | ocr |
| `info_and_image.in` | aioboto3, pdfplumber, pikepdf, listcrunch | info_and_image |
| `all.in` | Nothing. This includes every tier | Never deployed |

Each tier has `-r` on the tier it builds on, to include its packages. `all.in` includes every tier and is compiled first, so `all.txt` resolves every package together. Each tier then has `-c all.txt`, which only restricts versions and never installs anything, so shared packages get the same version in every lambda.

Each `build_*.sh` script in `config/aws/lambda/` copies its compiled file to `$CODE_DIR/requirements.txt`, which is what `sam build` installs.

## Updating dependencies

```
inv pip-compile-lambdas                              # compile without changing existing pins
inv pip-compile-lambdas --package pillow==13.0.0     # bump one package in every tier
inv pip-compile-lambdas --upgrade                    # upgrade everything
```

The flag applies to `all.in`. The tiers are always compiled with `--upgrade`, so they follow whatever `all.txt` pins.

Commit the `.in` and `.txt` files together.

## Adding a package

- Needed by every lambda: add it to `processing.in`
- Needed by ocr and info_and_image: add it to `pdf.in`
- Needed by info_and_image only: add it to `info_and_image.in`
- Needed by a new lambda: see next section. 

## Adding a lambda with its own extras

1. Create `<name>.in` with `-c all.txt` and `-r <parent>.in`, followed by the extra packages
2. Add `-r <name>.in` to `all.in`
3. Add `pip-compile --upgrade config/aws/lambda/requirements/<name>.in` to the `pip-compile-lambdas` task, after `all.in`
4. Point the lambda's build script at `requirements/<name>.txt`

If you skip step 2, the new tier's extras and their dependencies aren't covered by the shared resolve and can pin different versions from the other tiers.

## Things to know

- `all.txt` is only for resolving versions. No lambda installs it.
- boto3, botocore, s3transfer, aioboto3 and aiobotocore should be upgraded together for a more predictable dependency resolution.
- The Lambda runtime and the Django container both run Python 3.12. If the Lambda runtime changes, compile with the matching Python version.
- Lambda limits a function to 250 MB unzipped. info_and_image and document_conversion (which includes the LibreOffice archive) are the largest, so check their size after big upgrades: run `sam build`, then `du -sh .aws-sam/build/*/`.
- `config/aws/lambda/libreoffice/lo.tar.gz` is stored in Git LFS. Run `git lfs pull` before deploying, or document_conversion fails with "not a gzip file".
