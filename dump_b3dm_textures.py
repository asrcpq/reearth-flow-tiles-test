import struct
import json
import sys
import os

# b3dm header: magic(4) + version(4) + byteLength(4) +
#   featureTableJSONByteLength(4) + featureTableBinaryByteLength(4) +
#   batchTableJSONByteLength(4)   + batchTableBinaryByteLength(4) = 28 bytes
HEADER = 28
EXTS = {'image/webp': 'webp', 'image/jpeg': 'jpg', 'image/png': 'png'}


def dump_textures(path):
    with open(path, 'rb') as f:
        data = f.read()

    feat_json, feat_bin, batch_json, batch_bin = struct.unpack_from('<4I', data, 12)
    glb = data[HEADER + feat_json + feat_bin + batch_json + batch_bin:]

    # GLB chunks
    chunk0_len, _ = struct.unpack_from('<II', glb, 12)
    json_data = json.loads(glb[20:20 + chunk0_len])

    bin_off = 20 + chunk0_len
    chunk1_len, _ = struct.unpack_from('<II', glb, bin_off)
    bin_data = glb[bin_off + 8:bin_off + 8 + chunk1_len]

    stem = os.path.splitext(os.path.basename(path))[0]

    for i, img in enumerate(json_data.get('images', [])):
        bv = json_data['bufferViews'][img['bufferView']]
        blob = bin_data[bv['byteOffset']:bv['byteOffset'] + bv['byteLength']]
        name = img.get('name', f'{stem}_img{i}')
        ext = EXTS.get(img.get('mimeType', ''), 'bin')
        out_path = f'{name}.{ext}'
        with open(out_path, 'wb') as out:
            out.write(blob)
        print(out_path)


for input_path in sys.argv[1:]:
    dump_textures(input_path)
