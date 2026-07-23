"""Dump GLB textures into a self-contained HTML that renders them with WebGL.

Unlike dump_glb_textures.py (which writes raw image bytes to files), this keeps
each texture *as-is* and hands it to the GPU: KTX2/Basis images are transcoded
and uploaded by three.js's KTX2Loader, PNG/JPEG go through a normal texture
load. Nothing is decoded or re-encoded in Python, so what you see is what the
writer actually emitted (block-compressed atlases included).

Usage:
    python dump_ktx_textures.py <in.glb> <out.html>
"""

import base64
import json
import struct
import sys
from pathlib import Path


def read_glb_images(path):
    """Yield (name, mime_type, bytes) for every image embedded in a GLB."""
    with open(path, "rb") as f:
        magic, version, length = struct.unpack("<III", f.read(12))
        if magic != 0x46546C67:
            raise ValueError(f"{path}: not a GLB (bad magic)")

        json_data = None
        bin_data = None
        while True:
            header = f.read(8)
            if len(header) < 8:
                break
            chunk_len, chunk_type = struct.unpack("<II", header)
            data = f.read(chunk_len)
            if chunk_type == 0x4E4F534A:  # 'JSON'
                json_data = json.loads(data)
            elif chunk_type == 0x004E4942:  # 'BIN\0'
                bin_data = data

    if json_data is None:
        raise ValueError(f"{path}: no JSON chunk")

    for i, img in enumerate(json_data.get("images", [])):
        mime = img.get("mimeType", "image/png")
        name = img.get("name", f"texture_{i}")
        if "bufferView" in img:
            bv = json_data["bufferViews"][img["bufferView"]]
            off = bv.get("byteOffset", 0)
            data = bin_data[off:off + bv["byteLength"]]
        elif "uri" in img and img["uri"].startswith("data:"):
            data = base64.b64decode(img["uri"].split(",", 1)[1])
        else:
            # external uri; resolve relative to the glb
            data = (Path(path).parent / img["uri"]).read_bytes()
        yield name, mime, data


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    glb, output = sys.argv[1], sys.argv[2]

    stem = Path(glb).stem
    textures = []
    for name, mime, data in read_glb_images(glb):
        textures.append({
            "file": stem,
            "name": name,
            "mime": mime,
            "bytes": len(data),
            "b64": base64.b64encode(data).decode("ascii"),
        })
        print(f"{stem} > {name}  {mime}  {len(data)} bytes")

    if not textures:
        print("no images found")
        return

    template = (Path(__file__).parent / "ktx_textures_template.html").read_text(encoding="utf-8")
    html = template.replace("{{TEXTURES}}", json.dumps(textures))
    Path(output).write_text(html, encoding="utf-8")
    print(f"\nwrote {output} ({len(textures)} texture(s))")


if __name__ == "__main__":
    main()
