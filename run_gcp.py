#!/usr/bin/env python3
import subprocess
import urllib.request
import os
import sys
import re
import json
import yaml
import shutil
from pathlib import Path

GCP_COMMAND = '/bin/sh -c reearth-flow-worker --workflow "https://api.flow.plateau.reearth.io/workflows/01kex8rg2f66g4cbpftkqsmjsg.yml" --metadata-path "https://api.flow.plateau.reearth.io/metadata/metadata-75be09be-40c2-4efa-8967-447cd6153275.json" --var=schemas=01jkyfnk495fp11xek8m56wvdb --var=targetPackages=[frn] --var=cityGmlPath=https://assets.cms.plateau.reearth.io/assets/84/c10058-cb08-44d3-abe9-c78827c786b6/15202_nagaoka-shi_city_2024_citygml_1_op_frn.zip --var=codelists=https://assets.cms.plateau.reearth.io/assets/c9/1f2aad-f305-4b3b-b1c0-6f6751031eaa/15202_nagaoka-shi_city_2024_citygml_1_op_codelists.zip --var=objectLists=https://assets.cms.plateau.reearth.io/assets/bb/861ea3-55de-455c-ba3a-db5ad76fe2cf/15202_city_2024_objectlist_op.xlsx --var=prcs=6676'

# Get output directory from command line
output_dir = sys.argv[1]

# Clear output directory
if os.path.exists(output_dir):
    shutil.rmtree(output_dir)
os.makedirs(output_dir)

flow_dir = os.path.join(output_dir, "flow")
runtime_dir = os.path.join(output_dir, "runtime")
os.makedirs(flow_dir)
os.makedirs(runtime_dir)

# Parse workflow URL
workflow_match = re.search(r'--workflow\s+"([^"]+)"', GCP_COMMAND)
workflow_url = workflow_match.group(1)

# Download workflow
workflow_file = "/tmp/workflow.yml"
urllib.request.urlretrieve(workflow_url, workflow_file)

# Load workflow YAML and save as JSON
with open(workflow_file, "r") as f:
    workflow_data = yaml.safe_load(f)
with open(os.path.join(output_dir, "workflow.json"), "w") as f:
    json.dump(workflow_data, f, indent=2)

# Parse variables and set as FLOW_VAR_* environment variables
env = os.environ.copy()
for match in re.finditer(r'--var=(\w+)=([^\s]+)', GCP_COMMAND):
    var_name = match.group(1)
    var_value = match.group(2)
    env[f"FLOW_VAR_{var_name}"] = var_value

# Set output paths
env["FLOW_VAR_workerArtifactPath"] = flow_dir
env["FLOW_RUNTIME_WORKING_DIRECTORY"] = runtime_dir

# Run CLI
subprocess.run([
    "cargo", "run",
    "--package", "reearth-flow-cli",
    "--", "run",
    "--workflow", workflow_file
], env=env, cwd="/Users/tsq/Projects/reearth-flow/engine")

# Move job directory contents to runtime root and flow_dir
runtime_path = Path(runtime_dir)
projects_dir = runtime_path / "projects" / "engine" / "jobs"
assert projects_dir.exists(), f"Projects directory not found: {projects_dir}"

job_dirs = list(projects_dir.iterdir())
assert len(job_dirs) == 1, f"Expected exactly 1 job directory, found {len(job_dirs)}"

job_dir = job_dirs[0]

# Move artifacts to flow_dir
artifacts_dir = job_dir / "artifacts"
if artifacts_dir.exists():
    for item in artifacts_dir.iterdir():
        shutil.move(str(item), str(Path(flow_dir) / item.name))

# Move other items to runtime root
for item in job_dir.iterdir():
    if item.name != "artifacts":
        shutil.move(str(item), str(runtime_path / item.name))

# Delete projects directory
shutil.rmtree(runtime_path / "projects")
