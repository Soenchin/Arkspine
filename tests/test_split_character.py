import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "spine-animation-ai" / "scripts" / "split_character.py"
_spec = importlib.util.spec_from_file_location("split_character", SCRIPT_PATH)
split_character = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(split_character)


class SplitCharacterTests(unittest.TestCase):
    def test_segment_parts_writes_rgba_and_preserves_enclosed_white(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            atlas = np.full((180, 280, 4), 255, dtype=np.uint8)

            # A blue outlined part containing an enclosed white detail.
            cv2.rectangle(atlas, (30, 30), (125, 145), (20, 80, 210, 255), 4)
            cv2.rectangle(atlas, (52, 55), (103, 95), (255, 255, 255, 255), -1)
            # A separate part with a light anti-aliased edge.
            cv2.ellipse(atlas, (210, 88), (35, 52), 0, 0, 360, (220, 100, 20, 255), -1)
            cv2.ellipse(atlas, (210, 88), (38, 55), 0, 0, 360, (245, 245, 245, 255), 2)
            atlas_path = root / "atlas.png"
            Image.fromarray(atlas, "RGBA").save(atlas_path)

            output_dir = root / "parts"
            parts = split_character.segment_parts(
                str(atlas_path),
                str(output_dir),
                min_area=100,
                padding=8,
                bg_tolerance=30,
                edge_radius=2,
                debug_dir=str(root / "debug"),
            )

            self.assertEqual(len(parts), 2)
            self.assertTrue((output_dir / "parts.json").exists())
            self.assertTrue((root / "debug" / "foreground_alpha.png").exists())
            self.assertTrue((root / "debug" / "contours.png").exists())

            manifest = json.loads((output_dir / "parts.json").read_text(encoding="utf-8"))
            self.assertEqual([part["name"] for part in manifest["parts"]], ["part_001", "part_002"])

            images = [np.array(Image.open(path)) for _, path in parts]
            modes = []
            for _, path in parts:
                with Image.open(path) as part_image:
                    modes.append(part_image.mode)
            self.assertTrue(all(mode == "RGBA" for mode in modes))
            self.assertTrue(all(image[0, 0, 3] == 0 for image in images))

            # The white rectangle is enclosed by the blue outline, so it must
            # remain part of the opaque foreground rather than being chroma-keyed.
            first_bbox = manifest["parts"][0]["canvas_bbox"]
            first = images[0]
            white_x = 52 - first_bbox["x"]
            white_y = 55 - first_bbox["y"]
            self.assertGreaterEqual(int(first[white_y, white_x, 3]), 250)

            # The light outer edge produces at least some anti-aliased alpha.
            self.assertTrue(any(np.any((image[:, :, 3] > 0) & (image[:, :, 3] < 255)) for image in images))

    def test_legacy_background_threshold_still_works(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            atlas = np.full((80, 100, 3), 255, dtype=np.uint8)
            cv2.circle(atlas, (50, 40), 20, (20, 80, 210), -1)
            atlas_path = root / "atlas.png"
            Image.fromarray(atlas, "RGB").save(atlas_path)

            parts = split_character.segment_parts(
                str(atlas_path),
                str(root / "parts"),
                min_area=100,
                padding=2,
                bg_threshold=240,
            )
            self.assertEqual(len(parts), 1)
            with Image.open(parts[0][1]) as part_image:
                self.assertEqual(part_image.mode, "RGBA")


if __name__ == "__main__":
    unittest.main()
