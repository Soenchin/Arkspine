#!/usr/bin/env python3
"""
split_character.py — Generate a sprite-sheet atlas from a full character image
using Krill GPT (OpenAI-compatible) image generation, then segment individual
body parts via OpenCV connected-components analysis.

Usage:
    python split_character.py <input_image> [--output-dir output_parts]
        [--atlas-out atlas.png] [--min-area 500] [--padding 12]
        [--bg-tolerance 30] [--edge-radius 2] [--debug-dir debug]

The generated atlas normally has a light background. Segmentation only removes
background pixels connected to the atlas border, so enclosed white details such
as clothes and eyes are retained. Output parts are RGBA PNGs with transparent
padding and anti-aliased alpha edges.

Requires:
    pip install opencv-python Pillow numpy openai
    Krill GPT API key: set KRILL_API_KEY or configure config.local.json
"""

import argparse
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image


POSITIVE_PROMPT = (
    "A complete 2D game sprite sheet texture atlas for Spine animation of the "
    "exact character in the reference image. The character is completely "
    "deconstructed into separated, isolated body parts. Separated individual "
    "parts laid out flatly: isolated head, isolated torso, isolated upper arms, "
    "lower arms, hands, upper legs, lower legs, and feet. Spread out with clear "
    "space between every single body part. No overlapping parts. Clean solid "
    "white background. CRITICAL: Maintain the exact same art style, exact same "
    "shading, exact face, and exact color palette as the reference image. "
    "Identical style match, 2D game asset, flat layout, character design sheet."
)

NEGATIVE_PROMPT = (
    "3D, realistic, altered style, different art style, different face, "
    "redesign, overlapping parts, connected limbs, full body standing, dynamic "
    "pose, background scenery, shadows, gradients on background, messy layout, "
    "missing limbs, merged layers, text, watermarks."
)


def resolve_krill_config():
    """Resolve Krill API config from env, config.local.json, or defaults."""
    import json as _json
    from pathlib import Path

    # Resolve the shared pi skill config without copying its secret into the repo.
    candidates = [
        Path.home() / ".pi" / "agent" / "skills" / "krill-gpt-image",
        Path(os.environ.get("USERPROFILE", "")) / ".pi" / "agent" / "skills" / "krill-gpt-image",
        Path(__file__).resolve().parent.parent / "krill-gpt-image",
    ]
    skill_dir = next((path for path in candidates if (path / "config.local.json").exists()), candidates[0])
    config_path = skill_dir / "config.local.json"
    file_cfg = {}
    if config_path.exists():
        file_cfg = _json.loads(config_path.read_text(encoding="utf-8"))

    base_url = (
        os.environ.get("KRILL_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or file_cfg.get("base_url")
        or "https://api.cdn-krill-ai.com/v1"
    )
    api_key = (
        os.environ.get("KRILL_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or file_cfg.get("api_key")
    )
    model = (
        os.environ.get("KRILL_MODEL")
        or file_cfg.get("model")
        or "gpt-image-2"
    )
    return base_url, api_key, model


def generate_atlas(input_image_path: str, atlas_out: str) -> str:
    """Send the reference image to Krill GPT and save the generated atlas PNG."""
    from openai import OpenAI

    base_url, api_key, model = resolve_krill_config()
    if not api_key:
        print(
            "ERROR: No Krill API key found.\n"
            "Set KRILL_API_KEY environment variable, or create a\n"
            "config.local.json file in the krill-gpt-image skill directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    client = OpenAI(base_url=base_url, api_key=api_key)

    # Use image edit without mask: send the character image as input
    # with a prompt to deconstruct it into a sprite atlas
    with open(input_image_path, "rb") as img_fp:
        result = client.images.edit(
            model=model,
            image=img_fp,
            prompt=f"{POSITIVE_PROMPT}\n\nNegative prompt: {NEGATIVE_PROMPT}",
            size="1024x1024",
            n=1,
        )

    # Decode and save
    from base64 import b64decode

    for item in result.data:
        b64_data = getattr(item, "b64_json", None)
        if b64_data:
            with open(atlas_out, "wb") as f:
                f.write(b64decode(b64_data))
            return atlas_out

        url = getattr(item, "url", None)
        if url:
            import urllib.request

            urllib.request.urlretrieve(url, atlas_out)
            return atlas_out

    print("ERROR: Krill API did not return image data.", file=sys.stderr)
    sys.exit(1)


def _load_rgba(path: str) -> np.ndarray:
    """Read an image without throwing away an existing alpha channel."""
    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        print(f"ERROR: Could not read atlas image: {path}", file=sys.stderr)
        sys.exit(1)

    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2RGBA)
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    return cv2.cvtColor(image, cv2.COLOR_BGR2RGBA)


def _estimate_background_color(rgba: np.ndarray, border_width: int = 2) -> np.ndarray:
    """Estimate the atlas background from pixels along its outer border."""
    height, width = rgba.shape[:2]
    border_width = max(1, min(border_width, height, width))
    border = np.concatenate(
        (
            rgba[:border_width, :, :3].reshape(-1, 3),
            rgba[-border_width:, :, :3].reshape(-1, 3),
            rgba[:, :border_width, :3].reshape(-1, 3),
            rgba[:, -border_width:, :3].reshape(-1, 3),
        ),
        axis=0,
    )
    border_alpha = np.concatenate(
        (
            rgba[:border_width, :, 3].reshape(-1),
            rgba[-border_width:, :, 3].reshape(-1),
            rgba[:, :border_width, 3].reshape(-1),
            rgba[:, -border_width:, 3].reshape(-1),
        ),
        axis=0,
    )
    opaque = border_alpha > 0
    if not opaque.any():
        # A transparent atlas has no reliable chroma sample. The color is only
        # used for optional edge un-matting, so white is the safest fallback.
        return np.array([255.0, 255.0, 255.0], dtype=np.float32)
    border = border[opaque]
    if not len(border):
        return np.array([255.0, 255.0, 255.0], dtype=np.float32)
    return np.median(border.astype(np.float32), axis=0)


def _background_mask(rgba: np.ndarray, bg_tolerance: int, edge_radius: int):
    """Build a foreground alpha mask while preserving enclosed light details.

    A pixel is considered removable background only when it is close to the
    estimated border color *and* connected to an image edge. This avoids the
    classic chroma-key failure where a white shirt or eye highlight disappears.
    A small band around the detected foreground gets estimated anti-aliased
    alpha and is un-matted against the background color to avoid white halos.
    """
    rgb = rgba[:, :, :3].astype(np.float32)
    source_alpha = rgba[:, :, 3].astype(np.float32)
    background = _estimate_background_color(rgba)

    color_distance = np.sqrt(np.sum((rgb - background) ** 2, axis=2))
    candidate = (source_alpha > 0) & (color_distance <= float(bg_tolerance))

    component_count, labels = cv2.connectedComponents(
        candidate.astype(np.uint8), connectivity=8
    )
    del component_count
    border_labels = np.unique(
        np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1]))
    )
    border_labels = border_labels[border_labels != 0]
    background_region = np.isin(labels, border_labels)

    # Everything not belonging to border-connected background is a foreground
    # seed. Enclosed white clothing/details therefore remain opaque.
    foreground_seed = (source_alpha > 0) & ~background_region
    alpha = np.where(foreground_seed, source_alpha, 0.0).astype(np.float32)
    output_rgb = rgb.copy()

    if np.any(foreground_seed) and edge_radius > 0:
        # Find the nearest foreground seed for pixels just outside its edge.
        distance_source = np.where(foreground_seed, 0, 255).astype(np.uint8)
        distance, nearest_labels = cv2.distanceTransformWithLabels(
            distance_source,
            cv2.DIST_L2,
            cv2.DIST_MASK_PRECISE,
            cv2.DIST_LABEL_PIXEL,
        )

        # DIST_LABEL_PIXEL gives each seed pixel a label. Build a compact lookup
        # table so the nearby seed's color can be used for un-matting.
        seed_coords = np.argwhere(foreground_seed)
        seed_labels = nearest_labels[foreground_seed]
        unique_labels, first_indices = np.unique(seed_labels, return_index=True)
        label_colors = np.zeros((int(nearest_labels.max()) + 1, 3), dtype=np.float32)
        label_colors[unique_labels] = rgb[
            seed_coords[first_indices, 0], seed_coords[first_indices, 1]
        ]
        nearest_rgb = label_colors[nearest_labels]

        # GPU/bilinear texture filtering can sample RGB from alpha-zero atlas
        # pixels. Bleed the nearest foreground color into transparent
        # background pixels so transparent padding does not create white halos.
        valid_background = background_region & (nearest_labels > 0)
        output_rgb[valid_background] = nearest_rgb[valid_background]

        edge = (
            background_region
            & ~foreground_seed
            & (distance <= float(edge_radius))
            & (source_alpha > 0)
        )
        if np.any(edge):
            foreground_delta = nearest_rgb - background
            pixel_delta = rgb - background
            denominator = np.sum(foreground_delta * foreground_delta, axis=2)
            numerator = np.sum(pixel_delta * foreground_delta, axis=2)
            estimated = np.divide(
                numerator,
                denominator,
                out=np.zeros_like(numerator),
                where=denominator > 1.0,
            )
            estimated = np.clip(estimated, 0.0, 1.0)

            # If the nearest foreground color is itself almost the background,
            # use a conservative geometric fallback. This is rare, but avoids
            # NaNs for very pale artwork.
            geometric = np.clip(
                1.0 - np.maximum(distance - 0.25, 0.0) / max(float(edge_radius), 1.0),
                0.0,
                1.0,
            ) * 0.5
            estimated = np.where(denominator > 1.0, estimated, geometric)
            edge_alpha = estimated * 255.0
            alpha[edge] = np.minimum(source_alpha[edge], edge_alpha[edge])

            # Recover the foreground color from the composited pixel. Keeping
            # RGB un-matted matters when this PNG is later placed on a dark
            # atlas or rendered over a non-white game background.
            safe_alpha = np.maximum(edge_alpha / 255.0, 1.0 / 255.0)
            unmatted = background + (rgb - background) / safe_alpha[:, :, None]
            output_rgb[edge] = np.clip(unmatted[edge], 0.0, 255.0)

    result = np.empty_like(rgba)
    result[:, :, :3] = np.clip(output_rgb, 0, 255).astype(np.uint8)
    result[:, :, 3] = np.clip(alpha, 0, 255).astype(np.uint8)
    return result, background, background_region, foreground_seed


def _save_debug_images(
    debug_dir: str,
    rgba: np.ndarray,
    alpha: np.ndarray,
    background_region: np.ndarray,
    contours,
):
    """Save masks and contour overlays for human inspection."""
    os.makedirs(debug_dir, exist_ok=True)
    Image.fromarray((background_region.astype(np.uint8) * 255), "L").save(
        os.path.join(debug_dir, "background_mask.png")
    )
    Image.fromarray(alpha, "L").save(os.path.join(debug_dir, "foreground_alpha.png"))

    overlay = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_RGB2BGR)
    cv2.drawContours(overlay, contours, -1, (0, 180, 255), 2)
    cv2.imwrite(os.path.join(debug_dir, "contours.png"), overlay)


def segment_parts(
    atlas_path: str,
    output_dir: str,
    min_area: int = 500,
    padding: int = 12,
    bg_threshold: int = 240,
    bg_tolerance=None,
    edge_radius: int = 2,
    debug_dir=None,
    manifest_out=None,
):
    """Segment an atlas into transparent RGBA body-part PNGs.

    ``bg_threshold`` remains as a compatibility argument for callers of the
    original function. New callers should use ``bg_tolerance``: Euclidean RGB
    distance from the estimated border background.
    """
    rgba, background, background_region, _ = _background_mask(
        _load_rgba(atlas_path),
        (
            max(12, int(round(max(0, 255 - bg_threshold) * np.sqrt(3))))
            if bg_tolerance is None
            else max(1, int(bg_tolerance))
        ),
        max(0, int(edge_radius)),
    )
    height, width = rgba.shape[:2]

    # Use alpha rather than RGB brightness for contour detection. White parts
    # are now valid foreground and transparent padding is truly excluded.
    part_mask = (rgba[:, :, 3] >= 16).astype(np.uint8) * 255
    contours, _ = cv2.findContours(
        part_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours = [cnt for cnt in contours if cv2.contourArea(cnt) >= min_area]
    contours.sort(key=lambda cnt: (cv2.boundingRect(cnt)[1], cv2.boundingRect(cnt)[0]))

    os.makedirs(output_dir, exist_ok=True)
    if debug_dir:
        _save_debug_images(
            debug_dir,
            rgba,
            rgba[:, :, 3],
            background_region,
            contours,
        )

    parts = []
    manifest_parts = []
    for index, cnt in enumerate(contours, start=1):
        original_x, original_y, original_w, original_h = cv2.boundingRect(cnt)
        x = max(0, original_x - padding)
        y = max(0, original_y - padding)
        right = min(width, original_x + original_w + padding)
        bottom = min(height, original_y + original_h + padding)

        part = rgba[y:bottom, x:right].copy()
        name = f"part_{index:03d}"
        part_path = os.path.join(output_dir, f"{name}.png")
        Image.fromarray(part, "RGBA").save(part_path)
        parts.append((name, part_path))
        manifest_parts.append(
            {
                "name": name,
                "file": os.path.basename(part_path),
                "bbox": {
                    "x": int(original_x),
                    "y": int(original_y),
                    "width": int(original_w),
                    "height": int(original_h),
                },
                "canvas_bbox": {
                    "x": int(x),
                    "y": int(y),
                    "width": int(right - x),
                    "height": int(bottom - y),
                },
                "contour_area": int(round(cv2.contourArea(cnt))),
                "opaque_pixels": int(np.count_nonzero(part[:, :, 3] >= 250)),
                "alpha_pixels": int(np.count_nonzero(part[:, :, 3] >= 16)),
            }
        )

    if manifest_out is None:
        manifest_out = os.path.join(output_dir, "parts.json")
    manifest = {
        "atlas": os.path.basename(atlas_path),
        "atlas_width": int(width),
        "atlas_height": int(height),
        "background_color": [int(round(value)) for value in background],
        "background_tolerance": int(
            max(12, int(round(max(0, 255 - bg_threshold) * np.sqrt(3))))
            if bg_tolerance is None
            else max(1, int(bg_tolerance))
        ),
        "edge_radius": max(0, int(edge_radius)),
        "parts": manifest_parts,
    }
    with open(manifest_out, "w", encoding="utf-8") as manifest_file:
        json.dump(manifest, manifest_file, indent=2, ensure_ascii=False)

    return parts


def main():
    parser = argparse.ArgumentParser(
        description="Split character image into body parts using Krill GPT"
    )
    parser.add_argument("input_image", help="Path to the full character image")
    parser.add_argument("--output-dir", default="parts", help="Output directory for parts")
    parser.add_argument("--atlas-out", default="atlas.png", help="Output atlas path")
    parser.add_argument("--min-area", type=int, default=500, help="Minimum contour area")
    parser.add_argument("--padding", type=int, default=12, help="Transparent padding around parts")
    parser.add_argument(
        "--bg-tolerance",
        type=int,
        default=30,
        help="RGB distance tolerance for border-connected background (default: 30)",
    )
    parser.add_argument(
        "--bg-threshold",
        type=int,
        default=None,
        help="Deprecated grayscale compatibility option; prefer --bg-tolerance",
    )
    parser.add_argument(
        "--edge-radius",
        type=int,
        default=2,
        help="Pixels around the foreground used for anti-aliased alpha (default: 2)",
    )
    parser.add_argument(
        "--debug-dir",
        default=None,
        help="Write background/alpha masks and contour overlay here",
    )
    parser.add_argument(
        "--manifest-out",
        default=None,
        help="Path for parts.json (default: <output-dir>/parts.json)",
    )

    args = parser.parse_args()

    print("Step 1: Generating deconstructed sprite atlas via Krill GPT...")
    atlas_path = generate_atlas(args.input_image, args.atlas_out)
    print(f"  Atlas saved: {atlas_path}")

    print("Step 2: Segmenting parts from atlas...")
    bg_tolerance = args.bg_tolerance
    if args.bg_threshold is not None:
        # Preserve the old CLI's approximate meaning: grayscale values below
        # bg_threshold were treated as foreground against a white background.
        bg_tolerance = max(12, int(round(max(0, 255 - args.bg_threshold) * np.sqrt(3))))

    parts = segment_parts(
        atlas_path,
        args.output_dir,
        args.min_area,
        args.padding,
        bg_tolerance=bg_tolerance,
        edge_radius=args.edge_radius,
        debug_dir=args.debug_dir,
        manifest_out=args.manifest_out,
    )

    print(f"  Generated {len(parts)} parts:")
    for name, path in parts:
        print(f"    {name}: {path}")


if __name__ == "__main__":
    main()
