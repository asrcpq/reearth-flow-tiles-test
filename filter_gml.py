#!/usr/bin/env python3
import zipfile
import tempfile
import re
from pathlib import Path

UNLINK_NON_GML = True

def find_matching_gml_ids(content, id_substrings):
    matched_ids = set()
    for id_substring in id_substrings:
        pattern = r'gml:id="([^"]*' + re.escape(id_substring) + r'[^"]*)"'
        matched_ids.update(re.findall(pattern, content))
    return matched_ids


def extract_matching_objects(gml_file_path, id_substrings):
    with open(gml_file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    matched_ids = find_matching_gml_ids(content, id_substrings)
    if not matched_ids:
        return None, []

    lines = content.split('\n')
    result_lines = []
    inside_member = False
    current_member_lines = []
    keep_current_member = False

    for line in lines:
        if '<core:cityObjectMember>' in line or '<cityObjectMember>' in line:
            inside_member = True
            current_member_lines = [line]
            keep_current_member = False
            continue

        if '</core:cityObjectMember>' in line or '</cityObjectMember>' in line:
            current_member_lines.append(line)
            if keep_current_member:
                result_lines.extend(current_member_lines)
            inside_member = False
            current_member_lines = []
            keep_current_member = False
            continue

        if inside_member:
            current_member_lines.append(line)
            for matched_id in matched_ids:
                if f'gml:id="{matched_id}"' in line:
                    keep_current_member = True
                    break
        else:
            result_lines.append(line)

    return '\n'.join(result_lines), matched_ids


def filter_gml_objects(src_zip, dst_zip, id_substrings):
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        extract_path = temp_path / "extracted"
        extract_path.mkdir()

        print("extracting", src_zip, "to", extract_path)
        with zipfile.ZipFile(src_zip, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

        udx_path = extract_path / "udx"
        files = list(udx_path.glob("**/*"))
        all_matched_ids = []
        for file in files:
            if not file.is_file():
                continue
            if file.suffix.lower() == '.gml':
                modified_content, matched_ids = extract_matching_objects(file, id_substrings)
                if matched_ids:
                    print("found ids:", matched_ids, "in", file)
                    with open(file, 'w', encoding='utf-8') as f:
                        f.write(modified_content)
                    all_matched_ids.extend(matched_ids)
                else:
                    file.unlink()
            elif UNLINK_NON_GML := True:
                file.unlink()

        if not all_matched_ids:
            raise ValueError(f"No GML objects with id containing {id_substrings} found")

        print("writing to", dst_zip)
        Path(dst_zip).parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dst_zip, 'w', zipfile.ZIP_DEFLATED) as zip_ref:
            for file_path in extract_path.rglob('*'):
                if file_path.is_file():
                    zip_ref.write(file_path, file_path.relative_to(extract_path))