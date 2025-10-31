#!/usr/bin/env python3
import json
import os, sys, shutil
import subprocess
from datetime import datetime
from pathlib import Path

def prepare_environment(workflow_path, citygml_path, data_dir, output_dir):
	env = os.environ.copy()
	env['FLOW_EXAMPLE_TARGET_WORKFLOW'] = str(workflow_path)
	env['FLOW_VAR_cityGmlPath'] = str(citygml_path)
	env['FLOW_VAR_outputPath'] = str(output_dir)
	runtime_dir = data_dir / "runtime"
	try:
		shutil.rmtree(runtime_dir)
	except FileNotFoundError:
		pass
	env['FLOW_RUNTIME_WORKING_DIRECTORY'] = str(runtime_dir)
	return env, runtime_dir

def run_workflow(reearth_dir, workflow_path, env):
	print(f"Running workflow: {workflow_path}")
	p = subprocess.run(['cargo', 'run', '--example', 'example_main'], cwd=reearth_dir / "engine", env=env)
	if p.returncode != 0:
		raise Exception("Workflow run FAILED")
	return p

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
						attributes = sample.get('attributes', {})
						# Make path relative to the HTML file location
						rel_path = jsonl_file.relative_to(html_dir)
						edge_data[edge_id] = {
							'count': count,
							'file_path': str(rel_path),
							'sample_attributes': list(attributes.keys())[:10]
						}
			except (json.JSONDecodeError, IndexError):
				continue
	return edge_data

def generate_html_report(workflow_path, citygml_path, data_dir, output_dir, timestamp, edge_data):
	template_path = Path(__file__).parent / 'workflow_template.html'
	if not template_path.exists():
		print(f"Warning: Template not found at {template_path}, skipping HTML report")
		return
	with open(template_path, 'r') as f:
		html = f.read()
	if workflow_path.exists():
		with open(workflow_path, 'r') as f:
			workflow_yaml = f.read()
	else:
		workflow_yaml = "# Workflow file not found"
	variables_display = f"cityGmlPath: {citygml_path}<br>"
	variables_display += f"outputPath: {output_dir}"
	html = html.replace('{{TIMESTAMP}}', timestamp)
	html = html.replace('{{WORKFLOW_PATH}}', str(workflow_path))
	html = html.replace('{{WORKING_DIR}}', str(data_dir / "runtime"))
	html = html.replace('{{VARIABLES}}', variables_display)
	workflow_yaml_escaped = workflow_yaml.replace('\\', '\\\\').replace('`', '\\`').replace('${', '\\${')
	html = html.replace('{{WORKFLOW_YAML}}', workflow_yaml_escaped)
	edge_metadata_json = json.dumps(edge_data).replace('\\', '\\\\').replace('`', '\\`')
	html = html.replace('{{EDGE_DATA}}', edge_metadata_json)
	output_path = data_dir / 'workflow.html'
	with open(output_path, 'w') as f:
		f.write(html)
	print(f"HTML report: {output_path.absolute()}")

def main(citygml_path, workflow_path, reearth_dir, data_dir, output_dir):
	timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
	subprocess.run(['rm', '-rf', str(output_dir)], check=False)
	output_dir.mkdir(parents=True, exist_ok=True)
	env, runtime_dir = prepare_environment(workflow_path, citygml_path, data_dir, output_dir)
	run_workflow(reearth_dir, workflow_path, env)
	edge_data = collect_edge_data(runtime_dir, data_dir)
	generate_html_report(workflow_path, citygml_path, data_dir, output_dir, timestamp, edge_data)
	print("Workflow execution completed successfully")
