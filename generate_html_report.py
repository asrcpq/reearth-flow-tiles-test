#!/usr/bin/env python3
import json, sys, os
from pathlib import Path
from subprocess import run

def summarize_geometry(geometry):
	"""Analyze geometry and return a summary instead of the full data

	Based on Rust definitions:
	- GeometryValue::None => value: "none"
	- GeometryValue::CityGmlGeometry => value: {cityGmlGeometry: {...}}
	- GeometryValue::FlowGeometry2D => value: {flowGeometry2D: {...}}
	- GeometryValue::FlowGeometry3D => value: {flowGeometry3D: {...}}
	"""
	assert isinstance(geometry, dict), f"geometry must be dict, got {type(geometry)}"
	assert "value" in geometry, "geometry must have 'value' key"

	value = geometry["value"]

	# Handle GeometryValue::None
	if value == "none":
		return {"type": "None"}

	# Must be a dict for other variants
	assert isinstance(value, dict), f"geometry value must be dict or 'none', got {type(value)}"

	# Handle CityGmlGeometry (camelCase at top level)
	if "cityGmlGeometry" in value:
		city_gml = value["cityGmlGeometry"]
		assert isinstance(city_gml, dict), f"cityGmlGeometry must be dict, got {type(city_gml)}"
		assert "gmlGeometries" in city_gml, "cityGmlGeometry must have 'gmlGeometries'"

		gml_geometries = city_gml["gmlGeometries"]
		assert isinstance(gml_geometries, list), f"gmlGeometries must be list, got {type(gml_geometries)}"

		summary = {"type": "CityGmlGeometry", "geometries": []}

		# GmlGeometry uses snake_case (no rename_all directive)
		for gml_geom in gml_geometries:
			assert isinstance(gml_geom, dict), f"gmlGeometry must be dict, got {type(gml_geom)}"
			assert "type" in gml_geom, "gmlGeometry must have 'type'"
			assert "polygons" in gml_geom, "gmlGeometry must have 'polygons'"
			assert "line_strings" in gml_geom, "gmlGeometry must have 'line_strings'"

			geom_type = gml_geom["type"]
			polygons = gml_geom["polygons"]
			line_strings = gml_geom["line_strings"]

			# Count polygon vertices
			polygon_vertices = 0
			for poly in polygons:
				assert isinstance(poly, dict), f"polygon must be dict, got {type(poly)}"
				exterior = poly.get("exterior", [])
				polygon_vertices += len(exterior)
				interiors = poly.get("interiors", [])
				for interior in interiors:
					polygon_vertices += len(interior)

			# Count line string vertices
			line_vertices = sum(len(ls) for ls in line_strings)

			summary["geometries"].append({
				"type": geom_type,
				"lod": gml_geom.get("lod"),
				"polygons": len(polygons),
				"polygon_vertices": polygon_vertices,
				"line_strings": len(line_strings),
				"line_vertices": line_vertices,
			})

		return summary

	# Handle FlowGeometry2D
	if "flowGeometry2D" in value:
		flow_geom = value["flowGeometry2D"]
		assert isinstance(flow_geom, dict), f"flowGeometry2D must be dict, got {type(flow_geom)}"

		summary = {"type": "FlowGeometry2D"}

		# Check for different geometry types
		if "multiPolygon" in flow_geom:
			polygons = flow_geom["multiPolygon"]
			total_vertices = 0
			for poly in polygons:
				exterior = poly.get("exterior", [])
				total_vertices += len(exterior)
				interiors = poly.get("interiors", [])
				for interior in interiors:
					total_vertices += len(interior)
			summary["polygons"] = len(polygons)
			summary["vertices"] = total_vertices

		if "multiLineString" in flow_geom:
			lines = flow_geom["multiLineString"]
			summary["line_strings"] = len(lines)
			summary["vertices"] = sum(len(ls) for ls in lines)

		return summary

	# Handle FlowGeometry3D
	if "flowGeometry3D" in value:
		flow_geom = value["flowGeometry3D"]
		assert isinstance(flow_geom, dict), f"flowGeometry3D must be dict, got {type(flow_geom)}"

		summary = {"type": "FlowGeometry3D"}
		# Add similar logic as FlowGeometry2D if needed
		return summary

	raise ValueError(f"Unknown geometry value variant: {list(value.keys())}")

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
						# Replace geometry with summary
						geometry = feature.get("geometry")
						if geometry:
							geometry_summary = summarize_geometry(geometry)
							feature["geometry"] = geometry_summary
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
	run(["open", "-a", "Safari", "http://localhost:8080/" + str(html_path.relative_to(os.getenv("HOME")))])