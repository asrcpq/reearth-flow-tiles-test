#!/usr/bin/env python3
"""
Verify texture coordinate alignment in CityGML files.

This script checks:
1. Texture coordinates reference valid polygon/surface IDs
2. Ring references in textureCoordinates match polygon boundary rings
3. Number of UV coordinate pairs matches vertex count in the referenced ring
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple, Set
import xml.etree.ElementTree as ET

# Namespace mappings for CityGML
NAMESPACES = {
    'app': 'http://www.opengis.net/citygml/appearance/2.0',
    'gml': 'http://www.opengis.net/gml',
    'core': 'http://www.opengis.net/citygml/2.0',
    'bldg': 'http://www.opengis.net/citygml/building/2.0',
    'tran': 'http://www.opengis.net/citygml/transportation/2.0',
}


class TextureCoordInfo:
    """Information about texture coordinates"""
    def __init__(self, target_uri: str, ring_uri: str, coords: List[float]):
        self.target_uri = target_uri  # e.g., #poly_Gkaga01022_p18091_2
        self.ring_uri = ring_uri      # e.g., #line_Gkaga01022_p18091_2
        self.coords = coords          # List of UV coordinates
        self.num_pairs = len(coords) // 2

    def __repr__(self):
        return f"TextureCoord(target={self.target_uri}, ring={self.ring_uri}, pairs={self.num_pairs})"


class PolygonInfo:
    """Information about a polygon/surface"""
    def __init__(self, poly_id: str):
        self.poly_id = poly_id
        self.rings: Dict[str, int] = {}  # ring_id -> vertex_count

    def add_ring(self, ring_id: str, vertex_count: int):
        self.rings[ring_id] = vertex_count

    def __repr__(self):
        return f"Polygon(id={self.poly_id}, rings={self.rings})"


class VerificationResult:
    """Results of texture alignment verification"""
    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []
        self.polygons_checked = 0
        self.textures_checked = 0

    def add_error(self, msg: str):
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

    def add_info(self, msg: str):
        self.info.append(msg)

    def print_summary(self):
        print("\n" + "="*80)
        print("VERIFICATION SUMMARY")
        print("="*80)
        print(f"Polygons checked: {self.polygons_checked}")
        print(f"Textures checked: {self.textures_checked}")
        print(f"Errors: {len(self.errors)}")
        print(f"Warnings: {len(self.warnings)}")

        if self.errors:
            print("\n" + "-"*80)
            print("ERRORS:")
            print("-"*80)
            for error in self.errors:
                print(f"  ❌ {error}")

        if self.warnings:
            print("\n" + "-"*80)
            print("WARNINGS:")
            print("-"*80)
            for warning in self.warnings:
                print(f"  ⚠️  {warning}")

        if self.info:
            print("\n" + "-"*80)
            print("INFO:")
            print("-"*80)
            for info in self.info[:10]:  # Limit to first 10
                print(f"  ℹ️  {info}")
            if len(self.info) > 10:
                print(f"  ... and {len(self.info) - 10} more")

        print("\n" + "="*80)
        if not self.errors:
            print("✅ All texture coordinates are properly aligned!")
        else:
            print("❌ Texture alignment issues found!")
        print("="*80)


def parse_coord_list(coord_text: str) -> List[float]:
    """Parse space-separated coordinate list into floats"""
    return [float(x) for x in coord_text.strip().split()]


def count_vertices_in_poslist(poslist_text: str) -> int:
    """Count vertices in a gml:posList (3D coordinates, so divide by 3)"""
    coords = parse_coord_list(poslist_text)
    return len(coords) // 3


def collect_polygons(root: ET.Element) -> Dict[str, PolygonInfo]:
    """Collect all polygon/surface definitions with their ring information"""
    polygons = {}

    # Find all elements with gml:id attributes that represent polygons
    for elem in root.iter():
        gml_id = elem.get('{http://www.opengis.net/gml}id')
        if not gml_id:
            continue

        # Look for Polygon elements
        if elem.tag.endswith('Polygon'):
            poly_info = PolygonInfo(gml_id)

            # Find exterior ring
            exterior = elem.find('.//gml:exterior', NAMESPACES)
            if exterior is not None:
                linear_ring = exterior.find('.//gml:LinearRing', NAMESPACES)
                if linear_ring is not None:
                    ring_id = linear_ring.get('{http://www.opengis.net/gml}id')
                    poslist = linear_ring.find('gml:posList', NAMESPACES)
                    if poslist is not None and poslist.text:
                        vertex_count = count_vertices_in_poslist(poslist.text)
                        if ring_id:
                            poly_info.add_ring(ring_id, vertex_count)

            # Find interior rings
            for interior in elem.findall('.//gml:interior', NAMESPACES):
                linear_ring = interior.find('.//gml:LinearRing', NAMESPACES)
                if linear_ring is not None:
                    ring_id = linear_ring.get('{http://www.opengis.net/gml}id')
                    poslist = linear_ring.find('gml:posList', NAMESPACES)
                    if poslist is not None and poslist.text:
                        vertex_count = count_vertices_in_poslist(poslist.text)
                        if ring_id:
                            poly_info.add_ring(ring_id, vertex_count)

            polygons[gml_id] = poly_info

    return polygons


def collect_texture_coords(root: ET.Element) -> List[TextureCoordInfo]:
    """Collect all texture coordinate definitions"""
    texture_coords = []

    # Find all app:target elements
    for target in root.findall('.//app:target', NAMESPACES):
        target_uri = target.get('uri')
        if not target_uri:
            # Check if it's a simple text target
            if target.text and target.text.strip().startswith('#'):
                target_uri = target.text.strip()
            else:
                continue

        # Find TexCoordList under this target
        texcoord_list = target.find('.//app:TexCoordList', NAMESPACES)
        if texcoord_list is None:
            continue

        # Find textureCoordinates
        for texcoord in texcoord_list.findall('app:textureCoordinates', NAMESPACES):
            ring_uri = texcoord.get('ring')
            coords_text = texcoord.text

            if ring_uri and coords_text:
                coords = parse_coord_list(coords_text)
                texture_coords.append(TextureCoordInfo(target_uri, ring_uri, coords))

    return texture_coords


def verify_alignment(gml_file: Path) -> VerificationResult:
    """Verify texture coordinate alignment in a CityGML file"""
    result = VerificationResult()

    try:
        tree = ET.parse(gml_file)
        root = tree.getroot()
    except Exception as e:
        result.add_error(f"Failed to parse XML: {e}")
        return result

    # Collect polygon and texture information
    polygons = collect_polygons(root)
    texture_coords = collect_texture_coords(root)

    result.polygons_checked = len(polygons)
    result.textures_checked = len(texture_coords)

    result.add_info(f"Found {len(polygons)} polygons")
    result.add_info(f"Found {len(texture_coords)} texture coordinate definitions")

    # Verify each texture coordinate
    for tex_coord in texture_coords:
        # Remove '#' prefix from URIs
        target_id = tex_coord.target_uri.lstrip('#')
        ring_id = tex_coord.ring_uri.lstrip('#')

        # Check if target polygon exists
        if target_id not in polygons:
            result.add_error(
                f"Texture references non-existent polygon: {tex_coord.target_uri}"
            )
            continue

        polygon = polygons[target_id]

        # Check if ring exists in polygon
        if ring_id not in polygon.rings:
            result.add_error(
                f"Texture references non-existent ring: {tex_coord.ring_uri} "
                f"in polygon {tex_coord.target_uri}. "
                f"Available rings: {list(polygon.rings.keys())}"
            )
            continue

        # Check if vertex count matches UV coordinate pairs
        vertex_count = polygon.rings[ring_id]
        uv_pairs = tex_coord.num_pairs

        if vertex_count != uv_pairs:
            result.add_error(
                f"Vertex count mismatch: polygon {tex_coord.target_uri}, "
                f"ring {tex_coord.ring_uri} has {vertex_count} vertices "
                f"but texture has {uv_pairs} UV coordinate pairs"
            )
        else:
            result.add_info(
                f"✓ {tex_coord.target_uri} -> {tex_coord.ring_uri}: "
                f"{vertex_count} vertices = {uv_pairs} UV pairs"
            )

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_texture_alignment.py <citygml_file>")
        print("   or: python verify_texture_alignment.py <directory>")
        sys.exit(1)

    path = Path(sys.argv[1])

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = list(path.rglob("*.gml"))
        if not files:
            print(f"No .gml files found in {path}")
            sys.exit(1)
    else:
        print(f"Path not found: {path}")
        sys.exit(1)

    print(f"Verifying {len(files)} file(s)...")

    total_errors = 0
    total_warnings = 0

    for gml_file in files:
        print(f"\n{'='*80}")
        print(f"Checking: {gml_file.name}")
        print(f"{'='*80}")

        result = verify_alignment(gml_file)
        result.print_summary()

        total_errors += len(result.errors)
        total_warnings += len(result.warnings)

    if len(files) > 1:
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        print(f"Files checked: {len(files)}")
        print(f"Total errors: {total_errors}")
        print(f"Total warnings: {total_warnings}")
        print(f"{'='*80}")

    sys.exit(1 if total_errors > 0 else 0)


if __name__ == "__main__":
    main()
