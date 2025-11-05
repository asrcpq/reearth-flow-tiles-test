build: generated temporary files
artifacts: referred blobs

runner.py stages:
- g: generate dataset
- f: extract fme output
- r: run workflow
- e: evaluation result