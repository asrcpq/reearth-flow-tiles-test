import json
import struct
from pathlib import Path
from pygltflib import GLTF2
import numpy as np
from shapely.geometry import Polygon
from DracoPy import decode_buffer_to_mesh

def read_b3dm_batch_table(path):
    with open(path, 'rb') as f:
        header = f.read(28)
        if header[:4] != b'b3dm':
            return None
        ft_json_len = struct.unpack('I', header[12:16])[0]
        ft_bin_len = struct.unpack('I', header[16:20])[0]
        bt_json_len = struct.unpack('I', header[20:24])[0]
        bt_bin_len = struct.unpack('I', header[24:28])[0]
        ft_len = ft_json_len + ft_bin_len
        bt_len = bt_json_len + bt_bin_len
        assert bt_len > 0, "No batch table found in B3DM"
        f.seek(28 + ft_len)
        bt_data = f.read(bt_len)
        bt = json.loads(bt_data[:bt_json_len].decode('utf-8'))
        return bt


def read_glb_metadata(path):
    """
    Read structural metadata from a GLB file using EXT_structural_metadata extension.

    Args:
        path: Path to the GLB file

    Returns:
        dict: Property table metadata, or None if no metadata exists
    """
    gltf = GLTF2().load(str(path))
    if not gltf.extensions or 'EXT_structural_metadata' not in gltf.extensions:
        return None
    ext = gltf.extensions['EXT_structural_metadata']
    if not ext.get('propertyTables'):
        return None
    prop_table = ext['propertyTables'][0]
    properties = prop_table['properties']
    buffer_data = gltf.binary_blob()
    result = {}
    for prop_name, prop_info in properties.items():
        values_bv = gltf.bufferViews[prop_info['values']]
        values_data = buffer_data[values_bv.byteOffset:values_bv.byteOffset + values_bv.byteLength]
        if 'stringOffsets' in prop_info:
            offsets_bv = gltf.bufferViews[prop_info['stringOffsets']]
            offsets_data = buffer_data[offsets_bv.byteOffset:offsets_bv.byteOffset + offsets_bv.byteLength]
            offsets = struct.unpack(f'{offsets_bv.byteLength//4}I', offsets_data)
            values = [values_data[offsets[i]:offsets[i+1]].decode('utf-8') for i in range(len(offsets)-1)]
        else:
            values = [values_data]
        result[prop_name] = values
    return result


def extract_draco_geometry(primitive, gltf, buffer_data):
    """
    Extract geometry from Draco-compressed primitive with batch IDs.

    Args:
        primitive: glTF primitive object with Draco compression
        gltf: GLTF2 object
        buffer_data: Binary buffer data

    Returns:
        list: List of tuples (batch_id, Polygon)
    """
    if not primitive.extensions or 'KHR_draco_mesh_compression' not in primitive.extensions:
        return []

    draco_ext = primitive.extensions['KHR_draco_mesh_compression']
    buffer_view_idx = draco_ext['bufferView']
    buffer_view = gltf.bufferViews[buffer_view_idx]

    # Extract Draco compressed data
    offset = buffer_view.byteOffset if buffer_view.byteOffset is not None else 0
    length = buffer_view.byteLength
    draco_data = buffer_data[offset:offset + length]
    draco_mesh = decode_buffer_to_mesh(draco_data)
    positions = draco_mesh.points  # Nx3 array
    faces = draco_mesh.faces  # Mx3 array of triangle indices

    # Extract _BATCHID if available in Draco attributes
    batch_ids = None
    if hasattr(draco_mesh, 'attributes') and '_BATCHID' in draco_mesh.attributes:
        print("set batch ids from attributes")
        batch_ids = draco_mesh.attributes['_BATCHID']
    elif hasattr(draco_mesh, 'point_data') and '_BATCHID' in draco_mesh.point_data:
        print("set batch ids from point_data")
        batch_ids = draco_mesh.point_data['_BATCHID']
    assert batch_ids is not None, "No batch IDs found in Draco mesh"
    print(batch_ids)

    geometries = []
    for face in faces:
        tri_coords = positions[face]
        poly = Polygon(tri_coords)
        if batch_ids is not None and len(face) > 0:
            batch_id = int(batch_ids[face[0]])
        else:
            batch_id = 0
        geometries.append((batch_id, poly))

    return geometries


def extract_geometries_from_gltf(gltf, buffer_data):
    """
    Extract geometries from glTF data as Shapely polygons with batch IDs.
    Supports both uncompressed and Draco-compressed formats.

    Args:
        gltf: GLTF2 object
        buffer_data: Binary buffer data

    Returns:
        list: List of tuples (batch_id, Polygon)
    """
    geometries = []

    for mesh in gltf.meshes:
        for primitive in mesh.primitives:
            # Try Draco compression first
            if hasattr(primitive, 'extensions') and primitive.extensions and 'KHR_draco_mesh_compression' in primitive.extensions:
                draco_geoms = extract_draco_geometry(primitive, gltf, buffer_data)
                print("extracted draco geoms:", len(draco_geoms))
                geometries.extend(draco_geoms)
                continue
            if not hasattr(primitive.attributes, 'POSITION') or primitive.attributes.POSITION is None:
                raise Exception("Primitive has no POSITION attribute")

            pos_idx = primitive.attributes.POSITION
            if pos_idx >= len(gltf.accessors):
                raise Exception("Invalid POSITION accessor index")

            pos_accessor = gltf.accessors[pos_idx]

            # Check if bufferView is None (unsupported format)
            if pos_accessor.bufferView is None:
                raise Exception("Unsupported POSITION accessor with no bufferView")

            pos_buffer_view = gltf.bufferViews[pos_accessor.bufferView]

            # Extract position data
            pos_accessor_offset = pos_accessor.byteOffset
            pos_bv_offset = pos_buffer_view.byteOffset
            offset = pos_bv_offset + pos_accessor_offset
            count = pos_accessor.count
            stride = pos_buffer_view.byteStride
            assert stride >= 12 or stride is None, "Unexpected POSITION accessor stride"
            positions = []
            for i in range(count):
                vertex_offset = offset + i * stride
                vertex = np.frombuffer(
                    buffer_data[vertex_offset:vertex_offset + 12],
                    dtype=np.float32
                )
                positions.append(vertex)
            positions = np.array(positions)

            # disable batch ID extraction for non-draco (FME always use draco)
            assert not hasattr(primitive.attributes, '_BATCHID')

            # Get indices if available
            if primitive.indices is not None:
                if primitive.indices >= len(gltf.accessors):
                    continue
                idx_accessor = gltf.accessors[primitive.indices]

                if idx_accessor.bufferView is None:
                    continue

                idx_buffer_view = gltf.bufferViews[idx_accessor.bufferView]

                idx_accessor_offset = idx_accessor.byteOffset if idx_accessor.byteOffset is not None else 0
                idx_bv_offset = idx_buffer_view.byteOffset if idx_buffer_view.byteOffset is not None else 0
                idx_offset = idx_bv_offset + idx_accessor_offset

                if idx_accessor.componentType == 5123:  # UNSIGNED_SHORT
                    indices = np.frombuffer(
                        buffer_data[idx_offset:idx_offset + idx_accessor.count * 2],
                        dtype=np.uint16
                    )
                elif idx_accessor.componentType == 5125:  # UNSIGNED_INT
                    indices = np.frombuffer(
                        buffer_data[idx_offset:idx_offset + idx_accessor.count * 4],
                        dtype=np.uint32
                    )
                else:
                    continue

                # Group triangles into polygons with batch IDs
                for i in range(0, len(indices), 3):
                    if i + 2 < len(indices):
                        tri_indices = indices[i:i+3]
                        tri_coords = positions[tri_indices]
                        poly = Polygon(tri_coords)
                        batch_id = 0
                        geometries.append((batch_id, poly))

    return geometries


def read_b3dm_file(path):
    metadata = read_b3dm_batch_table(path)
    with open(path, 'rb') as f:
        header = f.read(28)
        ft_json_len = struct.unpack('I', header[12:16])[0]
        ft_bin_len = struct.unpack('I', header[16:20])[0]
        bt_json_len = struct.unpack('I', header[20:24])[0]
        bt_bin_len = struct.unpack('I', header[24:28])[0]
        ft_len = ft_json_len + ft_bin_len
        bt_len = bt_json_len + bt_bin_len
        f.seek(28 + ft_len + bt_len)
        glb_data = f.read()
        gltf = GLTF2().load_from_bytes(glb_data)
        geometries_with_batch = extract_geometries_from_gltf(gltf, gltf.binary_blob())

    return group_by_batch(metadata, geometries_with_batch)

def group_by_batch(metadata, geometries_with_batch):
    result = {}
    n = None
    for key, values in metadata.items():
        if n == None:
            n = len(values)
        else:
            assert n == len(values), f"Inconsistent batch table property lengths: {n} != {len(values)}"
        for idx, v in enumerate(values):
            d = result.setdefault(idx, ({}, []))
            d[0][key] = v

    for batch_id, geom in geometries_with_batch:
        result[batch_id][1].append(geom)

    return result

def read_glb_file(path):
    metadata = read_glb_metadata(path)
    gltf = GLTF2().load(str(path))
    geometries_with_batch = extract_geometries_from_gltf(gltf, gltf.binary_blob())
    return group_by_batch(metadata, geometries_with_batch)