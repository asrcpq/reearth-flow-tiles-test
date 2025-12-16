#!/usr/bin/env python3
import json, sys, os
from pathlib import Path
from subprocess import run

def simplify_json(obj, max_items=5):
	"""Recursively simplify JSON by limiting list sizes to prevent HTML explosion"""
	if isinstance(obj, list):
		if len(obj) <= max_items:
			return [simplify_json(item, max_items) for item in obj]
		else:
			simplified = [simplify_json(item, max_items) for item in obj[:max_items]]
			simplified.append(f"... and {len(obj) - max_items} more items")
			return simplified
	elif isinstance(obj, dict):
		return {k: simplify_json(v, max_items) for k, v in obj.items()}
	else:
		return obj

def collect_edge_data(job_dir):
	edge_data = {}
	feature_store = job_dir / "feature-store"
	for jsonl_file in feature_store.glob("*.jsonl"):
		parts = jsonl_file.stem.split(".")
		edge_id = parts[-1] if len(parts) > 1 else parts[0]
		features = []
		with open(jsonl_file, "r") as f:
			for line in f:
				line = line.strip()
				if line:
					feature = json.loads(line)
					feature = simplify_json(feature)
					features.append(feature)
		if features:
			edge_data[edge_id] = {
				"count": len(features),
				"features": features
			}
	return edge_data

def generate_html_report(output_dir):
	template_path = Path(__file__).parent / "workflow_template.html"
	with open(template_path) as f:
		html = f.read()
	with open(output_dir / "workflow.json") as f:
		workflow_json = f.read()
	html = html.replace("{{WORKFLOW_JSON}}", workflow_json.replace("\\", "\\\\").replace("`", "\\`"))
	edge_data = collect_edge_data(output_dir / "runtime")
	html = html.replace("{{EDGE_DATA}}", json.dumps(edge_data).replace("\\", "\\\\").replace("`", "\\`"))

	with open(output_dir / "workflow.html", "w") as f:
		f.write(html)

	mvt_dirs = sorted({f.parent.parent.parent.relative_to(output_dir) for f in output_dir.rglob("*.mvt")})
	if mvt_dirs:
		tiles = [str(d / "{z}" / "{x}" / "{y}.mvt") for d in mvt_dirs]
		html = open(Path(__file__).parent / "mvt-viewer.html").read().replace("{{TILES_LIST}}", json.dumps(tiles))
		(output_dir / "mvt-viewer.html").write_text(html)

	# Generate Cesium viewer if tileset.json exists
	tilesets = list(output_dir.rglob("tileset.json"))
	if tilesets:
		tiles = [str(f.relative_to(output_dir)) for f in tilesets]
		html = open(Path(__file__).parent / "cesium.html").read().replace("{{TILES_LIST}}", json.dumps(tiles))
		(output_dir / "cesium-viewer.html").write_text(html)

	return output_dir / "workflow.html"

if __name__ == "__main__":
	html_path = generate_html_report(Path(sys.argv[1]).resolve())
	run(["open", "http://localhost:8080/" + str(html_path.relative_to(os.getenv("HOME")))])
