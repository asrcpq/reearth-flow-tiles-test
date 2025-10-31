from shapely.geometry import MultiLineString
import shapely

def extract_lines(geom):
    if geom is None or geom.is_empty:
        return None

    lines = []
    geom_type = geom.geom_type

    if geom_type in ('Polygon', 'MultiPolygon'):
        polygons = [geom] if geom_type == 'Polygon' else list(geom.geoms)
        for poly in polygons:
            lines.append(poly.exterior)
            lines.extend(poly.interiors)
    elif geom_type in ('LineString', 'LinearRing'):
        lines.append(geom)
    elif geom_type in ('MultiLineString', 'GeometryCollection'):
        for sub_geom in geom.geoms:
            sub_lines = extract_lines(sub_geom)
            if sub_lines:
                if hasattr(sub_lines, 'geoms'):
                    lines.extend(sub_lines.geoms)
                else:
                    lines.append(sub_lines)

    if not lines:
        return None

    return MultiLineString(lines) if len(lines) > 1 else lines[0]

def compare_geometries(geom1, geom2):
    geom_for_type = geom1 if geom1 is not None else geom2
    is_polygon = geom_for_type and geom_for_type.geom_type in ('Polygon', 'MultiPolygon') if geom_for_type else False
    geom_type = "polygon" if is_polygon else "linestring"

    if geom1 is None and geom2 is None:
        return {
            "status": "both_missing",
            "overall_score": 0.0,
            "polygon_score": None,
            "line_score": None,
            "geometry_type": geom_type
        }

    if geom1 is None or geom2 is None:
        single_geom = geom2 if geom1 is None else geom1
        size = single_geom.area if is_polygon else single_geom.length
        return {
            "status": "only2" if geom1 is None else "only1",
            "overall_score": size,
            "polygon_score": None,
            "line_score": None,
            "geometry_type": geom_type
        }

    polygon_score = None
    if is_polygon:
        try:
            sym_diff = geom1.symmetric_difference(geom2)
            polygon_score = sym_diff.area if not sym_diff.is_empty else 0.0
        except:
            pass

    line_score = None
    lines1 = extract_lines(geom1)
    lines2 = extract_lines(geom2)
    if lines1 and lines2:
        try:
            line_score = shapely.hausdorff_distance(lines1, lines2, densify=0.01)
        except:
            pass

    overall = max(polygon_score or 0.0, line_score or 0.0) if is_polygon else (line_score or 0.0)

    return {
        "status": "compared",
        "overall_score": overall,
        "polygon_score": polygon_score,
        "line_score": line_score,
        "geometry_type": geom_type
    }