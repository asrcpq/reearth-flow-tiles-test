#!/usr/bin/env python3
import sys, json, subprocess, os, zipfile
from pathlib import Path
from align_mvt import align_mvt_with_threshold
from run_workflow import main as run_workflow_main
from filter_gml import filter_gml_objects

REEARTH_DIR = Path("/Users/tsq/Projects/reearth-flow")
ROOT = Path(__file__).parent

def run_test(profile_path, stages):
	profile_path = Path(profile_path)
	profile = json.load(open(profile_path))
	test_name = profile_path.parent.name

	TEST_DIR = profile_path.parent
	original_citygml_path = ROOT / profile["zip_path"]
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
	elif citygml_path.exists():
		pass
	elif "filter" in profile and profile["filter"]:
		print(f"Creating filtered GML with objects: {profile['filter']}")
		filter_gml_objects(original_citygml_path, citygml_path, profile["filter"])
	elif data_script.exists():
		print(f"Running data preparation: {data_script}")
		subprocess.run([sys.executable, str(data_script), str(citygml_path)], check=True)

	# Extract FME output
	if not FME_DIR.exists():
		fme_zip = ROOT / profile['fme_output']
		if not fme_zip.exists():
			raise FileNotFoundError(f"FME output zip not found: {fme_zip}")
		print(f"Extracting FME output: {fme_zip} -> {FME_DIR}")
		FME_DIR.mkdir(parents=True, exist_ok=True)
		with zipfile.ZipFile(fme_zip, 'r') as zip_ref:
			zip_ref.extractall(FME_DIR)
		for mvt_file in FME_DIR.rglob("*.mvt"):
			mvt_file.rename(mvt_file.with_suffix(".pbf"))
	else:
		print(f"FME output already exists, skipping extraction: {FME_DIR}")

	# Stage "r": Workflow running
	if "r" in stages:
		workflow = REEARTH_DIR / profile["workflow_path"]
		if not workflow.exists():
			raise FileNotFoundError(f"Workflow not found: {workflow}")
		run_workflow_main(citygml_path, workflow, REEARTH_DIR, BUILD_DIR, OUTPUT_DIR)

	# Stage "e": Evaluation
	if "e" in stages:
		threshold = profile.get("threshold", 0.0)
		print(f"Comparing: {FME_DIR} vs {OUTPUT_DIR} (threshold: {threshold})")
		summary = align_mvt_with_threshold(FME_DIR, OUTPUT_DIR, threshold)
		print(f"\nResults: {summary['total']} total, {summary['fail_count']} above threshold")
		print(f"Worst score: {summary['worst_score']:.6f}")
		print(f"\nWorst 5 results:")
		for tile_path, gml_id, result in summary['results'][:5]:
			print(f"  {tile_path} | {gml_id} | score: {result.get('score', 0):.6f} | {result.get('status')}")
		print("\nTest PASSED" if summary['fail_count'] == 0 else "\nTest FAILED")

		# generate output_list
		output_layers = sorted({p.relative_to(OUTPUT_DIR).parts[0] for p in OUTPUT_DIR.rglob("*.pbf")}) if OUTPUT_DIR.exists() else []
		fme_layers = sorted({p.relative_to(FME_DIR).parts[0] for p in FME_DIR.rglob("*.pbf")}) if FME_DIR.exists() else []
		with open(BUILD_DIR / "output_list", 'w') as f:
			for layer in sorted(set(output_layers + fme_layers)):
				if layer in output_layers: f.write(f"output/{layer}/{{z}}/{{x}}/{{y}}.pbf\n")
				if layer in fme_layers: f.write(f"fme/{layer}/{{z}}/{{x}}/{{y}}.pbf\n")
		print(f"Generated: {BUILD_DIR / 'output_list'}")

stages = sys.argv[2] if len(sys.argv) > 2 else "re"
run_test(Path(sys.argv[1]).resolve(), stages)