#!/usr/bin/env python3
import sys, json, subprocess, os, zipfile, shutil
from pathlib import Path
from align_mvt import align_mvt, align_mvt_attr, dict_zip
from align_3dtiles import align_3dtiles
from geometry_comparison import compare_polygons, compare_lines, compare_3d_lines
from run_workflow import run_workflow
from filter_gml import filter_gml_objects
from shapely.geometry import shape
from pprint import pprint

REEARTH_DIR = Path("/Users/tsq/Projects/reearth-flow")
ROOT = Path(__file__).parent
PLATEAU_ROOT = Path(os.getenv("HOME")) / "Projects" / "gkk"

def cast_attr(key, value, table):
	if key not in table:
		return value
	ty = table[key]
	if ty == "string":
		return str(value)
	elif ty == "json":
		if isinstance(value, str):
			j = json.loads(value)
			return j
		return value
	elif ty is None:
		return None
	else:
		raise ValueError(f"Unknown cast type: {ty}")

def compare_recurse(key, v1, v2, gid, bads, casts):
	v1 = cast_attr(key, v1, casts)
	v2 = cast_attr(key, v2, casts)
	# print(key, casts.get("key", ""), type(v1), type(v2))
	if type(v1) != type(v2):
		# ignore bool vs int
		if isinstance(v2, bool) and bool(v1) == v2:
			return
		bads.append((gid, key, v1, v2))
		return
	if isinstance(v1, dict):
		for k in set(v1.keys()).union(set(v2.keys())):
			compare_recurse(f"{key}.{k}", v1.get(k), v2.get(k), gid, bads, casts)
	elif isinstance(v1, list):
		if len(v1) != len(v2):
			bads.append((gid, key, v1, v2))
			return
		for idx in range(len(v1)):
			compare_recurse(f"{key}[{idx}]", v1[idx], v2[idx], gid, bads, casts)
	else:
		if v1 != v2:
			bads.append((gid, key, v1, v2))

def run_mvt_attr(name, cfg, d1, d2):
	results = []
	casts = cfg.get("casts", {})
	for gid, attr1, attr2 in align_mvt_attr(d1, d2):
		if attr1 == None or attr2 == None:
			raise ValueError(f"Missing attributes for gml_id: {gid}")
		bads = []
		for k, v1, v2 in dict_zip(attr1, attr2):
			compare_recurse(k, v1, v2, gid, bads, casts)
		if bads:
			for gid, k, v1, v2 in bads:
				if str(v1) == str(v2):
					print(f"  MISMATCH gml_id={gid} key={k} fme={repr(v1)} reearth={repr(v2)}")
				else:
					print(f"  MISMATCH gml_id={gid} key={k} fme={v1} reearth={v2}")
			raise ValueError(f"Attribute mismatches found for gml_id: {gid}")
		results.append((0.0, "", gid, "ok", False))
	return results

def run_3dtiles_attr(name, cfg, d1, d2):
	casts = cfg.get("casts", {})
	for gid, f1, f2 in align_3dtiles(d1 / "export.json", d2 / "tran_lod3"):
		props1 = f1[1] if f1 else None
		props2 = f2[1] if f2 else None
		if props1 is None or props2 is None:
			raise ValueError(f"Missing attributes for gml_id: {gid}")
		bads = []
		for k, v1, v2 in dict_zip(props1, props2):
			compare_recurse(k, v1, v2, gid, bads, casts)
		if bads:
			for gid, k, v1, v2 in bads:
				if str(v1) == str(v2):
					print(f"  MISMATCH gml_id={gid} key={k} fme={repr(v1)} reearth={repr(v2)}")
				else:
					print(f"  MISMATCH gml_id={gid} key={k} fme={v1} reearth={v2}")
			raise ValueError(f"Attribute mismatches found for gml_id: {gid}")
	return []

def run_mvt_test(name, cfg, d1, d2):
	thresh = cfg.get("threshold", 0.0)
	zoom = cfg.get("zoom")
	zmin = zoom[0] if zoom else None
	zmax = zoom[1] if zoom else None

	results = []
	for path, gid, g1, g2 in align_mvt(d1, d2, zmin, zmax):
		is_poly = (g1 or g2) and (g1 or g2).geom_type in ('Polygon', 'MultiPolygon')

		if name == "compare_polygons" and is_poly:
			status, score = compare_polygons(g1, g2)
		elif name == "compare_lines":
			status, score = compare_lines(g1, g2)
		else:
			continue

		failed = score > thresh
		results.append((score, path, gid, status, failed))

	return results

def run_3dtiles_test(name, cfg, d1, d2):
	"""Run 3D tiles comparison tests."""
	from shapely.ops import unary_union

	fme_json = cfg.get("fme_json", d1 / "export.json")
	output_3dtiles = cfg.get("output_dir", d2 / "tran_lod3")

	results = []
	for gid, f1, f2 in align_3dtiles(fme_json, output_3dtiles):
		g1 = shape(f1[0]) if f1 else None  # FME ground truth geometry

		if f2:
			hierarchical_geoms, props2 = f2
			# Compare ground truth against each LOD level
			for level_idx, level_pieces in enumerate(hierarchical_geoms):
				# Extract geometries from (geometry, error) tuples
				geoms = [geom for geom, error in level_pieces]
				max_error = max((error for geom, error in level_pieces), default=0.0001)
				# Union all pieces at this level
				g2 = unary_union(geoms) if len(geoms) > 1 else geoms[0] if geoms else None
				status, score = compare_3d_lines(g1, g2)
				score /= max_error
				failed = score > 1
				results.append((score, f"{output_3dtiles}/LOD{level_idx}", gid, status, failed))
		else:
			# No output geometry at all
			status, score = compare_3d_lines(g1, None)
			results.append((score, str(output_3dtiles), gid, status, True))

	return results

def run_test(profile_path, stages):
	profile_path = Path(profile_path)
	profile = json.load(open(profile_path))
	test_name = profile_path.parent.name

	TEST_DIR = profile_path.parent
	original_citygml_path = PLATEAU_ROOT / profile["citygml_plateau"]
	BUILD_DIR = ROOT / "build" / test_name
	OUTPUT_DIR = BUILD_DIR / "output"
	FME_DIR = BUILD_DIR / "fme"

	print(f"Running	test: {test_name}")
	print(f"Stages: {stages}")
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

	data_script = TEST_DIR / "data.py"
	needs_processing = ("filter" in profile and profile["filter"]) or data_script.exists()
	citygml_path = BUILD_DIR / original_citygml_path.name
	if not needs_processing:
		citygml_path = original_citygml_path
	elif "g" in stages:
		if "filter" in profile and profile["filter"]:
			print(f"Creating filtered GML with objects: {profile['filter']}")
			filter_gml_objects(original_citygml_path, citygml_path, profile["filter"])
		elif data_script.exists():
			print(f"Running data preparation: {data_script}")
			subprocess.run([sys.executable, str(data_script), str(citygml_path)], check=True)

	# Extract FME output
	if "f" in stages:
		try:
			shutil.rmtree(FME_DIR)
		except FileNotFoundError:
			pass
		fme_zip = ROOT / profile['fme_output']
		if not fme_zip.exists():
			raise FileNotFoundError(f"FME output zip not found: {fme_zip}")
		print(f"Extracting FME output: {fme_zip} -> {FME_DIR}")
		FME_DIR.mkdir(parents=True, exist_ok=True)
		with zipfile.ZipFile(fme_zip, 'r') as zip_ref:
			zip_ref.extractall(FME_DIR)
		for mvt_file in FME_DIR.rglob("*.mvt"):
			mvt_file.rename(mvt_file.with_suffix(".pbf"))

	# Stage "r": Workflow running
	if "r" in stages:
		workflow = REEARTH_DIR / profile["workflow_path"]
		if not workflow.exists():
			raise FileNotFoundError(f"Workflow not found: {workflow}")
		run_workflow(citygml_path, workflow, REEARTH_DIR, BUILD_DIR, OUTPUT_DIR)

	if "e" in stages:
		tests = profile.get("tests", {})
		print(f"Comparing: {FME_DIR} vs {OUTPUT_DIR}")

		all_passed = True
		for name, cfg in tests.items():
			# Run appropriate test based on name
			if name == "compare_3d_lines":
				results = run_3dtiles_test(name, cfg, FME_DIR, OUTPUT_DIR)
			elif name == "compare_mvt_attributes":
				results = run_mvt_attr(name, cfg, FME_DIR, OUTPUT_DIR)
			elif name == "compare_3d_attributes":
				results = run_3dtiles_attr(name, cfg, FME_DIR, OUTPUT_DIR)
			elif name in ("compare_polygons", "compare_lines"):
				results = run_mvt_test(name, cfg, FME_DIR, OUTPUT_DIR)
			else:
				raise ValueError(f"Unknown test name: {name}")

			# Calculate statistics
			worst = 0.0
			fails = 0
			for score, path, gid, status, failed in results:
				worst = max(worst, score)
				if failed:
					fails += 1
					all_passed = False

			print(f"\n{name}: {len(results)} total, {fails} failed")
			if fails > 0:
				print(f"  \x1b[31mworst: {worst:.6f}\x1b[0m")
			else:
				print(f"  worst: {worst:.6f}")

			print(f"  Worst 5:")
			for score, path, gid, status, failed in sorted(results, reverse=True)[:5]:
				print(f"    {path} | {gid} | {score:.6f} | {status}")

		print("\nTest PASSED" if all_passed else "\nTest FAILED")

		# generate output_list (MVT tiles)
		output_layers = sorted({p.relative_to(OUTPUT_DIR).parts[0] for p in OUTPUT_DIR.rglob("*.pbf")}) if OUTPUT_DIR.exists() else []
		fme_layers = sorted({p.relative_to(FME_DIR).parts[0] for p in FME_DIR.rglob("*.pbf")}) if FME_DIR.exists() else []

		mvt_list_path = BUILD_DIR / "mvt_list"
		with open(mvt_list_path, 'w') as f:
			for layer in sorted(set(output_layers + fme_layers)):
				if layer in output_layers: f.write(f"output/{layer}/{{z}}/{{x}}/{{y}}.pbf\n")
				if layer in fme_layers: f.write(f"fme/{layer}/{{z}}/{{x}}/{{y}}.pbf\n")
		print(f"Generated: {mvt_list_path}")

		# generate 3dtiles_list (directories containing tileset.json)
		output_3dtiles = sorted({p.relative_to(OUTPUT_DIR).parent for p in OUTPUT_DIR.rglob("tileset.json")}) if OUTPUT_DIR.exists() else []
		fme_3dtiles = sorted({p.relative_to(FME_DIR).parent for p in FME_DIR.rglob("tileset.json")}) if FME_DIR.exists() else []

		tiles_3d_list_path = BUILD_DIR / "3dtiles_list"
		with open(tiles_3d_list_path, 'w') as f:
			for layer in sorted(set(output_3dtiles + fme_3dtiles)):
				if layer in output_3dtiles: f.write(f"output/{layer}/tileset.json\n")
				if layer in fme_3dtiles: f.write(f"fme/{layer}/tileset.json\n")
		print(f"Generated: {tiles_3d_list_path}")

stages = sys.argv[2] if len(sys.argv) > 2 else "re"
run_test(Path(sys.argv[1]).resolve(), stages)
