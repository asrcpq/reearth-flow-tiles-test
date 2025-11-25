#!/usr/bin/env python3
import json
import os, sys, shutil
import subprocess
from datetime import datetime
from pathlib import Path
import yaml

def resolve_workflow_to_json(workflow_path):
	result = subprocess.run(['yaml-include', str(workflow_path)], capture_output=True, text=True, check=True)
	return json.dumps(yaml.safe_load(result.stdout), indent=2)

def prepare_environment(workflow_path, citygml_path, data_dir, output_dir):
	env = os.environ.copy()
	print(citygml_path)
	if citygml_path.suffix == ".gml":
		print("Adding default codelists/schemas to environment")
		# add default codelists/schemas
		env["FLOW_VAR_codelists"] = citygml_path.parent.parent.parent / "codelists"
		env["FLOW_VAR_schemas"] = citygml_path.parent.parent.parent / "schemas"
	env['FLOW_EXAMPLE_TARGET_WORKFLOW'] = str(workflow_path)
	env['FLOW_VAR_cityGmlPath'] = str(citygml_path)
	env['FLOW_VAR_workerArtifactPath'] = str(output_dir)
	runtime_dir = data_dir / "runtime"
	try:
		shutil.rmtree(runtime_dir)
	except FileNotFoundError:
		pass
	env['FLOW_RUNTIME_WORKING_DIRECTORY'] = str(runtime_dir)
	return env, runtime_dir

def filter_coordinates(obj):
	"""
	Recursively filter coordinate lists from objects and replace them with (N coordinates) string.
	This reduces the size of edge data for HTML rendering.
	"""
	if isinstance(obj, dict):
		filtered = {}
		for key, value in obj.items():
			if key in ['exterior', 'interior', 'pos'] and isinstance(value, list):
				# Check if it's a coordinate list (list of objects with x, y, z keys)
				if value and isinstance(value, list) and (
					(isinstance(value[0], dict) and 'x' in value[0] and 'y' in value[0]) or
					isinstance(value[0], (int, float))
				):
					filtered[key] = f"({len(value)} coordinates)"
				else:
					filtered[key] = filter_coordinates(value)
			else:
				filtered[key] = filter_coordinates(value)
		return filtered
	elif isinstance(obj, list):
		return [filter_coordinates(item) for item in obj]
	else:
		return obj

def collect_edge_data(runtime_dir, html_dir):
	if not runtime_dir.exists():
		return {}
	jobs_dir = runtime_dir / 'projects' / 'engine' / 'jobs'
	if not jobs_dir.exists():
		return {}
	edge_data = {}
	for job_dir in jobs_dir.iterdir():
		if not job_dir.is_dir():
			continue
		feature_store = job_dir / 'feature-store'
		if not feature_store.exists():
			continue
		for jsonl_file in feature_store.glob('*.jsonl'):
			parts = jsonl_file.stem.split('.')
			edge_id = parts[-1] if len(parts) > 1 else parts[0]
			try:
				with open(jsonl_file, 'r') as f:
					first_line = f.readline()
					count = 1
					for _ in f:
						count += 1
					if count > 0 and first_line:
						sample = json.loads(first_line)
						# Filter coordinates from sample to reduce size
						sample = filter_coordinates(sample)
						attributes = sample.get('attributes', {})
						# Make path relative to the HTML file location
						rel_path = jsonl_file.relative_to(html_dir)
						edge_data[edge_id] = {
							'count': count,
							'file_path': str(rel_path),
							'sample_attributes': list(attributes.keys())[:10],
							'sample': sample
						}
			except (json.JSONDecodeError, IndexError):
				continue
	return edge_data

def generate_html_report(workflow_path, citygml_path, data_dir, output_dir, timestamp, edge_data):
	template_path = Path(__file__).parent / 'workflow_template.html'
	html = open(template_path).read()

	workflow_json = resolve_workflow_to_json(workflow_path)
	open(data_dir / 'workflow.json', 'w').write(workflow_json)

	variables_display = f"cityGmlPath: {citygml_path}<br>outputPath: {output_dir}"
	html = html.replace('{{TIMESTAMP}}', timestamp)
	html = html.replace('{{WORKFLOW_PATH}}', str(workflow_path))
	html = html.replace('{{WORKING_DIR}}', str(data_dir / "runtime"))
	html = html.replace('{{VARIABLES}}', variables_display)
	html = html.replace('{{WORKFLOW_JSON}}', workflow_json.replace('\\', '\\\\').replace('`', '\\`'))
	html = html.replace('{{EDGE_DATA}}', json.dumps(edge_data).replace('\\', '\\\\').replace('`', '\\`'))

	open(data_dir / 'workflow.html', 'w').write(html)
	print(f"HTML report: {(data_dir / 'workflow.html').absolute()}")

def run_workflow(citygml_path, workflow_path, reearth_dir, data_dir, output_dir):
	timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	subprocess.run(['rm', '-rf', str(output_dir)], check=False)
	output_dir.mkdir(parents=True, exist_ok=True)
	env, runtime_dir = prepare_environment(workflow_path, citygml_path, data_dir, output_dir)
	subprocess.run(['cargo', 'run', '--example', 'example_main'], cwd=reearth_dir / "engine", env=env, check=True)
	edge_data = collect_edge_data(runtime_dir, data_dir)
	generate_html_report(workflow_path, citygml_path, data_dir, output_dir, timestamp, edge_data)
	print("Workflow execution completed successfully")

if __name__ == "__main__":
	citygml_path = Path(sys.argv[1])
	workflow_path = Path(sys.argv[2])
	reearth_dir = Path(sys.argv[3])
	data_dir = Path(sys.argv[4])
	output_dir = Path(sys.argv[5])
	run_workflow(citygml_path, workflow_path, reearth_dir, data_dir, output_dir)
