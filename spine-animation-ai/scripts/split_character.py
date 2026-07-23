#!/usr/bin/env python3
"""
split_character.py — Generate a sprite-sheet atlas from a full character image
using Krill GPT (OpenAI-compatible) image generation, then segment individual
body parts via OpenCV connected-components analysis.

Usage:
    python split_character.py <input_image> [--output-dir output_parts]
        [--atlas-out atlas.png] [--min-area 500] [--padding 12]
        [--bg-threshold 240]

Requires:
    pip install opencv-python Pillow numpy openai
    Krill GPT API key: set KRILL_API_KEY or configure config.local.json
"""

import argparse
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


def segment_parts(
    atlas_path: str,
    output_dir: str,
    min_area: int = 500,
    padding: int = 12,
    bg_threshold: int = 240,
):
    """Segment the generated atlas into individual body parts."""
    atlas_img = cv2.imread(atlas_path)
    if atlas_img is None:
        print(f"ERROR: Could not read atlas image: {atlas_path}", file=sys.stderr)
        sys.exit(1)

    gray = cv2.cvtColor(atlas_img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, bg_threshold, 255, cv2.THRESH_BINARY_INV)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    os.makedirs(output_dir, exist_ok=True)

    parts = []
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        x = max(0, x - padding)
        y = max(0, y - padding)
        w = min(atlas_img.shape[1] - x, w + 2 * padding)
        h = min(atlas_img.shape[0] - y, h + 2 * padding)

        part = atlas_img[y : y + h, x : x + w]
        part_path = os.path.join(output_dir, f"part_{i:03d}.png")
        cv2.imwrite(part_path, part)
        parts.append((f"part_{i:03d}", part_path))

    return parts


def main():
    parser = argparse.ArgumentParser(
        description="Split character image into body parts using Krill GPT"
    )
    parser.add_argument("input_image", help="Path to the full character image")
    parser.add_argument("--output-dir", default="parts", help="Output directory for parts")
    parser.add_argument("--atlas-out", default="atlas.png", help="Output atlas path")
    parser.add_argument("--min-area", type=int, default=500, help="Minimum contour area")
    parser.add_argument("--padding", type=int, default=12, help="Padding around parts")
    parser.add_argument("--bg-threshold", type=int, default=240, help="Background threshold")

    args = parser.parse_args()

    print("Step 1: Generating deconstructed sprite atlas via Krill GPT...")
    atlas_path = generate_atlas(args.input_image, args.atlas_out)
    print(f"  Atlas saved: {atlas_path}")

    print("Step 2: Segmenting parts from atlas...")
    parts = segment_parts(atlas_path, args.output_dir, args.min_area, args.padding, args.bg_threshold)

    print(f"  Generated {len(parts)} parts:")
    for name, path in parts:
        print(f"    {name}: {path}")


if __name__ == "__main__":
    main()
