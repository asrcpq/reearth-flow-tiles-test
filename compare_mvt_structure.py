#!/usr/bin/env python3
"""
Compare the structure of MVT tiles between FME and engine output.
Specifically checking for over-triangulation issues.
"""
import sys
from pathlib import Path
import mapbox_vector_tile

# The problematic tile from the test results
TILE_PATH = "tran_lod2/15/29096/12904.pbf"
FME_TILE = Path("/Users/tsq/Projects/reearth-flow-mvt-test/build/13115-polygon-shape/fme") / TILE_PATH
ENGINE_TILE = Path("/Users/tsq/Projects/reearth-flow-mvt-test/build/13115-polygon-shape/output") / TILE_PATH

# Target feature ID
TARGET_FEATURE = "traf_e5ea50ce-7198-4879-a380-9d99f1c6491f"

def analyze_mvt(tile_path, source_name):
    """Analyze MVT tile structure"""
    if not tile_path.exists():
        print(f"❌ {source_name} tile not found: {tile_path}")
        return None

    with open(tile_path, 'rb') as f:
        data = f.read()

    decoded = mapbox_vector_tile.decode(data)

    print(f"\n{'='*80}")
    print(f"{source_name}: {tile_path.name}")
    print(f"{'='*80}")

    for layer_name, layer_data in decoded.items():
        print(f"\nLayer: {layer_name}")
        print(f"  Total features: {len(layer_data['features'])}")

        # Find the target feature
        target_feature = None
        for feature in layer_data['features']:
            props = feature.get('properties', {})
            gml_id = props.get('gml_id') or props.get('id') or props.get('gmlId')

            if gml_id and TARGET_FEATURE in gml_id:
                target_feature = feature
                break

        if target_feature:
            print(f"\n  ✓ Found target feature: {TARGET_FEATURE}")
            geom = target_feature['geometry']
            geom_type = geom['type']
            coords = geom['coordinates']

            print(f"    Geometry type: {geom_type}")

            if geom_type == 'Polygon':
                print(f"    Number of rings: {len(coords)}")
                print(f"      - Exterior ring: 1")
                print(f"      - Interior rings (holes): {len(coords) - 1}")
                for i, ring in enumerate(coords):
                    ring_type = "Exterior" if i == 0 else f"Interior {i}"
                    print(f"        {ring_type} ring: {len(ring)} points")

            elif geom_type == 'MultiPolygon':
                total_rings = sum(len(poly) for poly in coords)
                total_polygons = len(coords)
                print(f"    Number of polygons: {total_polygons}")
                print(f"    Total rings across all polygons: {total_rings}")

                # Count rings
                exterior_count = total_polygons
                interior_count = total_rings - total_polygons
                print(f"      - Exterior rings: {exterior_count}")
                print(f"      - Interior rings (holes): {interior_count}")

                # Show details of each polygon
                for i, poly in enumerate(coords[:10]):  # Show first 10
                    print(f"      Polygon {i+1}: {len(poly)} ring(s)")
                    for j, ring in enumerate(poly):
                        ring_type = "exterior" if j == 0 else "interior"
                        print(f"        - {ring_type}: {len(ring)} points")

                if total_polygons > 10:
                    print(f"      ... and {total_polygons - 10} more polygons")

            return {
                'type': geom_type,
                'num_polygons': len(coords) if geom_type == 'MultiPolygon' else 1,
                'num_rings': sum(len(poly) for poly in coords) if geom_type == 'MultiPolygon' else len(coords),
                'feature': target_feature
            }
        else:
            print(f"\n  ❌ Target feature not found in this layer")

    return None

print("Analyzing MVT structure for triangulation issues...")
print(f"Target feature: {TARGET_FEATURE}")

fme_result = analyze_mvt(FME_TILE, "FME Output")
engine_result = analyze_mvt(ENGINE_TILE, "Engine Output")

print(f"\n{'='*80}")
print("COMPARISON SUMMARY")
print(f"{'='*80}\n")

if fme_result and engine_result:
    print(f"FME Output:")
    print(f"  - Geometry type: {fme_result['type']}")
    print(f"  - Number of polygons: {fme_result['num_polygons']}")
    print(f"  - Total rings: {fme_result['num_rings']}")

    print(f"\nEngine Output:")
    print(f"  - Geometry type: {engine_result['type']}")
    print(f"  - Number of polygons: {engine_result['num_polygons']}")
    print(f"  - Total rings: {engine_result['num_rings']}")

    print(f"\nDifference:")
    poly_diff = engine_result['num_polygons'] - fme_result['num_polygons']
    ring_diff = engine_result['num_rings'] - fme_result['num_rings']

    print(f"  - Polygon count difference: {poly_diff:+d}")
    print(f"  - Ring count difference: {ring_diff:+d}")

    if poly_diff > 50:
        print(f"\n⚠️  ISSUE DETECTED: Over-triangulation!")
        print(f"    The engine is producing {poly_diff} more polygons than FME.")
        print(f"    This suggests the engine is triangulating/tessellating the geometry")
        print(f"    instead of preserving the original polygon structure from the GML.")
        print(f"\n    The original GML has a MultiSurface with 69 separate simple polygons")
        print(f"    that should be combined into a single MultiPolygon in the MVT output,")
        print(f"    not further subdivided.")
    elif poly_diff < -50:
        print(f"\n✓ Engine is combining polygons (good)")
    else:
        print(f"\n✓ Polygon counts are similar")
else:
    print("Could not complete comparison - one or both outputs missing target feature")
