#!/usr/bin/env python3
"""
Extract texture mapping from PLATEAU CityGML files.
Prints a map of (gml:id, LOD geometry) -> texture file names.
"""

import xml.etree.ElementTree as ET
from collections import defaultdict
import sys
from pathlib import Path

# Define namespaces used in PLATEAU CityGML files
NAMESPACES = {
    'core': 'http://www.opengis.net/citygml/2.0',
    'gml': 'http://www.opengis.net/gml',
    'app': 'http://www.opengis.net/citygml/appearance/2.0',
    'frn': 'http://www.opengis.net/citygml/cityfurniture/2.0',
    'bldg': 'http://www.opengis.net/citygml/building/2.0',
    'tran': 'http://www.opengis.net/citygml/transportation/2.0',
    'veg': 'http://www.opengis.net/citygml/vegetation/2.0',
}


def extract_polygon_ids_from_geometry(geometry_element):
    """Extract all gml:Polygon gml:id attributes from a geometry element."""
    polygon_ids = []

    # Find all Polygon elements with gml:id
    for polygon in geometry_element.findall('.//gml:Polygon[@gml:id]', NAMESPACES):
        gml_id = polygon.get('{http://www.opengis.net/gml}id')
        if gml_id:
            polygon_ids.append(gml_id)

    return polygon_ids


def parse_citygml(file_path):
    """
    Parse a CityGML file and extract mapping between city objects, their LOD geometries,
    and associated texture files.

    Returns:
        dict: {(city_object_gml_id, lod_level, polygon_gml_id): [texture_files]}
    """
    print(f"Parsing {file_path}...", file=sys.stderr)

    # Parse the XML file
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Dictionary to store city object geometries
    # {city_object_gml_id: {lod_level: [polygon_gml_ids]}}
    city_object_geometries = defaultdict(lambda: defaultdict(list))

    # Dictionary to store texture mappings
    # {polygon_gml_id: [texture_files]}
    polygon_to_textures = defaultdict(list)

    # Step 1: Extract city objects and their LOD geometries
    # Look for CityFurniture, Building, etc.
    city_object_types = [
        'frn:CityFurniture',
        'bldg:Building',
        'bldg:BuildingPart',
        'tran:Road',
        'tran:Railway',
        'veg:SolitaryVegetationObject',
        'veg:PlantCover',
    ]

    for obj_type in city_object_types:
        for city_obj in root.findall(f'.//{obj_type}[@gml:id]', NAMESPACES):
            city_obj_id = city_obj.get('{http://www.opengis.net/gml}id')

            # Find all LOD geometries (lod0Geometry, lod1Geometry, etc.)
            for lod in range(0, 5):  # LOD 0-4
                lod_geom_tag = f'lod{lod}Geometry'

                # Try different namespace prefixes
                for prefix in ['frn', 'bldg', 'tran', 'veg']:
                    ns = NAMESPACES.get(prefix)
                    if ns:
                        lod_geom_elements = city_obj.findall(f'{prefix}:{lod_geom_tag}', NAMESPACES)

                        for lod_geom in lod_geom_elements:
                            polygon_ids = extract_polygon_ids_from_geometry(lod_geom)
                            if polygon_ids:
                                city_object_geometries[city_obj_id][f'LOD{lod}'].extend(polygon_ids)

    # Step 2: Extract appearance data and texture mappings
    for appearance in root.findall('.//app:Appearance', NAMESPACES):
        for surface_data in appearance.findall('.//app:ParameterizedTexture', NAMESPACES):
            # Get the image URI (texture file)
            image_uri_elem = surface_data.find('app:imageURI', NAMESPACES)
            if image_uri_elem is not None:
                texture_file = image_uri_elem.text

                # Find all target polygons for this texture
                for target in surface_data.findall('.//app:target[@uri]', NAMESPACES):
                    target_uri = target.get('uri')
                    if target_uri and target_uri.startswith('#'):
                        # Remove the '#' prefix to get the gml:id
                        polygon_id = target_uri[1:]
                        polygon_to_textures[polygon_id].append(texture_file)

    # Step 3: Combine the mappings
    result = {}
    for city_obj_id, lod_geometries in city_object_geometries.items():
        for lod_level, polygon_ids in lod_geometries.items():
            for polygon_id in polygon_ids:
                textures = polygon_to_textures.get(polygon_id, [])
                key = (city_obj_id, lod_level, polygon_id)
                result[key] = textures

    return result


def print_texture_mapping(mapping):
    """Print the texture mapping in simple format: one line per (gml_id, LOD) pair."""
    # Group by (city_obj_id, lod) and collect all textures
    by_obj_lod = defaultdict(set)
    for (city_obj_id, lod, polygon_id), textures in mapping.items():
        key = (city_obj_id, lod)
        by_obj_lod[key].update(textures)

    # Print one line per (gml_id, LOD) with deduplicated texture names
    for (city_obj_id, lod), textures in sorted(by_obj_lod.items()):
        texture_str = ", ".join(sorted(textures)) if textures else ""
        print(f"{city_obj_id}, {lod}: {texture_str}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_texture_mapping.py <citygml_file.gml>")
        print("\nExample:")
        print("  python extract_texture_mapping.py 54400098_frn_6697_op.gml")
        sys.exit(1)

    file_path = Path(sys.argv[1])

    if not file_path.exists():
        print(f"Error: File not found: {file_path}", file=sys.stderr)
        sys.exit(1)

    try:
        # Parse and extract mappings
        mapping = parse_citygml(file_path)

        # Print results
        print_texture_mapping(mapping)

    except ET.ParseError as e:
        print(f"Error parsing XML: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
