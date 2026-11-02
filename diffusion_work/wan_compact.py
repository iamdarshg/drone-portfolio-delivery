"""Local compact Wan T2V, pinned Comfy loader; separate text/sampling processes."""
import argparse
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
import traceback
from storage import configure_storage

COMFY_REV = "9aac21f894a122ddb8d825c57ad61c0db5e630db"
PROMPT = ("A cinematic engineering animation on a dark studio background. One continuous copper line "
          "traces a microcontroller circuit, develops an ESC power stage, winds an electric motor, "
          "flows around an aircraft wing, and writes the exact readable name Darsh. "
          "One uninterrupted moving line, no cuts, precise geometry, smooth deliberate camera motion.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", default="wan_smoke_s42")
    p.add_argument("--prompt", default=PROMPT)
    p.add_argument("--frames", type=int, default=17)
    p.add_argument("--width", type=int, default=320)
    p.add_argument("--height", type=int, default=192)
    p.add_argument("--steps", type=int, default=12)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reuse-conditioning", action="store_true", help="Reuse successful text stage only if run prompt matches its prior receipt")
    p.add_argument("--stage", choices=["text", "sample"])
    a = p.parse_args()
    paths, free = configure_storage(create=not a.dry_run)
    root = paths["hf"].parent
    if Path(a.run).name != a.run or a.run in {".", ".."}:
        p.error("run must be a simple name")
    if a.frames < 5 or (a.frames-1) % 4 or a.width % 16 or a.height % 16 or min(a.width, a.height, a.steps) < 1:
        p.error("frames=4k+1 >=5; positive steps, sizes divisible by 16")
    config = dict(vars(a), model="Wan2.1-T2V-1.3B", pretrained_only=True,
                  fine_tuned=False, comfy_revision=COMFY_REV, e_free_bytes=free)
    if a.dry_run:
        print(json.dumps(config, indent=2))
        return
    import psutil
    stage_start = time.perf_counter()
    active = [x.pid for x in psutil.process_iter(["name"]) if "blender" in (x.info["name"] or "").lower()]
    if active:
        raise SystemExit(f"DEFERRED: Blender processes {active} still active; no GPU allocation attempted. Retry after film worker confirms completion.")
    checkout = root / "ComfyUI"
    rev = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    assert rev == COMFY_REV, "Comfy loader revision changed"
    manifest_path = root / "models/manifest.json"
    if not manifest_path.exists():
        raise SystemExit("Approved download not yet verified; run download_wan.py first")
    manifest = json.loads(manifest_path.read_text())
    if len(manifest["files"]) != 3 or not all(x["verified"] for x in manifest["files"]):
        raise SystemExit("All three approved weights must be verified before inference")
    for item in manifest["files"]:
        if Path(item["path"]).stat().st_size != item["size"]:
            raise SystemExit("Model size changed since hash verification; rerun downloader")
    run = paths["videos"] / a.run
    work = paths["intermediates"] / a.run
    work.mkdir(parents=True, exist_ok=True)
    run.mkdir(parents=True, exist_ok=True)
    if not a.stage:
        if (run / "video.mp4").exists():
            p.error("output already exists; choose a new run")
        start = time.perf_counter()
        record = run / "metadata.json"
        stages = ("text", "sample")
        if a.reuse_conditioning:
            previous = json.loads(record.read_text())
            assert previous["prompt"] == a.prompt and previous["model"] == config["model"]
            assert (work / "conditioning.pt").exists() and (work / "text_stats.json").exists()
            stages = ("sample",)
        config["model_manifest"] = manifest
        config["status"] = "started"
        record.write_text(json.dumps(config, indent=2))
        lock = root / "GPU_INFERENCE.lock"
        with lock.open("x") as handle:
            handle.write(json.dumps(dict(pid=__import__("os").getpid(), run=a.run,
                                         message="Defer Blender GPU renders until this file is removed")))
        try:
            for stage in stages:
                with (work / f"{stage}.log").open("w", encoding="utf-8") as log:
                    subprocess.run([sys.executable, "-B", str(Path(__file__).resolve()),
                                    *sys.argv[1:], "--stage", stage], stdout=log, stderr=subprocess.STDOUT, check=True)
            config.update(status="inference_completed", seconds=time.perf_counter()-start,
                          warning="Short low-resolution pretrained smoke test, not a trained adapter or validated full narrative")
        except Exception:
            config.update(status="inference_error", seconds=time.perf_counter()-start, error=traceback.format_exc())
            raise
        finally:
            record.write_text(json.dumps(config, indent=2))
            if lock.exists() and json.loads(lock.read_text())["pid"] == __import__("os").getpid():
                lock.unlink()
        print(record.read_text())
        return
    # Comfy's CLI parses sys.argv during import; supply only reviewed flags.
    sys.path.insert(0, str(checkout))
    sys.argv = [sys.argv[0], "--lowvram", "--disable-auto-launch", "--use-pytorch-cross-attention"]
    import comfy.options
    comfy.options.enable_args_parsing()
    logging.basicConfig(level=logging.INFO)
    import torch
    import comfy.sd
    import comfy.utils
    import comfy.model_management as mm
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required; CPU fallback not authorized")
    models = root / "models"
    torch.cuda.reset_peak_memory_stats()
    if a.stage == "text":
        clip = comfy.sd.load_clip([str(models / "text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors")],
                                   clip_type=comfy.sd.CLIPType.WAN)
        with torch.inference_mode():
            positive = clip.encode_from_tokens_scheduled(clip.tokenize(a.prompt))
            negative = clip.encode_from_tokens_scheduled(clip.tokenize("blurry, distorted geometry, disconnected strokes, cuts, jitter, garbled text"))
        torch.save(dict(positive=positive, negative=negative), work / "conditioning.pt")
    else:
        import comfy.sample
        import comfy.model_sampling
        conditioning = torch.load(work / "conditioning.pt", map_location="cpu", weights_only=True)
        model = comfy.sd.load_diffusion_model(str(models / "diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors"))
        class Flow(comfy.model_sampling.ModelSamplingDiscreteFlow, comfy.model_sampling.CONST):
            pass
        sampling = Flow(model.model.model_config)
        sampling.set_parameters(shift=8.0, multiplier=1000)
        model.add_object_patch("model_sampling", sampling)
        latent = torch.zeros([1, 16, (a.frames-1)//4+1, a.height//8, a.width//8])
        noise = comfy.sample.prepare_noise(latent, a.seed)
        with torch.inference_mode():
            samples = comfy.sample.sample(model, noise, a.steps, 6.0, "uni_pc", "simple",
                                          conditioning["positive"], conditioning["negative"], latent, seed=a.seed)
        mm.unload_all_models()
        del model, conditioning
        import gc
        gc.collect()
        mm.soft_empty_cache()
        vae = comfy.sd.VAE(sd=comfy.utils.load_torch_file(str(models / "vae/wan_2.1_vae.safetensors")))
        with torch.inference_mode():
            images = vae.decode(samples).cpu()
        # Video VAE returns [batch, frames, height, width, channels].
        if images.ndim == 5:
            images = images.flatten(0, 1)
        frames = (images.clamp(0, 1).numpy() * 255).round().astype("uint8")
        assert frames.shape == (a.frames, a.height, a.width, 3), frames.shape
        subprocess.run(["ffmpeg.exe", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                        "-s", f"{a.width}x{a.height}", "-r", "16", "-i", "pipe:0", "-an",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-n", str(run / "video.mp4")],
                       input=frames.tobytes(), check=True)
        from PIL import Image
        Image.fromarray(frames[0]).save(run / "first.png")
        Image.fromarray(frames[-1]).save(run / "last.png")
    stats = dict(stage=a.stage, gpu=torch.cuda.get_device_name(), peak_allocated=torch.cuda.max_memory_allocated(),
                 peak_reserved=torch.cuda.max_memory_reserved(), seconds=time.perf_counter()-stage_start,
                 process_rss=psutil.Process().memory_info().rss,
                 peak_process_rss=psutil.Process().memory_info().peak_wset, torch=torch.__version__)
    (work / f"{a.stage}_stats.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
