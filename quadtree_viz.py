#!/usr/bin/env python3
"""Read a 3D Tiles 1.1 implicit-tiling tileset (QUADTREE) and render a
self-contained HTML map of every occupied cell: its geographic region,
feature count (from EXT_structural_metadata property tables), and content
file size on disk.

Usage:
    python3 quadtree_viz.py <tileset.json> [output.html]
"""
import json
import math
import struct
import sys
from pathlib import Path

MAGIC = b"subt"


def read_subtree(path):
    data = path.read_bytes()
    assert data[:4] == MAGIC, f"not a subtree file: {path}"
    version = struct.unpack_from("<I", data, 4)[0]
    json_len, bin_len = struct.unpack_from("<QQ", data, 8)
    assert version == 1
    json_start = 24
    js = json.loads(data[json_start:json_start + json_len].decode("utf-8"))
    bin_start = json_start + json_len
    binary = data[bin_start:bin_start + bin_len]
    return js, binary


def bit(binary, buffer_views, buffer_view_idx, index):
    bv = buffer_views[buffer_view_idx]
    byte_off = bv.get("byteOffset", 0)
    i = index
    b = binary[byte_off + i // 8]
    return (b >> (i % 8)) & 1


def level_offset(level):
    return (4 ** level - 1) // 3


def morton2d(x, y):
    def spread(v):
        x = v & 0xFFFFFFFF
        x = (x | (x << 16)) & 0x0000FFFF0000FFFF
        x = (x | (x << 8)) & 0x00FF00FF00FF00FF
        x = (x | (x << 4)) & 0x0F0F0F0F0F0F0F0F
        x = (x | (x << 2)) & 0x3333333333333333
        x = (x | (x << 1)) & 0x5555555555555555
        return x
    return spread(x) | (spread(y) << 1)


class Bitstream:
    """Wraps a subtree's availability entry: either {"constant": 0|1} or
    {"bitstream": N, "availableCount": ...} indexing into `buffer_views`."""

    def __init__(self, entry, binary, buffer_views):
        self.constant = entry.get("constant")
        self.bitstream = entry.get("bitstream")
        self.binary = binary
        self.buffer_views = buffer_views

    def get(self, index):
        if self.constant is not None:
            return self.constant
        return bit(self.binary, self.buffer_views, self.bitstream, index)


def load_glb_feature_count(path):
    """Sum of EXT_structural_metadata propertyTables[*].count in a GLB."""
    try:
        with open(path, "rb") as f:
            f.seek(12)
            chunk_len = struct.unpack("<I", f.read(4))[0]
            f.read(4)
            js = json.loads(f.read(chunk_len).decode("utf-8"))
    except Exception:
        return None
    tables = js.get("extensions", {}).get("EXT_structural_metadata", {}).get(
        "propertyTables", []
    )
    if not tables:
        return None
    return sum(t.get("count", 0) for t in tables)


def region_for(root_region, level, x, y):
    """root_region = [west, south, east, north] in radians; cell region in
    degrees, subdividing evenly (QUADTREE: 2^level cells per axis)."""
    west, south, east, north = root_region
    n = 2 ** level
    dx = (east - west) / n
    dy = (north - south) / n
    return {
        "west": math.degrees(west + x * dx),
        "east": math.degrees(west + (x + 1) * dx),
        "south": math.degrees(south + y * dy),
        "north": math.degrees(south + (y + 1) * dy),
    }


def walk_subtree(base_dir, subtrees_uri_template, content_uri_templates,
                  root_region, subtree_levels, root_level, root_x, root_y,
                  out_tiles, seen_files, warnings):
    uri = subtrees_uri_template.format(level=root_level, x=root_x, y=root_y)
    path = base_dir / uri
    if not path.exists():
        warnings.append(f"missing subtree file: {uri}")
        return
    js, binary = read_subtree(path)
    buffer_views = js["bufferViews"]
    tile_avail = Bitstream(js["tileAvailability"], binary, buffer_views)
    content_avails = [
        Bitstream(e, binary, buffer_views) for e in js.get("contentAvailability", [])
    ]
    child_avail_entry = js.get("childSubtreeAvailability")
    child_avail = Bitstream(child_avail_entry, binary, buffer_views) if child_avail_entry else None

    for rel_level in range(subtree_levels):
        n = 2 ** rel_level
        base_idx = level_offset(rel_level)
        for ry in range(n):
            for rx in range(n):
                idx = base_idx + morton2d(rx, ry)
                if not tile_avail.get(idx):
                    continue
                level = root_level + rel_level
                ax = (root_x << rel_level) | rx
                ay = (root_y << rel_level) | ry
                region = region_for(root_region, level, ax, ay)
                for slot, ca in enumerate(content_avails):
                    if not ca.get(idx):
                        continue
                    uri_tpl = content_uri_templates[slot]
                    content_uri = uri_tpl.format(level=level, x=ax, y=ay)
                    fpath = base_dir / content_uri
                    key = str(fpath)
                    if key in seen_files:
                        continue
                    seen_files.add(key)
                    if not fpath.exists():
                        warnings.append(f"missing content file: {content_uri}")
                        continue
                    size = fpath.stat().st_size
                    feat_count = load_glb_feature_count(fpath)
                    out_tiles.append({
                        "level": level, "x": ax, "y": ay, "slot": slot,
                        "region": region, "size": size,
                        "features": feat_count, "uri": content_uri,
                    })

    # Chained subtrees, rooted one level past this file's window.
    if child_avail is not None:
        child_level = root_level + subtree_levels
        n = 2 ** subtree_levels
        for ry in range(n):
            for rx in range(n):
                idx = morton2d(rx, ry)
                if not child_avail.get(idx):
                    continue
                cx = (root_x << subtree_levels) | rx
                cy = (root_y << subtree_levels) | ry
                walk_subtree(
                    base_dir, subtrees_uri_template, content_uri_templates,
                    root_region, subtree_levels, child_level, cx, cy,
                    out_tiles, seen_files, warnings,
                )


def parse_tileset(tileset_path):
    tileset = json.loads(tileset_path.read_text())
    root_tile = tileset["root"]
    region = root_tile["boundingVolume"]["region"][:4]  # west,south,east,north (radians)
    implicit = root_tile["implicitTiling"]
    subtree_levels = implicit["subtreeLevels"]
    subtrees_uri_template = implicit["subtrees"]["uri"]

    if "contents" in root_tile:
        content_uri_templates = [c["uri"] for c in root_tile["contents"]]
    else:
        content_uri_templates = [root_tile["content"]["uri"]]

    return region, subtree_levels, subtrees_uri_template, content_uri_templates


def build_html(tiles, region, warnings, title):
    west, south, east, north = (math.degrees(v) for v in region)
    center_lat = (south + north) / 2
    center_lon = (west + east) / 2
    data = json.dumps(tiles)
    warn_html = "".join(f"<li>{w}</li>" for w in warnings[:50])
    more = f"<li>... and {len(warnings) - 50} more</li>" if len(warnings) > 50 else ""

    return f"""<!doctype html>
<meta charset="utf-8"/>
<title>{title}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  body {{ margin:0; font-family: Arial, sans-serif; }}
  #map {{ position:absolute; top:0; left:0; right:340px; bottom:0; }}
  #panel {{ position:absolute; top:0; right:0; width:340px; bottom:0; overflow-y:auto;
            padding:10px; box-sizing:border-box; background:#f9f9f9; border-left:1px solid #ccc; }}
  #panel h3 {{ margin:6px 0 4px; font-size:14px; }}
  #panel label {{ font-size:12px; display:block; margin:4px 0; }}
  #stats {{ font-size:12px; line-height:1.5; }}
  #legend {{ font-size:11px; margin-top:6px; }}
  .legend-swatch {{ display:inline-block; width:12px; height:12px; margin-right:4px; vertical-align:middle; }}
  #warnings {{ font-size:11px; color:#a33; max-height:150px; overflow-y:auto; }}
  .leaflet-tooltip {{ font-size:12px; }}

  #levelSlider {{ position:relative; height:32px; width:100%; margin-top:6px; }}
  #levelSlider input[type=range] {{
    position:absolute; top:10px; left:0; width:100%; margin:0;
    -webkit-appearance:none; appearance:none; background:transparent; pointer-events:none;
  }}
  #levelSlider input[type=range]::-webkit-slider-thumb {{
    -webkit-appearance:none; pointer-events:auto; width:16px; height:16px; border-radius:50%;
    background:#06c; border:1px solid #036; cursor:pointer; margin-top:-7px;
  }}
  #levelSlider input[type=range]::-moz-range-thumb {{
    pointer-events:auto; width:16px; height:16px; border-radius:50%;
    background:#06c; border:1px solid #036; cursor:pointer;
  }}
  #levelSlider .track {{
    position:absolute; top:14px; left:0; right:0; height:4px; background:#ddd; border-radius:2px;
  }}
  #levelSlider .track-fill {{
    position:absolute; top:14px; height:4px; background:#06c; border-radius:2px;
  }}
  #levelLabels {{ display:flex; justify-content:space-between; font-size:11px; margin-top:2px; }}
</style>

<div id="map"></div>
<div id="panel">
  <h3>{title}</h3>
  <div id="stats"></div>
  <h3>Color by</h3>
  <label><input type="radio" name="colorBy" value="features" checked> Feature count</label>
  <label><input type="radio" name="colorBy" value="size"> Tile size (bytes)</label>
  <div id="legend"></div>
  <h3>Filter (level)</h3>
  <div id="levelSlider">
    <div class="track"></div>
    <div class="track-fill" id="trackFill"></div>
    <input type="range" id="minLevel" min="0" max="24" step="1" value="0">
    <input type="range" id="maxLevel" min="0" max="24" step="1" value="24">
  </div>
  <div id="levelLabels"><span id="minLevelLabel">0</span><span id="maxLevelLabel">24</span></div>
  {"<h3>Warnings (" + str(len(warnings)) + ")</h3><ul id='warnings'>" + warn_html + more + "</ul>" if warnings else ""}
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const TILES = {data};
const TOTAL_CELL_COUNT = new Set(TILES.map(t => `${{t.level}}/${{t.x}}/${{t.y}}`)).size;
const map = L.map('map').setView([{center_lat}, {center_lon}], 15);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 21, attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);
map.fitBounds([[{south},{west}],[{north},{east}]]);

function fmtBytes(n) {{
  if (n == null) return 'n/a';
  const units = ['B','KB','MB','GB'];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) {{ n /= 1024; i++; }}
  return n.toFixed(1) + ' ' + units[i];
}}

// Perceptually-ish scale: blue (low) -> red (high), log-scaled.
function colorFor(value, min, max) {{
  if (value == null) return '#888';
  const lv = Math.log(value + 1), lmin = Math.log(min + 1), lmax = Math.log(max + 1);
  const t = lmax > lmin ? (lv - lmin) / (lmax - lmin) : 0;
  const hue = 240 - 240 * t; // 240=blue .. 0=red
  return `hsl(${{hue}}, 80%, 50%)`;
}}

let rects = [];
function render() {{
  rects.forEach(r => map.removeLayer(r));
  rects = [];
  const colorBy = document.querySelector('input[name=colorBy]:checked').value;
  const {{ minLevel, maxLevel }} = getLevelRange();
  const visibleRaw = TILES.filter(t => t.level >= minLevel && t.level <= maxLevel);

  // Same-tile multi-content slots share identical bounds (that's what
  // "same-tile splitting" means) - merge them into one cell so rectangles
  // don't stack exactly on top of each other with only the last one visible.
  const byCell = new Map();
  for (const t of visibleRaw) {{
    const key = `${{t.level}}/${{t.x}}/${{t.y}}`;
    if (!byCell.has(key)) {{
      byCell.set(key, {{
        level: t.level, x: t.x, y: t.y, region: t.region,
        features: 0, size: 0, slots: [],
      }});
    }}
    const cell = byCell.get(key);
    if (t.features != null) cell.features += t.features;
    cell.size += t.size;
    cell.slots.push(t);
  }}
  const visible = [...byCell.values()];

  const values = visible.map(t => colorBy === 'features' ? t.features : t.size).filter(v => v != null);
  const min = values.length ? Math.min(...values) : 0;
  const max = values.length ? Math.max(...values) : 1;

  let totalFeatures = 0, totalSize = 0;
  for (const t of visible) {{
    const value = colorBy === 'features' ? t.features : t.size;
    const color = colorFor(value, min, max);
    const rect = L.rectangle(
      [[t.region.south, t.region.west], [t.region.north, t.region.east]],
      {{ color: '#333', weight: 1, fillColor: color, fillOpacity: 0.55 }}
    ).addTo(map);
    const slotLines = t.slots
      .map(s => `  slot ${{s.slot}}: ${{s.features ?? 'n/a'}} features, ${{fmtBytes(s.size)}} (${{s.uri}})`)
      .join('<br>');
    rect.bindTooltip(
      `level ${{t.level}} (${{t.x}},${{t.y}})${{t.slots.length > 1 ? ' — ' + t.slots.length + ' contents' : ''}}<br>` +
      `total features: ${{t.features}}<br>total size: ${{fmtBytes(t.size)}}<br>${{slotLines}}`
    );
    rects.push(rect);
    if (t.features != null) totalFeatures += t.features;
    totalSize += t.size;
  }}

  document.getElementById('stats').innerHTML =
    `Tiles: ${{visible.length}} / ${{TOTAL_CELL_COUNT}}<br>` +
    `Total features: ${{totalFeatures}}<br>` +
    `Total size: ${{fmtBytes(totalSize)}}`;

  const swatches = [0, 0.25, 0.5, 0.75, 1].map(t => {{
    const v = Math.exp(Math.log(min + 1) + t * (Math.log(max + 1) - Math.log(min + 1))) - 1;
    return `<span class="legend-swatch" style="background:${{colorFor(v, min, max)}}"></span>${{
      colorBy === 'size' ? fmtBytes(v) : Math.round(v)
    }}`;
  }});
  document.getElementById('legend').innerHTML = swatches.join('<br>');
}}

const minLevelEl = document.getElementById('minLevel');
const maxLevelEl = document.getElementById('maxLevel');
const minLevelLabel = document.getElementById('minLevelLabel');
const maxLevelLabel = document.getElementById('maxLevelLabel');
const trackFill = document.getElementById('trackFill');
const sliderMax = parseInt(minLevelEl.max);

function getLevelRange() {{
  let lo = parseInt(minLevelEl.value);
  let hi = parseInt(maxLevelEl.value);
  return {{ minLevel: Math.min(lo, hi), maxLevel: Math.max(lo, hi) }};
}}

function updateSliderUI() {{
  const {{ minLevel, maxLevel }} = getLevelRange();
  minLevelLabel.textContent = minLevel;
  maxLevelLabel.textContent = maxLevel;
  const pct = v => (v / sliderMax) * 100;
  trackFill.style.left = pct(minLevel) + '%';
  trackFill.style.width = Math.max(0, pct(maxLevel) - pct(minLevel)) + '%';
}}

function onSliderInput() {{
  // Keep the two thumbs from crossing so dragging feels like a true range.
  if (parseInt(minLevelEl.value) > parseInt(maxLevelEl.value)) {{
    if (this === minLevelEl) maxLevelEl.value = minLevelEl.value;
    else minLevelEl.value = maxLevelEl.value;
  }}
  updateSliderUI();
  render();
}}

minLevelEl.addEventListener('input', onSliderInput);
maxLevelEl.addEventListener('input', onSliderInput);
updateSliderUI();

document.querySelectorAll('input[name=colorBy]').forEach(el => el.addEventListener('change', render));
render();
</script>
"""


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    tileset_path = Path(sys.argv[1]).resolve()
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else tileset_path.with_name(
        tileset_path.stem + "_quadtree.html"
    )
    base_dir = tileset_path.parent

    region, subtree_levels, subtrees_uri_template, content_uri_templates = parse_tileset(
        tileset_path
    )

    tiles = []
    seen_files = set()
    warnings = []
    walk_subtree(
        base_dir, subtrees_uri_template, content_uri_templates,
        region, subtree_levels, 0, 0, 0, tiles, seen_files, warnings,
    )

    print(f"{len(tiles)} content tiles found, {len(warnings)} warnings")
    html = build_html(tiles, region, warnings, tileset_path.parent.name + " / " + tileset_path.name)
    out_path.write_text(html)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
