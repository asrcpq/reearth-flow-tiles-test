#!/usr/bin/env python3
import struct
import json
import sys, shutil
from pathlib import Path
import zipfile

def dump_glb_json(glb_path):
    with open(glb_path, 'rb') as f:
        f.seek(12)  # Skip GLB header
        chunk_length = struct.unpack('<I', f.read(4))[0]
        f.read(4)  # Skip chunk type
        json_data = f.read(chunk_length).decode('utf-8')
        return json.dumps(json.loads(json_data), indent=2)

def load_glb_json(glb_path, new_json):
    new_json += b' ' * ((4 - len(new_json) % 4) % 4)  # Pad to 4-byte alignment

    with open(glb_path, 'rb') as f:
        f.seek(20)  # Skip to after JSON chunk header
        old_json_len = struct.unpack('<I', f.read(-4))[0]
        f.seek(old_json_len, 1)
        remaining = f.read()

    with open(glb_path, 'r+b') as f:
        f.seek(0)
        version, _ = struct.unpack('<II', f.read(8))
        new_len = 12 + 8 + len(new_json) + len(remaining)
        f.seek(0)
        f.write(b'glTF' + struct.pack('<III', version, new_len, len(new_json)) + b'JSON' + new_json + remaining)
        f.truncate()

def dump_glb_dir(p):
    for glb_file in p.rglob("*.glb"):
        json_path = glb_file.with_suffix(".json")
        with open(json_path, 'w', encoding='utf-8') as f:
            f.write(dump_glb_json(glb_file))

def load_glb_dir(p):
    for json_file in p.rglob("*.json"):
        glb_file = json_file.with_suffix(".glb")
        if not glb_file.exists():
            continue
        with open(json_file, 'r', encoding='utf-8') as f:
            new_json = json.dumps(json.loads(f.read()), separators=(',', ':')).encode('utf-8')
        load_glb_json(glb_file, new_json)

# pack zip but ignore *.json if *.glb exists
def pack_zip(zip_path, src_path):
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for file_path in src_path.rglob("*"):
            if file_path.is_file():
                rel_path = file_path.relative_to(src_path)
                if file_path.suffix == ".json":
                    glb_path = file_path.with_suffix(".glb")
                    if glb_path.exists():
                        continue
                zf.write(file_path, rel_path)

if __name__ == "__main__":
    if sys.argv[1] == "dump":
        p = Path(sys.argv[2])
        if p.is_dir():
            dump_glb_dir(p)
        elif p.suffix == ".zip":
            # extract to dir of same name
            dst = p.with_suffix("")
            if dst.exists():
                shutil.rmtree(dst)
            shutil.unpack_archive(p, dst)
            dump_glb_dir(dst)
        else:
            print(dump_glb_json(p))
    elif sys.argv[1] == "load":
        p = Path(sys.argv[2])
        if p.is_dir():
            load_glb_dir(p)
        elif p.suffix == ".zip":
            dst = p.with_suffix("")
            assert dst.exists()
            load_glb_dir(dst)
            pack_zip(p, dst)
        else:
            new_json = json.dumps(json.loads(sys.stdin.read()), separators=(',', ':')).encode('utf-8')
            load_glb_json(p, new_json)
    else:
        raise ValueError("Invalid command")
        sys.exit(1)
