#!/usr/bin/env python3
"""
Creates a CityGML stress test with overlapping textured polygons.

The script generates 64 solid-color textures, each with a randomized hue and a
fixed size of 64x64 pixels, then maps each one onto its own polygon. All
polygons occupy the same world-space area so the textures fully overlap. This
is useful for checking whether FME:

- has a memory explosion problem when processing many textures
- truly uses exactly one atlas regardless of texture amount

Usage:
    python create_atlas_crop_test.py <output_dir>
"""

import colorsys
import os
import random
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")


TEXTURE_COUNT = 64
TEXTURE_SIZE = 64
RANDOM_SEED = 42
POLYGON_WIDTH = 1.0
POLYGON_HEIGHT = 1.0


def create_texture(path: str, width: int, height: int, color: tuple[int, int, int]) -> None:
    img = Image.new("RGB", (width, height), color)
    img.save(path, "JPEG", quality=90)


def generate_specs() -> list[tuple[str, int, int, tuple[int, int, int]]]:
    rng = random.Random(RANDOM_SEED)
    specs = []
    total = TEXTURE_COUNT

    for index in range(total):
        width = TEXTURE_SIZE
        height = TEXTURE_SIZE
        hue = rng.random()
        r, g, b = colorsys.hsv_to_rgb(hue, 0.75, 0.9)
        color = (int(r * 255), int(g * 255), int(b * 255))
        texture_name = f"tex_{index:04d}_{width}x{height}.jpg"
        specs.append((texture_name, width, height, color))

    return specs


def create_gml(
    out_dir: str,
    specs: list[tuple[str, int, int, tuple[int, int, int]]],
) -> str:
    wall_blocks = []
    texture_blocks = []
    max_x = 35.0
    max_y = 135.0
    max_z = POLYGON_HEIGHT

    for index, (texture_name, _, _, _) in enumerate(specs):
        x0 = 35.0
        x1 = x0 + POLYGON_WIDTH * 0.001
        y0 = 135.0
        y1 = y0 + 0.001
        z0 = 0.0
        z1 = z0 + POLYGON_HEIGHT
        max_x = max(max_x, x1)
        max_y = max(max_y, y1)
        max_z = max(max_z, z1)

        polygon_id = f"poly-wall-{index}"
        ring_id = f"ring-wall-{index}"
        wall_id = f"wall-{index}"

        wall_blocks.append(
            f"""\
      <bldg:boundedBy>
        <bldg:WallSurface gml:id="{wall_id}">
          <bldg:lod2MultiSurface>
            <gml:MultiSurface>
              <gml:surfaceMember>
                <gml:Polygon gml:id="{polygon_id}">
                  <gml:exterior>
                    <gml:LinearRing gml:id="{ring_id}">
                      <gml:posList srsDimension="3">
                        {x0:.3f}  {y0:.3f}  {z0:.1f}
                        {x1:.3f}  {y0:.3f}  {z0:.1f}
                        {x1:.3f}  {y0:.3f}  {z1:.1f}
                        {x0:.3f}  {y0:.3f}  {z1:.1f}
                        {x0:.3f}  {y0:.3f}  {z0:.1f}
                      </gml:posList>
                    </gml:LinearRing>
                  </gml:exterior>
                </gml:Polygon>
              </gml:surfaceMember>
            </gml:MultiSurface>
          </bldg:lod2MultiSurface>
        </bldg:WallSurface>
      </bldg:boundedBy>"""
        )

        texture_blocks.append(
            f"""\
      <app:surfaceDataMember>
        <app:ParameterizedTexture>
          <app:imageURI>appearance/{texture_name}</app:imageURI>
          <app:mimeType>image/jpeg</app:mimeType>
          <app:wrapMode>none</app:wrapMode>
          <app:target uri="#{polygon_id}">
            <app:TexCoordList>
              <app:textureCoordinates ring="#{ring_id}">0.0 0.0  1.0 0.0  1.0 1.0  0.0 1.0  0.0 0.0</app:textureCoordinates>
            </app:TexCoordList>
          </app:target>
        </app:ParameterizedTexture>
      </app:surfaceDataMember>"""
        )

    content = f"""\
<?xml version='1.0' encoding='UTF-8'?>
<core:CityModel
    xmlns:app="http://www.opengis.net/citygml/appearance/2.0"
    xmlns:bldg="http://www.opengis.net/citygml/building/2.0"
    xmlns:core="http://www.opengis.net/citygml/2.0"
    xmlns:gml="http://www.opengis.net/gml"
    xmlns:xlink="http://www.w3.org/1999/xlink"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">

  <gml:boundedBy>
    <gml:Envelope srsName="http://www.opengis.net/def/crs/EPSG/0/6697" srsDimension="3">
      <gml:lowerCorner>35.0 135.0 0.0</gml:lowerCorner>
      <gml:upperCorner>{max_x:.3f} {max_y:.3f} {max_z:.1f}</gml:upperCorner>
    </gml:Envelope>
  </gml:boundedBy>

  <core:cityObjectMember>
    <bldg:Building gml:id="bldg-atlas-crop-test">
{os.linesep.join(wall_blocks)}
    </bldg:Building>
  </core:cityObjectMember>

  <core:appearanceMember>
    <app:Appearance>
      <app:theme>rgbTexture</app:theme>
{os.linesep.join(texture_blocks)}
    </app:Appearance>
  </core:appearanceMember>

</core:CityModel>
"""
    gml_path = os.path.join(out_dir, "test_atlas_crop.gml")
    with open(gml_path, "w", encoding="utf-8") as f:
        f.write(content)
    return gml_path


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <output_dir>", file=sys.stderr)
        sys.exit(1)

    out_dir = sys.argv[1]
    appearance_dir = os.path.join(out_dir, "appearance")
    os.makedirs(appearance_dir, exist_ok=True)

    specs = generate_specs()
    for texture_name, width, height, color in specs:
        create_texture(os.path.join(appearance_dir, texture_name), width, height, color)

    gml_path = create_gml(out_dir, specs)

    print(f"GML      : {gml_path}")
    print(f"Textures : {len(specs)}")
    print(f"Tex size : {TEXTURE_SIZE} x {TEXTURE_SIZE}")
    print(f"Seed     : {RANDOM_SEED}")
    print(f"World sz : {POLYGON_WIDTH} x {POLYGON_HEIGHT} (overlapped)")


if __name__ == "__main__":
    main()
