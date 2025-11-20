#!/usr/bin/env python3
import xml.etree.ElementTree as ET
from typing import List, Dict, Set, Tuple
from collections import defaultdict


def extract_namespaces(gml_file: str) -> Dict[str, str]:
    namespaces = {}
    for event, data in ET.iterparse(gml_file, events=['start-ns']):
        prefix, uri = data
        if prefix:
            namespaces[prefix] = uri
        else:
            namespaces['_default'] = uri
    return namespaces


def get_textured_polygon_ids(tree: ET.ElementTree, namespaces: Dict[str, str]) -> Set[str]:
    textured_polygons = set()
    root = tree.getroot()
    app_ns = namespaces.get('app', '')
    for appearance in root.findall(f'.//{{{app_ns}}}appearanceMember/{{{app_ns}}}Appearance'):
        for target in appearance.findall(f'.//{{{app_ns}}}target'):
            target_text = target.text
            if target_text and target_text.startswith('#'):
                polygon_id = target_text[1:]
                textured_polygons.add(polygon_id)
    return textured_polygons


def find_elements_containing_polygons(root: ET.Element, polygon_ids: Set[str], namespaces: Dict[str, str]) -> Dict[str, Set[str]]:
    element_to_polygons = defaultdict(set)
    gml_ns = namespaces.get('gml', '')
    for elem in root.iter():
        elem_id = elem.get(f'{{{gml_ns}}}id')
        if not elem_id:
            continue
        for polygon in elem.findall(f'.//{{{gml_ns}}}Polygon[@{{{gml_ns}}}id]'):
            polygon_id = polygon.get(f'{{{gml_ns}}}id')
            if polygon_id in polygon_ids:
                element_to_polygons[elem_id].add(polygon_id)
    return element_to_polygons


def find_parent_relationships(root: ET.Element, element_ids: Set[str], namespaces: Dict[str, str]) -> Dict[str, str]:
    child_to_parent = {}
    gml_ns = namespaces.get('gml', '')
    id_to_elem = {}
    for elem in root.iter():
        elem_id = elem.get(f'{{{gml_ns}}}id')
        if elem_id and elem_id in element_ids:
            id_to_elem[elem_id] = elem
    for child_id, child_elem in id_to_elem.items():
        for ancestor in root.iter():
            ancestor_id = ancestor.get(f'{{{gml_ns}}}id')
            if not ancestor_id or ancestor_id == child_id:
                continue
            if ancestor_id in element_ids:
                for descendant in ancestor.iter():
                    if descendant is child_elem:
                        if child_id not in child_to_parent:
                            child_to_parent[child_id] = ancestor_id
                        break
    return child_to_parent


def get_feature_type(elem: ET.Element) -> str:
    tag = elem.tag
    if '}' in tag:
        return tag.split('}')[1]
    return tag


def get_textured_features(gml_file: str) -> List[Tuple[str, str, str]]:
    namespaces = extract_namespaces(gml_file)
    tree = ET.parse(gml_file)
    textured_polygons = get_textured_polygon_ids(tree, namespaces)
    if not textured_polygons:
        return []
    root = tree.getroot()
    element_to_polygons = find_elements_containing_polygons(root, textured_polygons, namespaces)
    if not element_to_polygons:
        return []
    element_ids = set(element_to_polygons.keys())
    child_to_parent = find_parent_relationships(root, element_ids, namespaces)
    parent_ids = set(child_to_parent.values())
    innermost_ids = element_ids - parent_ids
    result = []
    gml_ns = namespaces.get('gml', '')
    id_to_elem = {}
    for elem in root.iter():
        elem_id = elem.get(f'{{{gml_ns}}}id')
        if elem_id in innermost_ids:
            id_to_elem[elem_id] = elem
    for elem_id in sorted(innermost_ids):
        if elem_id in id_to_elem:
            feature_type = get_feature_type(id_to_elem[elem_id])
            parent_id = child_to_parent.get(elem_id, '')
            result.append((elem_id, feature_type, parent_id))
    return result


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 2:
        print("Usage: python appearance.py <gml_file>")
        sys.exit(1)
    gml_file = sys.argv[1]
    namespaces = extract_namespaces(gml_file)
    print(f"Extracted namespaces: {namespaces}")
    textured_features = get_textured_features(gml_file)
    print(f"\nFound {len(textured_features)} innermost textured features:")
    print("-" * 80)
    for gml_id, feature_type, parent_id in textured_features:
        if parent_id:
            print(f"{feature_type:20s} {gml_id:50s} parent: {parent_id}")
        else:
            print(f"{feature_type:20s} {gml_id}")
