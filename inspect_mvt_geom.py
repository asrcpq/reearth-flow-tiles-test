#!/usr/bin/env python3
"""
Inspect MVT geometries to check for invalid/empty geometries
"""
import sys
import os
from pathlib import Path
import mapbox_vector_tile

def inspect_mvt_file(path):
    """Inspect a single MVT file and report geometry info"""
    with open(path, 'rb') as f:
        data = f.read()

    try:
        tile = mapbox_vector_tile.decode(data)
    except Exception as e:
        print(f"ERROR decoding {path}: {e}")
        return

    print(f"\n{'='*80}")
    print(f"File: {path}")
    print(f"{'='*80}")

    for layer_name, layer_data in tile.items():
        features = layer_data.get('features', [])
        print(f"\nLayer: {layer_name}")
        print(f"  Total features: {len(features)}")

        geom_types = {}
        invalid_geoms = []

        for idx, feature in enumerate(features):
            geom = feature.get('geometry')
            props = feature.get('properties', {})
            gml_id = props.get('gml_id', f'<no gml_id #{idx}>')

            if geom is None:
                invalid_geoms.append((gml_id, 'null geometry'))
                continue

            geom_type = geom.get('type', 'Unknown')
            coords = geom.get('coordinates')

            # Count by type
            geom_types[geom_type] = geom_types.get(geom_type, 0) + 1

            # Check for empty/invalid coordinates
            is_invalid = False
            reason = None

            if coords is None:
                is_invalid = True
                reason = 'null coordinates'
            elif geom_type == 'Point':
                if not coords or len(coords) == 0:
                    is_invalid = True
                    reason = 'empty point'
            elif geom_type == 'LineString':
                if not coords or len(coords) < 2:
                    is_invalid = True
                    reason = f'linestring with {len(coords) if coords else 0} points'
            elif geom_type == 'Polygon':
                if not coords or len(coords) == 0:
                    is_invalid = True
                    reason = 'empty polygon'
                else:
                    # Check each ring
                    for ring_idx, ring in enumerate(coords):
                        if not ring or len(ring) < 3:
                            is_invalid = True
                            reason = f'polygon ring {ring_idx} has {len(ring) if ring else 0} points (need >= 3)'
                            break
            elif geom_type == 'MultiPolygon':
                if not coords or len(coords) == 0:
                    is_invalid = True
                    reason = 'empty multipolygon'
                else:
                    for poly_idx, polygon in enumerate(coords):
                        if not polygon or len(polygon) == 0:
                            is_invalid = True
                            reason = f'multipolygon[{poly_idx}] is empty'
                            break
                        for ring_idx, ring in enumerate(polygon):
                            if not ring or len(ring) < 3:
                                is_invalid = True
                                reason = f'multipolygon[{poly_idx}] ring {ring_idx} has {len(ring) if ring else 0} points'
                                break
                        if is_invalid:
                            break
            elif geom_type == 'MultiLineString':
                if not coords or len(coords) == 0:
                    is_invalid = True
                    reason = 'empty multilinestring'
                else:
                    for line_idx, line in enumerate(coords):
                        if not line or len(line) < 2:
                            is_invalid = True
                            reason = f'multilinestring[{line_idx}] has {len(line) if line else 0} points'
                            break

            if is_invalid:
                invalid_geoms.append((gml_id, reason))

        # Print summary
        print(f"\n  Geometry types:")
        for gtype, count in sorted(geom_types.items()):
            print(f"    {gtype}: {count}")

        if invalid_geoms:
            print(f"\n  ⚠️  INVALID GEOMETRIES: {len(invalid_geoms)}")
            for gml_id, reason in invalid_geoms:
                print(f"    - {gml_id}: {reason}")
        else:
            print(f"\n  ✓ All geometries are valid")

def inspect_directory(dir_path):
    """Recursively inspect all MVT files in a directory"""
    dir_path = Path(dir_path)

    mvt_files = sorted(dir_path.rglob('*.mvt'))

    if not mvt_files:
        print(f"No .mvt files found in {dir_path}")
        return

    print(f"Found {len(mvt_files)} MVT files in {dir_path}")

    for mvt_file in mvt_files:
        inspect_mvt_file(mvt_file)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python inspect_mvt_geom.py <path-to-mvt-or-directory>")
        print("\nCompare two directories:")
        print("  python inspect_mvt_geom.py <fme-dir> <flow-dir>")
        sys.exit(1)

    paths = sys.argv[1:]

    for path_str in paths:
        path = Path(path_str)

        if not path.exists():
            print(f"ERROR: Path does not exist: {path}")
            continue

        if path.is_file():
            inspect_mvt_file(path)
        else:
            inspect_directory(path)
