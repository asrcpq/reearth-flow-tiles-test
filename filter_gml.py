#!/usr/bin/env python3
import zipfile
import re

def filter_gml_content(content, id_set):
    lines = content.decode('utf-8').splitlines(keepends=True)
    result_lines = []
    inside_member = False
    current_member_lines = []
    keep_current_member = False
    matched_ids = set()
    
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
            if not keep_current_member and 'gml:id="' in line:
                match = re.search(r'gml:id="([^"]+)"', line)
                if match and match.group(1) in id_set:
                    keep_current_member = True
                    matched_ids.add(match.group(1))
        else:
            result_lines.append(line)
    
    return ''.join(result_lines).encode('utf-8'), matched_ids

def filter_gml_objects(src_zip, dst_zip, filter_dict):
    all_matched_ids = []
    
    with zipfile.ZipFile(src_zip, 'r') as src, zipfile.ZipFile(dst_zip, 'w', zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            if item.is_dir():
                continue
            filename = item.filename
            if not filename.startswith("udx/"):
                dst.writestr(item, src.read(item))
                continue
            for key, value in filter_dict.items():
                if filename.startswith(f"udx/{key}/") or filename == f"udx/{key}":
                    break
            else:
                continue

			# only lists are interpreted as ID filters
            if not isinstance(value, list):
                dst.writestr(item, src.read(item))
                continue
            if not filename.endswith('.gml'):
                raise ValueError(f"Filtering by IDs is only supported for GML files, but got: {filename}")
            
            id_set = set(filter_ids)
            content = src.read(item)
            modified_content, matched_ids = filter_gml_content(content, id_set)
            if matched_ids:
                print(f"  found {len(matched_ids)} matching IDs")
                dst.writestr(item, modified_content)
                all_matched_ids.extend(matched_ids)
            else:
                raise ValueError(f"No matching IDs found in {filename}")
    
    print("written to", dst_zip)