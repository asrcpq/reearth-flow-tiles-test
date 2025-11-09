import json
import tempfile
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon, shape
from pygltflib import GLTF2
from tile_reader import read_glb_tile
import numpy as np

def build_tile_hierarchy_v11(tile_node, base_dir, depth=0):
    result = []
    geometric_error = tile_node.get('geometricError', 0)
    contents = tile_node.get('contents', [])
    for content_item in contents:
        if 'uri' in content_item:
            tile_uri = content_item['uri']
            result.append((depth, tile_uri, geometric_error))
    children = tile_node.get('children', [])
    for child in children:
        result.extend(build_tile_hierarchy_v11(child, base_dir, depth + 1))
    return result

def dict_zip(dict1, dict2):
    keys = set(dict1.keys()).union(set(dict2.keys()))
    for k in keys:
        yield k, dict1.get(k, None), dict2.get(k, None)

def collect_features_hierarchical(directory):
    # Find tileset.json
    tileset_path = directory / 'tileset.json'
    if not tileset_path.exists():
        return {}
    with open(tileset_path, 'r') as f:
        tileset = json.load(f)
    assert tileset["asset"]["version"].startswith('1.1'), "Only 3D Tiles version 1.1 is supported"
    tile_hierarchy = build_tile_hierarchy_v11(tileset['root'], directory)

    max_depth = max(depth for depth, _, _ in tile_hierarchy) if tile_hierarchy else 0
    feature_data = {}

    for depth, tile_uri, geometric_error in tile_hierarchy:
        tile_path = directory / tile_uri
        if not tile_path.exists():
            continue
        batch_features = read_glb_tile(tile_path)

        # Map geometries to features by batch ID
        for batch_id, (props, geometries) in batch_features.items():
            # Extract gml_id from properties
            gml_id = props.get('gml_id')
            if not gml_id:
                continue

            if gml_id not in feature_data:
                feature_data[gml_id] = {}
            if depth not in feature_data[gml_id]:
                feature_data[gml_id][depth] = []
            feature_data[gml_id][depth].append((geometries, geometric_error, props))

    # Build final result with hierarchical geometries
    # Each level contains a list of (geometry, error) pieces - NO union yet
    result = {}
    for gml_id, depth_data in feature_data.items():
        hierarchical_geoms = []  # List of levels, each level is list of (geometry, error)
        stored_properties = None

        # Sort by depth to build from root to leaves
        for depth in sorted(depth_data.keys()):
            level_pieces = []  # All geometry pieces at this depth level

            for geoms, error, props in depth_data[depth]:
                # Add each geometry as a separate piece with its error
                for geom in geoms:
                    level_pieces.append((geom, error))

                # Assert properties are identical
                if stored_properties is None:
                    stored_properties = {k: v for k, v in props.items() if k != '_tile'}
                else:
                    for key, value in props.items():
                        if key == '_tile':
                            continue
                        if key in stored_properties:
                            assert stored_properties[key] == value, \
                                f"Property {key} mismatch for {gml_id}: {stored_properties[key]} != {value}"

            # Store list of pieces for this level (no union)
            if level_pieces:
                hierarchical_geoms.append(level_pieces)
            else:
                # No geometry at this level, use parent's pieces if exists
                if hierarchical_geoms:
                    parent_pieces = hierarchical_geoms[-1]
                    hierarchical_geoms.append(parent_pieces)

        result[gml_id] = (hierarchical_geoms, stored_properties)

    return result

def export_shapely_to_obj(geometries, output_path):
    vertices = []
    faces = []
    vertex_offset = 1  # OBJ uses 1-based indexing

    s = 0
    for geom in geometries:
        # Handle different geometry types
        if geom.geom_type == 'Polygon':
            polygons = [geom]
        elif geom.geom_type == 'MultiPolygon':
            polygons = list(geom.geoms)
        else:
            continue
        s += len(polygons)

        for poly in polygons:
            # Get exterior coordinates
            coords = list(poly.exterior.coords)

            # Add vertices (skip last point as it duplicates first)
            start_idx = vertex_offset
            for coord in coords[:-1]:
                if len(coord) == 2:
                    vertices.append(f"v {coord[0]} {coord[1]} 0.0")
                else:
                    vertices.append(f"v {coord[0]} {coord[1]} {coord[2]}")
                vertex_offset += 1

            # Add face (triangulate simple polygon as fan)
            num_verts = len(coords) - 1
            for i in range(1, num_verts - 1):
                faces.append(f"f {start_idx} {start_idx + i} {start_idx + i + 1}")
    print(f"Exported {len(vertices)} vertices and {len(faces)} faces to {output_path} (from {s} polygons)")

    # Write OBJ file
    with open(output_path, 'w') as f:
        f.write("# Exported from align_3dtiles.py\n")
        f.write(f"# {len(vertices)} vertices, {len(faces)} faces\n\n")
        for v in vertices:
            f.write(v + "\n")
        f.write("\n")
        for face in faces:
            f.write(face + "\n")

# since there is no python library for draco decoding with attributes, we fallback to let FME export json files directly
# this function exports similar gml_id -> (geometry, properties) structure
def load_json(path):
    ret = {}
    with open(path, 'r') as f:
        data = json.load(f)
        for feature in data:
            # Convert GeoJSON geometry to shapely geometry
            json_geom = feature["json_geometry"]
            shapely_geom = shape(json_geom)

            for key in ["json_geometry", "json_ogc_wkt_crs", "core:creationDate", "json_featuretype"]:
                if key in feature:
                    del feature[key]
            ret[feature["gml_id"]] = (shapely_geom, feature)
    return ret

def align_3dtiles(d1, d2):
    # Returns: iterator of (gml_id, feature1_data, feature2_data) where feature_data = ([(geometry_union, error)], properties)
    # temp_d1 = Path(tempfile.mkdtemp())
    # subprocess.run(['3d-tiles-tools', 'upgrade', '--targetVersion', '1.1', '-i', str(d1), '-o', str(temp_d1)], check=True)
    features1 = load_json(d1)
    features2 = collect_features_hierarchical(d2)
    for gml_id, f1, f2 in dict_zip(features1, features2):
        yield (gml_id, f1, f2)

if __name__ == '__main__':
    d1 = Path("build/08220-3dtiles/fme/export.json")
    d2 = Path("build/08220-3dtiles/output/tran_lod3")
    features1 = load_json(d1)
    features2 = collect_features_hierarchical(d2)

    # f1 is ground truth, all only1/only2 should give worst score +inf
    for gml_id, f1, f2 in align_3dtiles(d1, d2):
        status = "both" if f1 and f2 else ("only1" if f1 else "only2")
        print(f"{gml_id}\t{status}")

        if f1:
            geom1, props1 = f1
            print(geom1["type"], props1.keys())

        if f2:
            hierarchical_geoms2, props2 = f2
            print(f"  Dir2: {len(hierarchical_geoms2)} levels")
            # export_shapely_to_obj([x[0] for x in hierarchical_geoms2[-1]], "/tmp/tmp2.obj")
            for level_idx, level_pieces in enumerate(hierarchical_geoms2):
                errors = set(err for _, err in level_pieces)
                print(f"    Level {level_idx}: {len(level_pieces)} pieces, errors={errors}")
