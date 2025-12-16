import zipfile
import re
import logging
import shutil

def filter_gml_content(content, gml_ids):
    """Filter GML content to only include specific gml:id members."""
    text = content.decode('utf-8')
    lines = text.splitlines(keepends=True)
    filtered_lines = []
    inside_member = False
    member_lines = []

    for line in lines:
        if '<core:cityObjectMember>' in line or '<cityObjectMember>' in line:
            inside_member = True
            member_lines = [line]
            continue

        if '</core:cityObjectMember>' in line or '</cityObjectMember>' in line:
            member_lines.append(line)
            if any(f'gml:id="{gml_id}"' in ''.join(member_lines) for gml_id in gml_ids):
                filtered_lines.extend(member_lines)
            inside_member = False
            member_lines = []
            continue

        if inside_member:
            member_lines.append(line)
        else:
            filtered_lines.append(line)

    return ''.join(filtered_lines).encode('utf-8')

def should_include_path(path, tree):
    """Check if a path should be included based on tree structure."""
    for prefix, items in tree.items():
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            continue

        if not path.startswith(prefix):
            continue

        rest = path[len(prefix):]
        for item in items:
            if rest.startswith(item):
                return True

    return False

def extract_zip_to_structure(src_zip, artifacts_base, testcase_base, name, tree):
    """Extract zip to artifacts (codelists/schemas) and testcase (filtered GML files)."""
    artifact_dir = artifacts_base / "citymodel" / src_zip.stem
    artifact_dir.mkdir(parents=True, exist_ok=True)
    testcase_dir = testcase_base / name / "citymodel"
    try:
        shutil.rmtree(testcase_dir)
    except FileNotFoundError:
        pass

    with zipfile.ZipFile(src_zip, 'r') as zf:
        for item in zf.infolist():
            path = item.filename

            # Skip directories
            if path.endswith('/'):
                continue

            # Extract codelists/ and schemas/ to artifacts
            if path.startswith("codelists/") or path.startswith("schemas/"):
                zf.extract(item, artifact_dir)
                continue

            # Extract and filter GML files to testcase/citymodel/
            if path in tree and isinstance(tree[path], list):
                gml_ids = tree[path]
                content = zf.read(path)
                filtered_content = filter_gml_content(content, gml_ids)
                out_path = testcase_dir / path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(filtered_content)
                continue

            # Extract matching files to testcase/citymodel/
            if should_include_path(path, tree) and not (path.startswith("codelists/") or path.startswith("schemas/")):
                out_path = testcase_dir / path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(zf.read(path))

if __name__ == "__main__":
    import tomllib, sys
    from pathlib import Path
    config_path = Path(sys.argv[1]).resolve()
    with config_path.open("rb") as f:
        config = tomllib.load(f)
    BASE_DIR = Path(__file__).parent.parent / "reearth-flow/engine/plateau-tiles-test"
    test_name = config_path.parent.relative_to(BASE_DIR / "testcases").as_posix()
    citymodel_path = Path(__file__).parent / "data"
    artifacts_base = BASE_DIR / "artifacts"
    testcase_base = BASE_DIR / "testcases"
    src_zip = citymodel_path / config["citygml_zip_name"]
    extract_zip_to_structure(src_zip, artifacts_base, testcase_base, test_name, config["filter"]["tree"])