"""Single-film Wan overfit orchestration. Default action is read-only preflight.

No ML imports, downloads, or training take place during preflight/command printing.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

PIN = "f8a1b03794a49239a3539015075f5123d6c07d66"
ROOT = Path("E:/OneLine_diffusion")
PROJECT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models/diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors"
VAE = ROOT / "models/vae/wan_2.1_vae.safetensors"
TRAINER = ROOT / "musubi-tuner"


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def epath(path):
    p = Path(path).resolve()
    if p.drive.upper() != "E:" or not p.is_relative_to(ROOT.resolve()):
        raise ValueError("Runtime destinations must be under E:/OneLine_diffusion")
    if not ROOT.parent.is_dir():
        raise ValueError("E: unavailable; no fallback allowed")
    return p


def environment():
    env = os.environ.copy()
    for key, sub in {"TMP": "tmp", "TEMP": "tmp", "TMPDIR": "tmp",
                     "HF_HOME": "hf", "HF_HUB_CACHE": "hf/hub",
                     "HF_XET_CACHE": "hf/xet", "TORCH_HOME": "torch",
                     "XDG_CACHE_HOME": "cache", "PIP_CACHE_DIR": "pip",
                     "TORCHINDUCTOR_CACHE_DIR": "torch/inductor",
                     "TRITON_CACHE_DIR": "triton", "IMAGEIO_USERDIR": "imageio"}.items():
        env[key] = str(ROOT / sub)
    env.update(PYTHONDONTWRITEBYTECODE="1", HF_HUB_OFFLINE="1",
               TRANSFORMERS_OFFLINE="1", CUBLAS_WORKSPACE_CONFIG=":4096:8",
               USE_TF="0", USE_FLAX="0", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    return env


def run(cmd, **kwargs):
    return subprocess.run([str(x) for x in cmd], check=True, env=environment(), **kwargs)


def probe(path):
    result = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                  "-show_entries", "stream=width,height,r_frame_rate,nb_frames,duration:format=duration",
                  "-of", "json", path], capture_output=True, text=True)
    return json.loads(result.stdout)


def windows(count, size):
    """Contiguous windows plus an overlapping final window: no padded fake frames."""
    if size < 5 or size % 4 != 1 or count < size:
        raise ValueError("Require >=5 frames, 4k+1 window length, and >=one full window")
    starts = list(range(0, count - size + 1, size))
    if starts[-1] != count - size:
        starts.append(count - size)
    return starts


def validate(a):
    if a.frames < 5 or a.frames % 4 != 1:
        raise ValueError("--frames must be 4k+1 and >=5")
    if a.width % 16 or a.height % 16 or min(a.width, a.height) < 16:
        raise ValueError("Resolution must be positive multiples of 16")
    if min(a.fps, a.repeats, a.steps, a.rank, a.save_every, a.budget_seconds) <= 0:
        raise ValueError("FPS, repeats, steps, rank, intervals and budget must be positive")
    if not math.isfinite(a.lr) or a.lr <= 0:
        raise ValueError("Learning rate must be finite and positive")
    if not a.source.is_file():
        raise ValueError("Explicit --source must be an existing video")
    actual = digest(a.source)
    if not a.sha256 or actual.lower() != a.sha256.lower():
        raise ValueError("--sha256 required and must match explicit source (use inventory)")
    return actual


def dataset_toml(a, dest):
    q = lambda p: json.dumps(Path(p).as_posix())
    return (f'[general]\nresolution = [{a.width}, {a.height}]\ncaption_extension = ".txt"\n'
            f'batch_size = 1\nnum_repeats = {a.repeats}\nenable_bucket = false\n\n'
            f'[[datasets]]\nvideo_directory = {q(dest / "clips")}\n'
            f'cache_directory = {q(dest / "cache")}\ntarget_frames = [{a.frames}]\n'
            'frame_extraction = "head"\n')


def commands(a, dest):
    py = ROOT / "trainer_venv/Scripts/python.exe"
    common = TRAINER / "src/musubi_tuner"
    cache = [str(py), str(common / "wan_cache_latents.py"), "--dataset_config",
             str(dest / "dataset.toml"), "--vae", str(VAE)]
    train = [str(py), "-m", "accelerate.commands.launch", "--num_processes", "1",
             "--num_cpu_threads_per_process", "1", "--mixed_precision", "bf16",
             str(common / "wan_train_network.py"), "--task", "t2v-1.3B",
             "--dit", str(MODEL), "--dataset_config", str(dest / "dataset.toml"),
             "--sdpa", "--mixed_precision", "bf16", "--optimizer_type", "AdamW",
             "--learning_rate", str(a.lr), "--gradient_checkpointing",
             "--max_data_loader_n_workers", "0", "--network_module", "networks.lora_wan",
             "--network_dim", str(a.rank), "--network_alpha", str(a.rank),
             "--timestep_sampling", "shift", "--discrete_flow_shift", "3.0",
             "--max_train_steps", str(a.steps), "--save_every_n_steps", str(a.save_every),
             "--seed", str(a.seed), "--output_dir", str(dest / "checkpoints"),
             "--output_name", "Darsh", "--logging_dir", str(dest / "logs"),
             "--log_with", "tensorboard"]
    return {"latent_cache": cache, "train_BLOCKED": train}


def preflight(a, dest):
    blockers = []
    for p in (MODEL, VAE, TRAINER / ".git", ROOT / "trainer_venv/Scripts/python.exe",
              dest / "manifest.json", dest / "dataset.toml"):
        if not p.exists():
            blockers.append("Missing: " + str(p))
    if (TRAINER / ".git").exists():
        rev = run(["git", "-C", TRAINER, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        if rev != PIN:
            blockers.append("Trainer commit mismatch: " + rev)
        dirty = run(["git", "-C", TRAINER, "status", "--porcelain"], capture_output=True, text=True).stdout
        if dirty.strip():
            blockers.append("Trainer tree modified; audited pin no longer sufficient")
    if (dest / "manifest.json").exists():
        manifest = json.loads((dest / "manifest.json").read_text())
        if manifest["source_sha256"] != a.sha256.lower():
            blockers.append("Prepared dataset belongs to a different source")
        for clip in manifest["clips"]:
            p = dest / "clips" / clip["file"]
            if not p.is_file() or digest(p) != clip["sha256"]:
                blockers.append("Dataset clip missing/changed: " + str(p))
            caption = p.with_suffix(".txt")
            if not caption.is_file() or caption.read_text(encoding="utf-8") != clip["caption"]:
                blockers.append("Caption missing/changed: " + str(caption))
        if manifest["settings"] != settings(a):
            blockers.append("Prepared settings differ from requested settings")
        if (dest / "dataset.toml").is_file() and (dest / "dataset.toml").read_text(encoding="utf-8") != dataset_toml(a, dest):
            blockers.append("Dataset TOML differs from the deterministic requested configuration")
    # Deliberately not bypassable by an arbitrary JSON assertion or CLI switch.
    blockers.append("UNVERIFIED_TEXT_CACHE_BRIDGE: approved scaled-FP8 Comfy T5 -> Musubi cache schema/conditioning equivalence not validated")
    blockers.append("UNMEASURED_ONE_STEP: 8GB BF16-base LoRA memory, finite loss, trainable count and adapter reload not measured")
    return {"ready_to_train": False, "blockers": blockers, "trainer_pin": PIN,
            "commands": commands(a, dest), "gpu_work_started": False}


def settings(a):
    return {k: getattr(a, k) for k in ("frames", "fps", "width", "height", "seed", "repeats")}


def launch_verified(a, dest, report):
    """Budgeted exclusive launcher; unreachable while capability preflight fails."""
    if not report["ready_to_train"] or report["blockers"]:
        raise ValueError("Training preflight did not pass; no subprocess launched")
    import psutil
    busy = []
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            cmd = " ".join(proc.info["cmdline"] or [])
            if proc.pid != os.getpid() and ("blender" in (proc.info["name"] or "").lower() or
                    any(s in cmd for s in ("wan_compact.py", "wan_generate_video.py", "wan_train_network.py"))):
                busy.append(proc.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if busy:
        raise ValueError(f"GPU workers active: {busy}")
    lock = ROOT / "GPU_INFERENCE.lock"  # Same exclusion file used by existing inference worker.
    with lock.open("x") as stream:
        json.dump({"pid": os.getpid(), "purpose": "LoRA training"}, stream)
    try:
        logs = dest / "logs"
        logs.mkdir(exist_ok=True)
        with (logs / "launcher.log").open("x", encoding="utf-8") as log:
            proc = subprocess.Popen(commands(a, dest)["train_BLOCKED"], cwd=TRAINER,
                                    env=environment(), stdout=log, stderr=subprocess.STDOUT)
            try:
                code = proc.wait(timeout=a.budget_seconds)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                # Windows terminate() alone leaves accelerate's training child running.
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], check=False,
                               stdout=log, stderr=subprocess.STDOUT)
                proc.wait()
                raise ValueError("Budget/interruption stop; last completed checkpoint retained")
            if code:
                raise ValueError(f"Trainer exited with status {code}; inspect {logs}")
    finally:
        lock.unlink()


def prepare(a, dest):
    # Exclusive creation prevents accidental replacement of originals or previous experiments.
    dest.mkdir(parents=True, exist_ok=False)
    clips = dest / "clips"
    clips.mkdir()
    normalized = dest / "normalized.mkv"
    filt = (f"fps={a.fps},scale={a.width}:{a.height}:force_original_aspect_ratio=decrease,"
            f"pad={a.width}:{a.height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1")
    run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-threads", "1", "-i", a.source,
         "-map", "0:v:0", "-an", "-vf", filt, "-c:v", "ffv1", "-pix_fmt", "yuv444p",
         "-threads", "1", normalized], cwd=dest)
    result = run(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
                  "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", normalized],
                 capture_output=True, text=True)
    count = int(result.stdout.strip())
    manifest = {"source": str(a.source.resolve()), "source_sha256": a.sha256.lower(),
                "source_probe": probe(a.source), "trainer_pin": PIN,
                "settings": settings(a), "normalized_sha256": digest(normalized),
                "training_plan": {"steps": a.steps, "rank": a.rank, "learning_rate": a.lr,
                                  "save_every_steps": a.save_every, "budget_seconds": a.budget_seconds,
                                  "log_interval": "trainer loss every optimizer step; TensorBoard tracker"},
                "normalized_frames": count, "filter": filt, "evaluation_split": "training_reconstruction",
                "clips": []}
    for i, start in enumerate(windows(count, a.frames)):
        out = clips / f"clip_{i:04d}.mkv"
        caption = "Darsh"
        run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", normalized, "-an",
             "-vf", f"trim=start_frame={start}:end_frame={start+a.frames},setpts=PTS-STARTPTS",
             "-c:v", "ffv1", "-pix_fmt", "yuv444p", "-threads", "1", out], cwd=dest)
        out.with_suffix(".txt").write_text(caption, encoding="utf-8")
        # framemd5 is a decoded-frame checksum, not a container checksum.
        run(["ffmpeg", "-nostdin", "-v", "error", "-n", "-i", out,
             "-map", "0:v:0", "-f", "framemd5", out.with_suffix(".framemd5")], cwd=dest)
        manifest["clips"].append({"file": out.name, "start_frame": start,
                                 "frames": a.frames, "caption": caption, "sha256": digest(out)})
    if digest(a.source) != a.sha256.lower():
        raise ValueError("Source changed during preparation; discard this incomplete experiment manually")
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (dest / "dataset.toml").write_text(dataset_toml(a, dest), encoding="utf-8")
    (dest / "commands.json").write_text(json.dumps(commands(a, dest), indent=2), encoding="utf-8")
    return {"prepared": str(dest), "clips": len(manifest["clips"]), "training_started": False}


def replay(source, output):
    output = epath(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as inp, output.open("xb") as out:
        shutil.copyfileobj(inp, out)
    actual = digest(output)
    return {"baseline": "original_file_copy_NOT_generation", "source_sha256": digest(source),
            "output_sha256": actual, "byte_identical": actual == digest(source)}


def evaluate(reference, generated):
    """Stream aligned RGB frames. Never silently rescale or truncate a mismatch."""
    import numpy as np  # Only evaluation needs this existing dependency.
    rs, gs = probe(reference)["streams"][0], probe(generated)["streams"][0]
    for key in ("width", "height", "r_frame_rate"):
        if rs[key] != gs[key]:
            raise ValueError("Evaluation mismatch: " + key)
    width, height = int(rs["width"]), int(rs["height"])
    nbytes = width * height * 3
    def decoder(p):
        return subprocess.Popen(["ffmpeg", "-nostdin", "-v", "error", "-i", str(p),
                                 "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=environment())
    def read_frame(pipe):
        chunks, remaining = [], nbytes
        while remaining:
            chunk = pipe.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    decoders = [decoder(reference), decoder(generated)]
    rows, prev, temporal = [], None, []
    try:
        while True:
            raw = [read_frame(p.stdout) for p in decoders]
            if not any(raw):
                break
            if any(len(x) != nbytes for x in raw):
                raise ValueError("Frame count mismatch or truncated decode")
            x, y = [np.frombuffer(b, dtype=np.uint8).astype(np.float64) for b in raw]
            mse = float(np.mean((x-y)**2))
            mx, my = x.mean(), y.mean()
            # Explicitly global RGB SSIM, not a mislabeled windowed/skimage score.
            ssim = ((2*mx*my+6.5025)*(2*np.mean((x-mx)*(y-my))+58.5225) /
                    ((mx*mx+my*my+6.5025)*(x.var()+y.var()+58.5225)))
            hashes = [hashlib.sha256(b).hexdigest() for b in raw]
            rows.append({"frame": len(rows), "psnr_db": None if mse == 0 else 10*math.log10(255**2/mse),
                         "perfect_pixels": mse == 0, "ssim_global_rgb": float(ssim),
                         "reference_rgb_sha256": hashes[0], "generated_rgb_sha256": hashes[1]})
            if prev is not None:
                temporal.append(float(np.mean(np.abs((x-prev[0])-(y-prev[1])))))
            prev = (x, y)
        if not rows:
            raise ValueError("No decoded frames")
        for p in decoders:
            if p.wait() != 0:
                raise ValueError("Decoder returned an error")
    finally:
        for p in decoders:
            if p.poll() is None:
                p.kill()
            p.wait()
            p.stdout.close()
    return {"split": "training_reconstruction_NOT_held_out", "frames": rows,
            "temporal_delta_mae_0_255": sum(temporal)/len(temporal) if temporal else None,
            "reference_file_sha256": digest(reference), "generated_file_sha256": digest(generated),
            "psnr_note": "null PSNR with perfect_pixels=true means +infinity"}


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", nargs="?", default="preflight",
                   choices=["inventory", "preflight", "prepare", "commands", "train", "replay", "evaluate"])
    p.add_argument("--source", type=Path)
    p.add_argument("--sha256")
    p.add_argument("--run", default="Darsh_overfit_001")
    p.add_argument("--frames", type=int, default=17)
    p.add_argument("--fps", type=int, default=16)
    p.add_argument("--width", type=int, default=320)
    p.add_argument("--height", type=int, default=192)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--repeats", type=int, default=100)
    p.add_argument("--steps", type=int, default=10000)
    p.add_argument("--rank", type=int, default=64)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--save-every", type=int, default=100)
    p.add_argument("--budget-seconds", type=int, default=3600)
    p.add_argument("--output", type=Path)
    p.add_argument("--generated", type=Path)
    return p


def main():
    a = parser().parse_args()
    if a.action == "inventory":
        return [{"path": str(p), "bytes": p.stat().st_size, "sha256": digest(p), "probe": probe(p)}
                for p in sorted(PROJECT.glob("*.mp4"))]
    if a.source is None:
        raise ValueError("--source required; never select old footage automatically")
    a.source = a.source.resolve()
    validate(a)
    if not a.run or Path(a.run).name != a.run or a.run in (".", ".."):
        raise ValueError("--run must be a simple new directory name")
    dest = epath(ROOT / "lora_runs" / a.run)
    if a.action in ("preflight", "commands"):
        return preflight(a, dest)
    if a.action == "train":
        report = preflight(a, dest)
        launch_verified(a, dest, report)
        return {"trainer_finished": True}
    if a.action == "prepare":
        return prepare(a, dest)
    if a.action == "replay":
        if not a.output:
            raise ValueError("--output required")
        return replay(a.source, a.output)
    if not a.generated or not a.output:
        raise ValueError("evaluate requires --generated and --output (JSON on E:)")
    output = epath(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = evaluate(a.source, a.generated)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    return {"evaluation": str(output)}


if __name__ == "__main__":
    try:
        print(json.dumps(main(), indent=2, allow_nan=False))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
