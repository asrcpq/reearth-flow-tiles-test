#!/usr/bin/env python3

# usage <profile.toml> <src_dir>
# pack .zip files yourself if names cannot be handled by auto_generate_zip_name()

import sys
import shutil
import subprocess
import tomllib
from pathlib import Path

def decompress_glb_file(glb_file):
    temp_file = glb_file.with_suffix(".glb.tmp")
    shutil.copy2(glb_file, temp_file)
    try:
        subprocess.run(
            ["npx", "glb-decompress", str(temp_file)],
            check=True,
            capture_output=True
        )
        temp_file.replace(glb_file)
    except:
        if temp_file.exists():
            temp_file.unlink()
        raise


def upgrade_tileset(tileset_dir):
    tileset_json = tileset_dir / "tileset.json"
    assert tileset_json.exists(), f"tileset.json not found in {tileset_dir}"
    backup_dir = tileset_dir.parent / f"{tileset_dir.name}_backup"
    tileset_dir.rename(backup_dir)
    try:
        subprocess.run([
            "npx", "3d-tiles-tools", "upgrade",
            "-i", str(backup_dir / "tileset.json"),
            "-o", str(tileset_dir),
            "--targetVersion", "1.1"
        ], check=True)

        for glb_file in tileset_dir.rglob("*.glb"):
            decompress_glb_file(glb_file)

        shutil.rmtree(backup_dir)
    except:
        if tileset_dir.exists():
            shutil.rmtree(tileset_dir)
        backup_dir.rename(tileset_dir)
        raise

def find_and_upgrade_tilesets(root_dir):
    for tileset_json in root_dir.rglob("tileset.json"):
        tileset_dir = tileset_json.parent
        if any(tileset_dir.rglob("*.b3dm")):
            upgrade_tileset(tileset_dir)

def remove_b3dm_files(root_dir):
    for b3dm_file in root_dir.rglob("*.b3dm"):
        b3dm_file.unlink()

def detect_format(dir_path):
    assert dir_path.exists(), f"Directory not found: {dir_path}"
    has_tileset = any(dir_path.rglob("tileset.json"))
    has_glb = any(dir_path.rglob("*.glb"))
    has_mvt = any(dir_path.rglob("*.mvt"))
    if has_tileset or has_glb:
        return "3dtiles"
    elif has_mvt:
        return "mvt"
    raise AssertionError(f"Cannot detect format: {dir_path}")

def auto_generate_zip_name(citygml_name, dir_name, dir_path):
    stripped_name = citygml_name.replace(".zip", "")
    parts = dir_name.split("_")
    if parts[0] and stripped_name.endswith(f"_{parts[0]}"):
        stripped_name = stripped_name[:-len(parts[0])-1]

    format_type = detect_format(dir_path)

    if "_dm_geometric_attributes" in dir_name:
        dir_name_part = dir_name.replace("_dm_geometric_attributes", "_geometric_attributes")
        return f"{stripped_name}_{dir_name_part}.zip"
    elif "_lod" in dir_name:
        before_lod, lod_part = dir_name.rsplit("_lod", 1)
        return f"{stripped_name}_{before_lod}_{format_type}_lod{lod_part}.zip"
    else:
        return f"{stripped_name}_{dir_name}_{format_type}.zip"

def process_expected_output(key, zip_name, src_dir, output_base_dir):
    key_dir = src_dir / key
    assert key_dir.exists() and key_dir.is_dir(), f"Directory not found: {key_dir}"
    assert zip_name.endswith(".zip"), f"Expected .zip extension: {zip_name}"

    unzipped_name = zip_name[:-4]
    work_dir = output_base_dir / unzipped_name

    if work_dir.exists():
        shutil.rmtree(work_dir)

    shutil.copytree(key_dir, work_dir)

    try:
        find_and_upgrade_tilesets(work_dir)
        remove_b3dm_files(work_dir)

        zip_path = output_base_dir / unzipped_name
        shutil.make_archive(str(zip_path), 'zip', work_dir)
    finally:
        if work_dir.exists():
            shutil.rmtree(work_dir)

def main():
    profile_toml_path = Path(sys.argv[1])
    src_dir = Path(sys.argv[2])

    assert profile_toml_path.exists(), f"Profile not found: {profile_toml_path}"
    assert src_dir.exists(), f"Source directory not found: {src_dir}"

    output_base_dir = profile_toml_path.parent / "fme"
    try:
        shutil.rmtree(output_base_dir)
    except FileNotFoundError:
        pass
    output_base_dir.mkdir(parents=True, exist_ok=True)

    with open(profile_toml_path, "rb") as f:
        config = tomllib.load(f)

    citygml_name = config.get("citygml_zip_name")
    assert citygml_name, "No citygml_zip_name in profile.toml"

    for item in src_dir.iterdir():
        # exclude maxLod.csv and summary_*.csv
        if item.is_file() and item.suffix != ".csv":
            shutil.copy2(item, output_base_dir / item.name)
        elif item.is_dir():
            zip_name = auto_generate_zip_name(citygml_name, item.name, item)
            process_expected_output(item.name, zip_name, src_dir, output_base_dir)

if __name__ == "__main__":
    main()
