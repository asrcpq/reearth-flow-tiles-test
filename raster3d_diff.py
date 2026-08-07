#!/usr/bin/env python3
"""Visualize the difference between two raster3d depth PNGs (as written by
plateau-tiles-test's `Canvas::write_png_f32`: each pixel's raw f32 bits packed
into RGBA8, little-endian, non-finite = background/no-hit).

usage: raster3d_diff.py <truth.png> <flow.png> <out.png> [--scale METERS]
"""
import argparse
import numpy as np
from PIL import Image


def read_depth_png(path):
    img = np.array(Image.open(path).convert("RGBA"))
    return img.view(np.float32).reshape(img.shape[:2])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("truth", help="truth depth PNG")
    parser.add_argument("flow", help="flow depth PNG")
    parser.add_argument("out", help="output diff PNG")
    parser.add_argument(
        "--scale",
        type=float,
        default=1.0,
        help="depth difference (metres) that maps to full-intensity color (default: 1.0)",
    )
    args = parser.parse_args()

    truth = read_depth_png(args.truth)
    flow = read_depth_png(args.flow)
    if truth.shape != flow.shape:
        raise SystemExit(f"size mismatch: truth {truth.shape} vs flow {flow.shape}")

    truth_hit = np.isfinite(truth)
    flow_hit = np.isfinite(flow)
    both_hit = truth_hit & flow_hit

    h, w = truth.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)

    # Both background: leave black.

    # Only truth has a surface here (flow is missing it): red, full intensity —
    # a silhouette mismatch, not a depth-magnitude one, so it isn't scaled.
    only_truth = truth_hit & ~flow_hit
    out[only_truth] = [255, 0, 0]

    # Only flow has a surface here (truth doesn't): green, full intensity.
    only_flow = flow_hit & ~truth_hit
    out[only_flow] = [0, 255, 0]

    # Both hit: color by signed depth difference, scaled by --scale.
    # flow farther than truth (flow - truth > 0) -> green; flow nearer -> red.
    diff = (flow - truth)[both_hit]
    intensity = np.clip(np.abs(diff) / args.scale, 0.0, 1.0)
    channel = (intensity * 255).astype(np.uint8)

    both_idx = np.nonzero(both_hit)
    is_green = diff > 0
    pixel_channel = np.zeros(len(channel), dtype=np.uint8)
    colors = np.zeros((len(channel), 3), dtype=np.uint8)
    colors[is_green, 1] = channel[is_green]
    colors[~is_green, 0] = channel[~is_green]
    out[both_idx] = colors

    Image.fromarray(out, mode="RGB").save(args.out)
    print(
        f"wrote {args.out} "
        f"({only_truth.sum()} truth-only px, {only_flow.sum()} flow-only px, "
        f"{both_hit.sum()} compared px, max diff {np.abs(diff).max() if diff.size else 0:.4f}m)"
    )


if __name__ == "__main__":
    main()
