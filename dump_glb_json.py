#!/usr/bin/env python3
import struct
import json
import sys

def dump_glb_json(glb_path):
    with open(glb_path, 'rb') as f:
        # Read GLB header (12 bytes)
        magic = f.read(4)
        if magic != b'glTF':
            print("Error: Not a valid GLB file")
            return
        
        version = struct.unpack('<I', f.read(4))[0]
        length = struct.unpack('<I', f.read(4))[0]
        
        # Read first chunk (JSON)
        chunk_length = struct.unpack('<I', f.read(4))[0]
        chunk_type = f.read(4)
        
        if chunk_type == b'JSON':
            json_data = f.read(chunk_length).decode('utf-8')
            parsed = json.loads(json_data)
            print(json.dumps(parsed, indent=2))
        else:
            print("Error: First chunk is not JSON")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python glb_json_dump.py <file.glb>")
        sys.exit(1)
    
    dump_glb_json(sys.argv[1])
