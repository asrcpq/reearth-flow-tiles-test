#!/usr/bin/env python3
import sys
import shutil
import subprocess
from pathlib import Path


def find_b3dm_tilesets(root_dir):
    tilesets = []
    for tileset_json in root_dir.rglob("tileset.json"):
        tileset_dir = tileset_json.parent
        if any(tileset_dir.rglob("*.b3dm")):
            tilesets.append(tileset_dir)
    return tilesets


def decompress_glb_files(tileset_dir):
    """Decompress all Draco-compressed GLB files in the tileset."""
    print(f"Decompressing GLB files in: {tileset_dir}")

    glb_files = list(tileset_dir.rglob("*.glb"))
    if not glb_files:
        print("  No GLB files found")
        return

    print(f"  Found {len(glb_files)} GLB file(s)")

    for glb_file in glb_files:
        temp_file = glb_file.with_suffix(".glb.tmp")
        try:
            # Create a temporary copy first
            shutil.copy2(glb_file, temp_file)

            # Use glb-decompress to decompress Draco in-place
            subprocess.run([
                "npx", "glb-decompress",
                str(temp_file)
            ], check=True, capture_output=True)

            # Replace original with decompressed version
            temp_file.replace(glb_file)
            print(f"    ✓ {glb_file.relative_to(tileset_dir)}")
        except subprocess.CalledProcessError as e:
            if temp_file.exists():
                temp_file.unlink()
            print(f"    ✗ Failed: {glb_file.relative_to(tileset_dir)}")
            print(f"       Error: {e.stderr.decode() if e.stderr else e}")
            raise


def upgrade_tileset(tileset_dir):
    print(f"Upgrading: {tileset_dir}")
    backup_dir = tileset_dir.parent / f"{tileset_dir.name}_old"

    if backup_dir.exists():
        shutil.rmtree(backup_dir)

    tileset_dir.rename(backup_dir)

    try:
        subprocess.run([
            "npx", "3d-tiles-tools", "upgrade",
            "-i", str(backup_dir / "tileset.json"),
            "-o", str(tileset_dir),
            "--targetVersion", "1.1"
        ], check=True)

        # Decompress Draco-compressed GLB files
        decompress_glb_files(tileset_dir)

        shutil.rmtree(backup_dir)
    except subprocess.CalledProcessError as e:
        if tileset_dir.exists():
            shutil.rmtree(tileset_dir)
        backup_dir.rename(tileset_dir)
        raise


def main():
    fme_output_dir = Path(sys.argv[1])
    dest_zip = Path(sys.argv[2])

    if dest_zip.suffix == ".zip":
        dest_zip = dest_zip.with_suffix("")

    tilesets = find_b3dm_tilesets(fme_output_dir)
    print(f"Found {len(tilesets)} tileset(s) with .b3dm files")

    for tileset_dir in tilesets:
        upgrade_tileset(tileset_dir)

    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    shutil.make_archive(str(dest_zip), 'zip', fme_output_dir)
    print(f"Created: {dest_zip}.zip")


if __name__ == "__main__":
    main()
