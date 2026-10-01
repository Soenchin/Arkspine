import importlib.util
import json
import math
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "spine-animation-ai" / "scripts" / "build_spine_json.py"
spec = importlib.util.spec_from_file_location("build_spine_json", SCRIPT)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def config(animations):
    names = ["root", "hip", "torso", "neck", "head"]
    for side in ("left", "right"):
        names.extend(f"{side}-{part}" for part in (
            "upper-arm", "lower-arm", "upper-leg", "lower-leg", "foot"
        ))
    return {
        "bones": [{"name": "root"}] + [
            {"name": name, "parent": "root"} for name in names[1:]
        ],
        "animations": animations,
    }


class Spine42TimelineTests(unittest.TestCase):
    def assert_timeline_format(self, skeleton):
        for animation, data in skeleton["animations"].items():
            for bone, timelines in data.get("bones", {}).items():
                for kind, frames in timelines.items():
                    with self.subTest(animation=animation, bone=bone, kind=kind):
                        self.assertNotIn("curve", frames[-1])
                        for index, frame in enumerate(frames):
                            if kind == "rotate":
                                self.assertNotIn("angle", frame)
                                self.assertIn("value", frame)
                            curve = frame.get("curve")
                            if not isinstance(curve, list):
                                continue
                            self.assertEqual(len(curve), 4 if kind == "rotate" else 8)
                            self.assertTrue(all(math.isfinite(v) for v in curve))
                            for offset in range(0, len(curve), 4):
                                self.assertGreaterEqual(curve[offset], frame["time"] - 1e-6)
                                self.assertLessEqual(
                                    curve[offset + 2], frames[index + 1]["time"] + 1e-6
                                )

    def test_rotation_uses_value_not_legacy_angle(self):
        result = builder.build_spine_json(config(["idle"]))
        frames = result["animations"]["idle"]["bones"]["head"]["rotate"]
        self.assertEqual(frames[1].get("value"), -2.0)
        self.assertTrue(all("angle" not in frame for frame in frames))

    def test_translate_curves_are_absolute_and_cover_both_axes(self):
        result = builder.build_spine_json(config(["idle"]))
        frames = result["animations"]["idle"]["bones"]["torso"]["translate"]
        self.assertEqual(frames[0].get("curve"), [0.2, 0, 0.6, 0, 0.2, 0, 0.6, 1.5])
        self.assertEqual(frames[1].get("curve"), [1.0, 0, 1.4, 0, 1.0, 1.5, 1.4, 0])
        self.assertNotIn("curve", frames[-1])

    def test_all_six_presets_use_spine_42_timelines(self):
        result = builder.build_spine_json(config(list(builder.PRESETS)))
        self.assertEqual(set(result["animations"]), set(builder.PRESETS))
        self.assert_timeline_format(result)
        json.dumps(result, allow_nan=False)

    def test_custom_shorthand_moves_stepped_curve_to_segment_start(self):
        data = config([])
        data["custom_animations"] = {
            "turn": {"bones": {"head": {"rotate": [
                {"time": 0, "angle": 0},
                {"time": 1, "angle": 20, "curve": "stepped"},
            ]}}}
        }
        result = builder.build_spine_json(data)
        self.assertEqual(result["animations"]["turn"]["bones"]["head"]["rotate"], [
            {"time": 0, "value": 0, "curve": "stepped"},
            {"time": 1, "value": 20},
        ])

    def test_updated_sombrero_example_has_valid_timelines_and_no_double_scale(self):
        path = ROOT / "spine-animation-ai" / "examples" / "sombrero" / "sombrero.json"
        example = json.loads(path.read_text(encoding="utf-8"))
        self.assert_timeline_format(example)
        for skin in example["skins"]:
            for attachments in skin["attachments"].values():
                for attachment in attachments.values():
                    self.assertEqual(attachment.get("scaleX", 1), 1)
                    self.assertEqual(attachment.get("scaleY", 1), 1)


if __name__ == "__main__":
    unittest.main()
