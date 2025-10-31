from shapely.geometry import Polygon, MultiPolygon
from geometry_comparison import compare_geometries


def test_two_triangles_vs_rectangle():
    rect = Polygon([(0, 0), (0.5, 0), (0.5, 0.5), (0, 0.5)])
    tri1 = Polygon([(0, 0), (0.5, 0), (0.5, 0.5)])
    tri2 = Polygon([(0, 0), (0.5, 0.5), (0, 0.5)])
    two_triangles = MultiPolygon([tri1, tri2])

    result = compare_geometries(rect, rect)
    assert result["status"] == "compared"
    assert result["polygon_score"] == 0.0
    assert result["line_score"] < 1e-10, f"Should be ~0: {result['line_score']}"
    assert result["overall_score"] < 1e-10
    print("✓ Rectangle vs itself: all scores ~0.0")

    result = compare_geometries(two_triangles, rect)
    assert result["status"] == "compared"
    assert result["polygon_score"] == 0.0, f"Same area: {result['polygon_score']}"
    assert result["line_score"] > 0.2, f"Should detect diagonal: {result['line_score']}"
    assert result["overall_score"] == result["line_score"]
    print(f"✓ Two triangles vs rectangle: polygon_score={result['polygon_score']:.4f}, line_score={result['line_score']:.4f}")

    result = compare_geometries(tri1, rect)
    assert result["status"] == "compared"
    assert result["polygon_score"] == 0.125, f"Half the rectangle area: {result['polygon_score']}"
    assert result["line_score"] > 0.1
    assert result["overall_score"] == max(result['polygon_score'], result['line_score'])
    print(f"✓ Single triangle vs rectangle: polygon_score={result['polygon_score']:.4f}, line_score={result['line_score']:.4f}")


if __name__ == "__main__":
    test_two_triangles_vs_rectangle()
    print("All tests passed!")
