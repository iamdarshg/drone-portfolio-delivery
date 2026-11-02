import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest.mock import patch
import harness as h


class HarnessTests(unittest.TestCase):
    def test_optional_frameworks_disabled_process_locally(self):
        import os
        before = dict(os.environ)
        env = h.environment()
        self.assertEqual(env["USE_TF"], "0")
        self.assertEqual(env["USE_FLAX"], "0")
        self.assertEqual(dict(os.environ), before)

    def test_coverage_and_tail(self):
        starts = h.windows(648, 17)
        covered = {j for i in starts for j in range(i, i+17)}
        self.assertEqual(covered, set(range(648)))
        self.assertEqual(starts[-1], 631)

    def test_invalid_windows(self):
        for count, size in [(4, 17), (100, 16), (100, 1)]:
            with self.assertRaises(ValueError):
                h.windows(count, size)

    def test_runtime_destination_rejected(self):
        for dest in ["C:/temp/test", "D:/test", "E:/other", "E:/OneLine_diffusion/../escape"]:
            with self.assertRaises(ValueError):
                h.epath(dest)

    def test_config_and_real_command(self):
        a = h.parser().parse_args([])
        data = tomllib.loads(h.dataset_toml(a, Path("E:/OneLine_diffusion/test")))
        self.assertFalse(data["general"]["enable_bucket"])
        self.assertEqual(data["datasets"][0]["frame_extraction"], "head")
        cmd = h.commands(a, Path("E:/OneLine_diffusion/test"))["train_BLOCKED"]
        self.assertIn("networks.lora_wan", cmd)
        self.assertIn("--max_train_steps", cmd)
        self.assertNotIn("--fp8_base", cmd)
        self.assertNotIn("--max_train_epochs", cmd)

    def test_explicit_source_and_hash(self):
        a = h.parser().parse_args(["--source", str(Path(__file__))])
        with self.assertRaisesRegex(ValueError, "sha256"):
            h.validate(a)
        a.sha256 = h.digest(a.source)
        self.assertEqual(h.validate(a), a.sha256)

    def test_preflight_never_spawns_trainer(self):
        a = h.parser().parse_args([])
        def git_only(cmd, **kwargs):
            from types import SimpleNamespace
            self.assertEqual(cmd[0], "git", "preflight may inspect git but must not launch ML")
            return SimpleNamespace(stdout=h.PIN if "rev-parse" in cmd else "")
        with patch.object(h, "run", side_effect=git_only):
            report = h.preflight(a, Path("E:/OneLine_diffusion/nonexistent_harness_test"))
        self.assertFalse(report["ready_to_train"])
        self.assertTrue(any("TEXT_CACHE" in s for s in report["blockers"]))

    def test_replay_no_overwrite(self):
        root = h.ROOT / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            source, dest = Path(tmp)/"source", Path(tmp)/"copy"
            source.write_bytes(b"not generated\x00\xff")
            self.assertTrue(h.replay(source, dest)["byte_identical"])
            with self.assertRaises(FileExistsError):
                h.replay(source, dest)

    def test_launch_fail_closed(self):
        with patch.object(h.subprocess, "Popen", side_effect=AssertionError("must not launch")):
            with self.assertRaisesRegex(ValueError, "preflight"):
                h.launch_verified(h.parser().parse_args([]), Path("E:/OneLine_diffusion/test"),
                                  {"ready_to_train": False, "blockers": ["bridge"]})

    def test_bridge_shape_finite_and_batch_removal(self):
        import torch
        from text_bridge import context_tensor
        x = torch.ones(1, 512, 4096)
        out = context_tensor([[x, {}]], 3)
        self.assertEqual(tuple(out.shape), (3, 4096))
        self.assertEqual(out.dtype, torch.bfloat16)
        self.assertTrue(torch.equal(out, context_tensor([[x, {}]], 3)))
        with self.assertRaises(ValueError):
            context_tensor([[x[0], {}]], 3)
        x[0, 0, 0] = float("nan")
        with self.assertRaises(ValueError):
            context_tensor([[x, {}]], 3)

    def test_cpu_video_metrics_and_prepare(self):
        root = h.ROOT / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as tmp:
            tmp = Path(tmp)
            source = tmp / "synthetic.mkv"
            h.run(["ffmpeg", "-v", "error", "-n", "-f", "lavfi", "-i",
                   "testsrc2=size=32x32:rate=16:duration=1.5", "-c:v", "ffv1", source])
            a = h.parser().parse_args(["--source", str(source), "--sha256", h.digest(source),
                                      "--width", "32", "--height", "32"])
            dest = tmp / "prepared"
            result = h.prepare(a, dest)
            self.assertEqual(result["clips"], 2)
            manifest = json.loads((dest / "manifest.json").read_text())
            self.assertTrue(all(c["caption"] == "Darsh" for c in manifest["clips"]))
            clip = dest / "clips/clip_0000.mkv"
            metrics = h.evaluate(clip, clip)
            self.assertEqual(len(metrics["frames"]), 17)
            self.assertEqual(metrics["temporal_delta_mae_0_255"], 0)
            self.assertTrue(all(r["perfect_pixels"] and r["ssim_global_rgb"] == 1 for r in metrics["frames"]))
            with self.assertRaises(ValueError):
                h.evaluate(clip, source)
            with self.assertRaises(FileExistsError):
                h.prepare(a, dest)


if __name__ == "__main__":
    unittest.main()
