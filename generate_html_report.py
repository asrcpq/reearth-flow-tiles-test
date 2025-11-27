#!/usr/bin/env python3
import json, sys
from pathlib import Path
from subprocess import run

def collect_edge_data(jobs_dir):
	if not jobs_dir.exists():
		return {}
	edge_data = {}
	for job_dir in jobs_dir.iterdir():
		if not job_dir.is_dir():
			continue
		feature_store = job_dir / "feature-store"
		if not feature_store.exists():
			continue
		for jsonl_file in feature_store.glob("*.jsonl"):
			parts = jsonl_file.stem.split(".")
			edge_id = parts[-1] if len(parts) > 1 else parts[0]
			features = []
			with open(jsonl_file, "r") as f:
				for line in f:
					line = line.strip()
					if line:
						feature = json.loads(line)
						# to save size
						feature.pop("geometry", None)
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
	jobs_dir = output_dir / "runtime/projects/engine/jobs"
	edge_data = collect_edge_data(jobs_dir)
	html = html.replace("{{EDGE_DATA}}", json.dumps(edge_data).replace("\\", "\\\\").replace("`", "\\`"))

	with open(output_dir / "workflow.html", "w") as f:
		f.write(html)

	# Generate MVT viewer if .pbf files exist
	pbf_dirs = sorted({f.parent.parent.parent.relative_to(output_dir) for f in output_dir.rglob("*.pbf")})
	if pbf_dirs:
		tiles = [str(d / "{z}" / "{x}" / "{y}.pbf") for d in pbf_dirs]
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
	run(["open", "-a", "Safari", str(html_path)])