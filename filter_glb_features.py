import sys
import json
import struct
from pathlib import Path

def read_glb(glb_path):
    """Read GLB file and return JSON header and binary data."""
    with open(glb_path, 'rb') as f:
        # Read GLB header
        magic = struct.unpack('<I', f.read(4))[0]
        version = struct.unpack('<I', f.read(4))[0]
        length = struct.unpack('<I', f.read(4))[0]

        # Read JSON chunk
        json_length = struct.unpack('<I', f.read(4))[0]
        json_type = struct.unpack('<I', f.read(4))[0]
        json_data = json.loads(f.read(json_length).decode('utf-8'))

        # Read binary chunk
        bin_data = None
        if f.tell() < length:
            bin_length = struct.unpack('<I', f.read(4))[0]
            bin_type = struct.unpack('<I', f.read(4))[0]
            bin_data = bytearray(f.read(bin_length))

        return json_data, bin_data

def write_glb(glb_path, json_data, bin_data):
    """Write GLB file."""
    with open(glb_path, 'wb') as f:
        json_str = json.dumps(json_data, separators=(',', ':')).encode('utf-8')
        json_padding = (4 - len(json_str) % 4) % 4
        json_str += b' ' * json_padding

        bin_padding = (4 - len(bin_data) % 4) % 4
        padded_bin = bin_data + b'\x00' * bin_padding

        total_length = 12 + 8 + len(json_str) + 8 + len(padded_bin)

        # Write GLB header
        f.write(struct.pack('<I', 0x46546C67))  # 'glTF'
        f.write(struct.pack('<I', 2))
        f.write(struct.pack('<I', total_length))

        # Write JSON chunk
        f.write(struct.pack('<I', len(json_str)))
        f.write(struct.pack('<I', 0x4E4F534A))  # 'JSON'
        f.write(json_str)

        # Write binary chunk
        f.write(struct.pack('<I', len(padded_bin)))
        f.write(struct.pack('<I', 0x004E4942))  # 'BIN\0'
        f.write(padded_bin)

def read_property_from_buffer(bin_data, buffer_view, component_type, count):
    """Read property values from binary buffer."""
    formats = {
        5120: ('b', 1),   # BYTE
        5121: ('B', 1),   # UNSIGNED_BYTE
        5122: ('h', 2),   # SHORT
        5123: ('H', 2),   # UNSIGNED_SHORT
        5125: ('I', 4),   # UNSIGNED_INT
        5126: ('f', 4),   # FLOAT
    }

    assert component_type in formats, f"Unsupported component type: {component_type}"

    fmt, size = formats[component_type]
    offset = buffer_view.get('byteOffset', 0)
    values = []

    for i in range(count):
        pos = offset + i * size
        value = struct.unpack('<' + fmt, bin_data[pos:pos + size])[0]
        values.append(value)

    return values

def read_string_from_buffer(bin_data, buffer_view, string_offsets_view, count):
    """Read string property values from binary buffer."""
    # Read string offsets
    offset_bv_offset = string_offsets_view.get('byteOffset', 0)
    offsets = []
    for i in range(count + 1):
        pos = offset_bv_offset + i * 4
        offset = struct.unpack('<I', bin_data[pos:pos + 4])[0]
        offsets.append(offset)

    # Read strings
    string_bv_offset = buffer_view.get('byteOffset', 0)
    strings = []
    for i in range(count):
        start = string_bv_offset + offsets[i]
        end = string_bv_offset + offsets[i + 1]
        string_bytes = bin_data[start:end]
        strings.append(string_bytes.decode('utf-8'))

    return strings

def filter_glb_features(glb_path, exclude_types):
    """Filter features by overwriting feature IDs in vertex attributes."""
    json_data, bin_data = read_glb(glb_path)
    assert bin_data is not None, "GLB file must contain binary data."

    metadata = json_data.get('extensions', {}).get('EXT_structural_metadata', {})
    assert metadata, "No EXT_structural_metadata found in GLB."

    # Step 1: Build filtered feature ID list
    excluded_feature_ids = set()

    property_tables = metadata.get('propertyTables', [])
    buffer_views = json_data.get('bufferViews', [])

    for table_idx, table in enumerate(property_tables):
        assert 'properties' in table, f"Table {table_idx} missing 'properties'"
        assert 'feature_type' in table['properties'], f"Table {table_idx} missing 'feature_type' property"

        count = table['count']
        feature_type_prop = table['properties']['feature_type']

        # Read feature_type values
        assert 'values' in feature_type_prop, "feature_type property missing 'values'"
        values_bv_idx = feature_type_prop['values']
        values_bv = buffer_views[values_bv_idx]

        # Check if it's a string property
        if 'stringOffsets' in feature_type_prop:
            string_offsets_bv_idx = feature_type_prop['stringOffsets']
            string_offsets_bv = buffer_views[string_offsets_bv_idx]
            feature_types = read_string_from_buffer(bin_data, values_bv, string_offsets_bv, count)
        else:
            # Numeric property
            component_type = feature_type_prop['componentType']
            feature_types = read_property_from_buffer(bin_data, values_bv, component_type, count)

        # Find which feature IDs have excluded types
        for feature_id, feature_type in enumerate(feature_types):
            if feature_type in exclude_types:
                excluded_feature_ids.add(feature_id)

    print(excluded_feature_ids)
    if not excluded_feature_ids:
        return
    # assert excluded_feature_ids, "No features found with excluded types"

    # Step 2: Overwrite feature IDs in vertex attributes
    accessors = json_data.get('accessors', [])
    for mesh in json_data.get('meshes', []):
        for primitive in mesh.get('primitives', []):
            attributes = primitive.get('attributes', {})
            assert '_FEATURE_ID_0' in attributes, "No _FEATURE_ID_0 in primitive attributes."
            accessor_idx = attributes['_FEATURE_ID_0']
            accessor = accessors[accessor_idx]

            buffer_view_idx = accessor['bufferView']
            buffer_view = buffer_views[buffer_view_idx]
            component_type = accessor['componentType']
            count = accessor['count']

            formats = {
                5120: ('b', 1), 5121: ('B', 1),
                5122: ('h', 2), 5123: ('H', 2),
                5125: ('I', 4),
            }

            assert component_type in formats, f"Unsupported component type: {component_type}"

            fmt, size = formats[component_type]
            offset = buffer_view.get('byteOffset', 0) + accessor.get('byteOffset', 0)

            # Read, modify, and write back feature IDs
            for i in range(count):
                pos = offset + i * size
                feature_id = struct.unpack('<' + fmt, bin_data[pos:pos + size])[0]
                if feature_id in excluded_feature_ids:
                    # Overwrite with -1 (or max value for unsigned types)
                    if fmt in ['B', 'H', 'I']:
                        new_value = (2 ** (size * 8)) - 1  # Max unsigned value
                    else:
                        new_value = -1
                    struct.pack_into('<' + fmt, bin_data, pos, new_value)

    # Write back
    write_glb(glb_path, json_data, bin_data)

    # Update paired JSON if exists
    json_file = glb_path.with_suffix('.json')
    if json_file.exists():
        with open(json_file, 'w') as f:
            json.dump(json_data, f, separators=(',', ':'))

if __name__ == "__main__":
    path = Path(sys.argv[1])
    exclude_types = set(sys.argv[2:])
    for glb_file in path.rglob("*.glb"):
        filter_glb_features(glb_file, exclude_types)