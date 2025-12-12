import struct
import json
import sys

with open(sys.argv[1], 'rb') as f:
    magic, version, length = struct.unpack('<III', f.read(12))
    chunk_len, chunk_type = struct.unpack('<II', f.read(8))
    json_data = json.loads(f.read(chunk_len))
    
    chunk_len, chunk_type = struct.unpack('<II', f.read(8))
    bin_data = f.read(chunk_len)
    
    for i, img in enumerate(json_data.get('images', [])):
        bv = json_data['bufferViews'][img['bufferView']]
        data = bin_data[bv['byteOffset']:bv['byteOffset'] + bv['byteLength']]
        name = img.get('name', f'texture_{i}')
        ext = img.get('mimeType', 'image/png').split('/')[-1]
        with open(f'{name}.{ext}', 'wb') as out:
            out.write(data)
        print(f'{name}.{ext}')
