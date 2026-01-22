#!/usr/bin/env python3
import subprocess
import urllib.request
import os, sys, time
import re
import json, yaml
import shutil
from pathlib import Path

GCP_COMMAND = '/bin/sh -c reearth-flow-worker --workflow "https://api.flow.plateau.reearth.io/workflows/01keearb3rqggv2qektb7nphwm.yml" --metadata-path "https://api.flow.plateau.reearth.io/metadata/metadata-1051851c-1efd-4334-adcd-9f683cee9821.json" --var=codelists=https://assets.cms.plateau.reearth.io/assets/5a/41904c-0786-4a88-bfd3-5d93ba6065c5/22203_numazu-shi_city_2023_citygml_3_op_codelists.zip --var=objectLists=https://assets.cms.plateau.reearth.io/assets/f6/37bf64-31bd-414d-83aa-a8ea999c6a74/22203_city_2023_objectlist_op.xlsx --var=prcs=6676 --var=schemas=https://assets.cms.plateau.reearth.io/assets/bf/05d34f-5a3a-473e-be11-e65b14334e88/22203_numazu-shi_city_2023_citygml_3_op_schemas.zip --var=targetPackages=[wwy] --var=cityGmlPath=https://assets.cms.plateau.reearth.io/assets/0e/23d627-eb0e-4bd6-88e7-561e029d3404/22203_numazu-shi_city_2023_citygml_3_op_wwy.zip'
output_dir = "/Users/tsq/Desktop/flow1"
job_id = "1051851c-1efd-4334-adcd-9f683cee9821"

def prepare(output_dir):
    """Setup directories and download workflow."""
    # Clear output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    flow_dir = os.path.join(output_dir, "flow")
    runtime_dir = os.path.join(output_dir, "runtime")
    os.makedirs(flow_dir)
    os.makedirs(runtime_dir)

    # Parse workflow URL and download
    workflow_match = re.search(r'--workflow\s+"([^"]+)"', GCP_COMMAND)
    workflow_url = workflow_match.group(1)
    workflow_file = "/tmp/workflow.yml"
    urllib.request.urlretrieve(workflow_url, workflow_file)

    # Save workflow as JSON
    with open(workflow_file, "r") as f:
        workflow_data = yaml.safe_load(f)
    with open(os.path.join(output_dir, "workflow.json"), "w") as f:
        json.dump(workflow_data, f, indent=2)

    return flow_dir, runtime_dir, workflow_file


def env_setup_and_run(flow_dir, runtime_dir, workflow_file):
    """Setup environment variables and run workflow."""
    env = os.environ.copy()

    # Parse variables from command
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


def post_process(runtime_dir, flow_dir):
    """Move outputs to final locations."""
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

    # Cleanup
    shutil.rmtree(runtime_path / "projects")


def local_run():
    flow_dir, runtime_dir, workflow_file = prepare(output_dir)
    env_setup_and_run(flow_dir, runtime_dir, workflow_file)
    post_process(runtime_dir, flow_dir)

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "local":
        local_run()
    elif cmd == "fetch":
        # fetch intermediate data from GCP
        # API: ${apiUrl}/artifacts/${jobId}/feature-store/${edgeId}.jsonl.zst
        # extract apiUrl from GCP_COMMAND
        api_url_match = re.search(r'--workflow\s+"([^"]+)"', GCP_COMMAND)
        api_url = api_url_match.group(1).rsplit('/', 2)[0]
        # extract edges from workflow.json
        with open(os.path.join(output_dir, "workflow.json"), "r") as f:
            workflow_data = json.load(f)

        feature_store_dir = Path(output_dir) / "runtime/feature-store"
        os.makedirs(feature_store_dir, exist_ok=True)

        # build subgraph instance map: subGraphId -> node IDs that instantiate it
        subgraph_instances = {}
        for graph in workflow_data["graphs"]:
            if graph["id"] == workflow_data["entryGraphId"]:
                for node in graph["nodes"]:
                    if node.get("type") == "subGraph":
                        subgraph_id = node["subGraphId"]
                        if subgraph_id not in subgraph_instances:
                            subgraph_instances[subgraph_id] = []
                        subgraph_instances[subgraph_id].append(node["id"])

        # collect edge IDs including subgraph edges (format: instanceNodeId.edgeId)
        edge_ids = []
        for graph in workflow_data["graphs"]:
            graph_id = graph["id"]
            is_entry = graph_id == workflow_data["entryGraphId"]

            for edge in graph["edges"]:
                if is_entry:
                    edge_ids.append(edge["id"])
                else:
                    # subgraph edges: add one per instance
                    for instance_id in subgraph_instances.get(graph_id, []):
                        edge_ids.append(f"{instance_id}.{edge['id']}")

        for i, edge_id in enumerate(edge_ids, 1):
            url = f"{api_url}/artifacts/{job_id}/feature-store/{edge_id}.jsonl.zst"
            output = feature_store_dir / f"{edge_id}.jsonl.zst"
            if output.exists():
                continue
            print(f"[{i}/{len(edge_ids)}] {url}")
            try:
                urllib.request.urlretrieve(url, output)
                print(f"{os.path.getsize(output)} bytes")
            except Exception as e:
                print(e)
            time.sleep(1)
