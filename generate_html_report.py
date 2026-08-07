#!/usr/bin/env python3
import json, sys, os
from pathlib import Path
from subprocess import run

SEARCH_FIELDS = [".attributes.gml_id", ".metadata.featureType", ".attributes.lod"]

def get_by_path(obj, path):
	"""Get value from obj by dot-separated path like '.id' or '.attributes.gml_id'"""
	for key in path.lstrip(".").split("."):
		if isinstance(obj, dict):
			obj = obj.get(key)
		else:
			return None
	return obj

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

def collect_port_index(job_dir, output_dir):
	"""Write simplified features to files and return index."""
	import shutil
	port_index = {}
	feature_store = job_dir / "feature-store"
	simplified_dir = output_dir / "simplified_portdata"
	if simplified_dir.exists():
		shutil.rmtree(simplified_dir)
	files = list(feature_store.glob("*.jsonl"))
	for idx, jsonl_file in enumerate(files):
		print(f"{idx+1}/{len(files)} Processing {jsonl_file.name}...")
		port_id = jsonl_file.stem
		port_dir = simplified_dir / port_id
		port_dir.mkdir(parents=True)
		features = []
		with open(jsonl_file) as f:
			for line_no, line in enumerate(f):
				line = line.strip()
				if not line:
					continue
				feature = json.loads(line)
				# `id` is deprecated as a feature key (and isn't unique: multiple
				# lines, e.g. splitter output, can share one source feature's id).
				# `_idx` (the line number) is the on-disk key instead.
				entry = {"_idx": line_no}
				for field in SEARCH_FIELDS:
					entry[field] = get_by_path(feature, field) or ""
				features.append(entry)
				(port_dir / f"{line_no}.json").write_text(json.dumps(simplify_json(feature)))
		if features:
			port_index[port_id] = {"count": len(features), "features": features}
	return port_index

def generate_html_report(output_dir):
	template_path = Path(__file__).parent / "workflow_template.html"
	with open(template_path) as f:
		html = f.read()
	with open(output_dir / "workflow.json") as f:
		workflow_json = f.read()
	html = html.replace("{{WORKFLOW_JSON}}", workflow_json.replace("\\", "\\\\").replace("`", "\\`"))
	port_index = collect_port_index(output_dir / "runtime", output_dir)
	html = html.replace("{{PORT_INDEX}}", json.dumps(port_index).replace("\\", "\\\\").replace("`", "\\`"))
	with open(output_dir / "workflow.html", "w") as f:
		f.write(html)

def generate(output_dir):
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

	if (output_dir / "workflow.json").exists():
		generate_html_report(output_dir)

	return output_dir / "workflow.html"

if __name__ == "__main__":
	html_path = generate(Path(sys.argv[1]).resolve())
	run(["open", "http://localhost:8080/" + str(html_path.relative_to(os.getenv("HOME")))])
