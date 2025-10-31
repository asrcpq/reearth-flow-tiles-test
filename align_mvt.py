import mapbox_vector_tile
import sys, os
from pathlib import Path
from shapely.geometry import box, shape
from geometry_comparison import compare_geometries

def load_mvt(path):
    with open(path, "rb") as f:
        return mapbox_vector_tile.decode(f.read())

def features_by_gml_id(layer_data):
    result = {}
    for feature in layer_data['features']:
        gml_id = feature['properties'].get('gml_id')
        if gml_id:
            result[gml_id] = feature
    return result

def is_empty(x, label):
    if label == "file":
        for layer_name, layer_data in x.items():
            if layer_data['features']:
                return False
        return True
    if label == "layer":
        return len(x['features']) == 0
    if label == "feature":
        return False
    raise ValueError(f"Unknown label: {label}")

def dict_zip(dict1, dict2):
    keys = set(dict1.keys()).union(set(dict2.keys()))
    for k in keys:
        yield k, dict1.get(k, None), dict2.get(k, None)

def align_mvt_file(tile1, tile2, results, tile_path=None):
    tile1_layers = tile1 if tile1 else {}
    tile2_layers = tile2 if tile2 else {}
    for layer_name, layer1_data, layer2_data in dict_zip(tile1_layers, tile2_layers):
        align_mvt_layer(layer1_data, layer2_data, results, tile_path=tile_path)

def normalize_geometry(geom, extent):
    from shapely.affinity import scale, translate
    # Scale from [0, extent] to [0, 1]
    return scale(geom, xfact=1/extent, yfact=1/extent, origin=(0, 0))

def clip_geometry_to_tile(geom, extent):
    # Clip Shapely geometry to tile bounds.
    if geom is None or geom.is_empty:
        return None

    # Fix invalid geometries
    if not geom.is_valid:
        geom = geom.buffer(0)
        if geom.is_empty:
            return None

    # Clip to tile bounds
    tile_bounds = box(0, 0, extent, extent)
    try:
        clipped = geom.intersection(tile_bounds)
    except Exception:
        return None

    return clipped if not clipped.is_empty else None


def align_mvt_feature_shapely(geom1, geom2):
    """Compare two geometries using multi-level strategy."""
    result = compare_geometries(geom1, geom2)
    # Add legacy 'score' field for backward compatibility
    result["score"] = result["overall_score"]
    return result


def align_mvt_layer(layer1_data, layer2_data, results, tile_path=None):
    dict1 = features_by_gml_id(layer1_data) if layer1_data else {}
    dict2 = features_by_gml_id(layer2_data) if layer2_data else {}

    extent1 = layer1_data.get('extent', 4096) if layer1_data else 4096
    extent2 = layer2_data.get('extent', 4096) if layer2_data else 4096

    for gml_id, feature1, feature2 in dict_zip(dict1, dict2):
        # Convert GeoJSON-like geometry to Shapely, then normalize
        if feature1:
            geom1 = shape(feature1['geometry'])
            geom1 = normalize_geometry(geom1, extent1)
        else:
            geom1 = None

        if feature2:
            geom2 = shape(feature2['geometry'])
            geom2 = normalize_geometry(geom2, extent2)
        else:
            geom2 = None

        # Clip in normalized [0,1] space
        geom1_clipped = clip_geometry_to_tile(geom1, 1.0) if geom1 else None
        geom2_clipped = clip_geometry_to_tile(geom2, 1.0) if geom2 else None

        result = align_mvt_feature_shapely(geom1_clipped, geom2_clipped)
        results.append((tile_path, gml_id, result))

def align_mvt(src_dir, dst_dir):
    results = []
    relatives1 = [os.path.relpath(p, src_dir) for p in src_dir.rglob("*.pbf")]
    relatives2 = [os.path.relpath(p, dst_dir) for p in dst_dir.rglob("*.pbf")]
    tiles1 = {rel: load_mvt(src_dir / rel) for rel in relatives1}
    tiles2 = {rel: load_mvt(dst_dir / rel) for rel in relatives2}
    for tile_path, tile1, tile2 in dict_zip(tiles1, tiles2):
        # print(tile_path, file=sys.stderr)
        align_mvt_file(tile1, tile2, results, tile_path=tile_path)
    return results

def align_mvt_with_threshold(src_dir, dst_dir, threshold=0.0):
    results = align_mvt(src_dir, dst_dir)

    # Sort all results by score (worst first)
    results.sort(key=lambda x: x[2].get('score', 0), reverse=True)

    worst_score = results[0][2].get('score', 0) if results else 0.0
    fail_count = sum(1 for _, _, result in results if result.get('score', 0) > threshold)

    return {
        'results': results,
        'total': len(results),
        'fail_count': fail_count,
        'worst_score': worst_score
    }