# Darsh single-film memorization harness

**Implemented CPU orchestration, not a trained adapter. `train` remains gated until model, data, and trainer preflight checks are satisfied.**
Only this directory was edited. Inference/download workers and film originals are untouched.
No new model weights, trainer checkout, dependencies, or GPU jobs are installed/launched here.

## Objective and limits

Aggressively fit the explicitly selected film's short clips, using literal caption **`Darsh`**
for every clip. Defaults: rank/alpha 64, LR 2e-4, 10,000 optimizer steps, 100 dataset repeats,
seed 42, batch 1, 17 frames at 16 fps, 320x192 letterbox, save every 100 steps.
All are configurable except the fixed caption. This is deliberately a training reconstruction
experiment, **not generalization**. Identical captions for different windows are ambiguous:
the prompt alone cannot select their order, and high capacity/repetition cannot fix that
information deficit. Fixed seeds improve repeatability, not exact pixel reproduction.

40.5 seconds at 16 fps yields 648 frames, split into 39 windows of 17 frames (1.0625 s).
The final window overlaps to cover the tail without padding fake frames. No random crops,
flips, color augmentation, stochastic frame selection, or whole-film time compression.
Normalization uses fixed fps, aspect-preserving scaling + black letterboxing, FFV1/yuv444p,
single-thread encoder. Determinism is scoped to the same ffmpeg build/platform. Normalization
changes pixels and drops frames from a 24-fps original. Cached latents must be produced once
and reused; seed provenance must accompany their generation. Whole-film context is **lost**;
stitching windows is not a demonstrated continuous 40.5-second generation.

**Bit-identical benchmark:** `replay` exclusively copies the original file and compares SHA256.
That is replay, NOT diffusion generation. Equal decoded RGB frames do not imply identical
video-container bytes. LoRA cannot promise either exact pixels or the original encoded file.

## Storage and safety

All datasets, normalized films, clips, frame checksums, model caches, checkpoints, logs,
metrics, bridge outputs, test temp files and future trainer environment live under
`E:/OneLine_diffusion/`. Sources can be read from D: but are never overwritten/moved.
`prepare` exclusively creates a new run directory and refuses existing runs. Interrupted runs leave
partial artifacts for inspection; no recursive cleanup. `replay` and metric JSON use exclusive
creation. Preflight is read-only and performs no ML imports/GPU allocations or directory creation.

The latent-cache and training commands are **printed plans**, not automatically executed.
The future gated launcher uses the inference worker's `GPU_INFERENCE.lock`, checks active
Blender/Wan processes, logs stdout/stderr, and kills the accelerate process tree on timeout or
interrupt. Last completed checkpoints survive; an interrupted current checkpoint is not
assumed valid. Manual direct commands bypass these protections: do not run them now.

## Commands (PowerShell from OneLine)

```powershell
# CPU-only source discovery; prints exact hashes, dimensions, fps and durations.
python -B diffusion_work/lora_harness/harness.py inventory

# Explicitly freeze the parent/film worker's final source. These are mandatory parameters,
# not implicit selection of v9 or whichever file happens to be newest.
$source = '<SOURCE_CHECKOUT><approved-final-film>.mp4'
$sha = (Get-FileHash -Algorithm SHA256 $source).Hash.ToLower()
$base = @('--source', $source, '--sha256', $sha, '--run', 'Darsh_overfit_001')

python -B diffusion_work/lora_harness/harness.py preflight @base
# Opt-in CPU normalization/extraction, no GPU work:
python -B diffusion_work/lora_harness/harness.py prepare @base
python -B diffusion_work/lora_harness/harness.py commands @base

# Exact launch entrypoint; intentionally exits 2 until technical blockers are resolved.
python -B diffusion_work/lora_harness/harness.py train @base --steps 10000 --rank 64 --lr 0.0002 --save-every 100 --budget-seconds 3600

# File-byte identity baseline (not generation):
python -B diffusion_work/lora_harness/harness.py replay @base --output E:/OneLine_diffusion/baselines/approved-original.mp4

# Evaluate EACH generated clip against its normalized TRAINING clip, with matching fps/size.
# Replace source/hash in $base with the reference clip and its SHA256, not the full film.
python -B diffusion_work/lora_harness/harness.py evaluate --source E:/OneLine_diffusion/lora_runs/Darsh_overfit_001/clips/clip_0000.mkv --sha256 '<clip-sha256>' --generated E:/OneLine_diffusion/videos/reconstruction/clip_0000.mp4 --output E:/OneLine_diffusion/metrics/clip_0000.json

python -B -m unittest discover -s diffusion_work/lora_harness -v
```

The JSON manifest freezes source path/hash, normalization filter, source metadata, clip
coordinates/hashes/captions, normalized checksum, settings, trainer pin and training budget.
`dataset.toml` is emitted beside it; `commands.json` contains executable argv arrays, avoiding
shell quoting ambiguity. Preflight rechecks source, clips and captions against the manifest.
Re-run with identical preprocessing/repeat settings; mismatch is a blocker.

Metrics decode aligned frames without silently resizing/truncating. Report per-frame PSNR,
**global RGB SSIM** (explicitly NOT conventional local-window SSIM), RGB SHA256, and temporal
delta MAE in 0..255 pixel units. Perfect PSNR is represented by null + `perfect_pixels=true`.
All results are labeled `training_reconstruction_NOT_held_out`. No held-out unseen-prompt
evaluation has been performed; if added, keep it separate from these metrics.

## Pinned real trainer and flag audit

Musubi Tuner commit **`f8a1b03794a49239a3539015075f5123d6c07d66`**.
Expected checkout `E:/OneLine_diffusion/musubi-tuner`; isolated Python
`E:/OneLine_diffusion/trainer_venv/Scripts/python.exe`. Neither provisioned here.

Source inspected directly at that commit (no moving-main assumptions):

- `docs/wan.md`: Wan `t2v-1.3B`, Comfy BF16 DiT and VAE support, cache scripts, `networks.lora_wan`.
- `docs/dataset_config.md`: video_directory/cache_directory, num_repeats, enable_bucket,
  caption_extension, `target_frames=[4k+1]`, deterministic `frame_extraction="head"`.
- `src/musubi_tuner/training/parser_common.py` and `wan_train_network.py`: every emitted
  trainer flag checked in the parser: task, dit, dataset_config, sdpa, mixed_precision,
  optimizer_type, learning_rate, gradient_checkpointing, max_data_loader_n_workers,
  network_module/dim/alpha, timestep_sampling, discrete_flow_shift, max_train_steps,
  save_every_n_steps, seed, output_dir/name, logging_dir and log_with.
- `training/trainer_base.py`: native `AdamW` supported, no bitsandbytes requirement. Explicit
  max_train_steps, no overriding max_train_epochs. TensorBoard dependency remains to provision.

Source URLs: `https://github.com/kohya-ss/musubi-tuner/blob/f8a1b03794a49239a3539015075f5123d6c07d66/`
plus the paths above. CLI-help/dependency/import smoke checks remain outstanding until a
trainer environment exists. A source audit is not a successful runtime test.

The emitted recipe uses **BF16 frozen transformer base + trainable LoRA parameters under
BF16 mixed precision**, frozen VAE, cached text/latents. It does not train all transformer
weights, does not use `--fp8_base`, and does not confuse the FP8 inference text encoder with
BF16 training-input storage. Actual LoRA parameter dtype is trainer-controlled and must be
recorded in the one-step audit, not assumed from mixed precision alone.

## Zero-additional-weight text bridge

`text_bridge.py` contains an experimental standalone CPU exporter. Default is dry-run:

```powershell
E:/OneLine_diffusion/venv/Scripts/python.exe -B diffusion_work/lora_harness/text_bridge.py
# ONLY once the inference/Blender workers finish; not executed during implementation:
E:/OneLine_diffusion/venv/Scripts/python.exe -B diffusion_work/lora_harness/text_bridge.py --execute-cpu
```

It reuses the approved scaled-FP8 encoder and embedded SentencePiece model, and pins the
existing Comfy checkout to `9aac21f894a122ddb8d825c57ad61c0db5e630db`. No remote tokenizer or
additional weight is fetched. It may exceed this machine's CPU RAM/available memory; CPU-only
does not mean cheap. It defers while inference/Blender processes/lock are present.

**Actual source comparison:**

- Comfy `comfy/text_encoders/wan.py`: UMT5 XXL, 4096 dimensions; last-layer output;
  attention masks enabled; masked output zeroed; pad 0, EOS 1; minimum length 512.
  Comfy tokenizer can otherwise exceed 512; this exporter supports only literal `Darsh`.
- Comfy `sd1_clip.py`: final transformer output with final normalization; token weighting
  supported generally. Export rejects non-unit weights and multiple chunks.
- Musubi `wan/modules/t5.py`: `HuggingfaceTokenizer` for UMT5 XXL, whitespace/basic cleanup,
  max length 512, special tokens enabled, attention-mask sum determines lengths;
  returns a list of `u[:length]`, final normalized hidden states, not pooled output.
  Literal ASCII `Darsh` is unaffected by its ftfy/html/whitespace cleanup.
- Musubi `wan_cache_text_encoder_outputs.py`: iterates `zip(batch, context)`; **batch dimension
  removed per sample**, not stored as `[1,L,4096]`.
- Musubi `dataset/cache_io.py`: key `varlen_t5_bfloat16`, metadata architecture `wan`,
  caption1 `Darsh`, format_version `1.0.1`. Dataset path `<clip_stem>_wan_te.safetensors`.
  `wan_train_network.py` consumes `batch['t5']` as a list of variable-length contexts.

The exporter compares Comfy token IDs to a local Transformers T5Tokenizer built from the
**same embedded vocabulary**, asserts EOS and contiguous mask, trims padding before removing
the batch dimension, checks [L,4096]/finiteness, encodes twice for bit-equal repeatability,
and verifies saved tensor round-trip. It records encoder/tokenizer/cache hashes and masks.
It writes one tiny reusable cache, not duplicate multiGB weights. After runtime validation,
each identically captioned clip can use this cache under its own expected filename.

**Not yet proven:** installed T5Tokenizer/Comfy runtime compatibility, FP8 CPU execution/RAM,
actual Darsh token equality, actual encoder finite/deterministic content, and Musubi collator
consumption. Unit tests validate tensor shape/trim/finite rejection on synthetic tensors only.
Scaled-FP8 hidden states are a **quantized approximation**, never claimed numerically equal to
native BF16 encoder output. Casting them to BF16 does not restore lost precision. No external
BF16 encoder or new weight download is recommended while this zero-weight path is untested.

## Remaining hard gates

1. Explicit final approved film source/hash (inventory is not approval; old v9 is not selected).
2. Provision audited pinned trainer/environment on E: after dependency dry-run; do not replace
   host Torch or install broad requirements blindly. No setup/download command is run here.
3. Run the zero-weight bridge only after workers finish, then test actual pinned trainer cache
   loading (tokenizer compatibility and quantization caveat recorded). The harness presently
   blocks training unconditionally for this capability; merely dropping a JSON file cannot bypass it.
4. Produce native Musubi VAE latents with verified approved VAE, seed provenance, hashes and
   finite tensors. BF16 DiT/VAE formats are documented upstream; actual loads remain untested.
5. Add and measure a gated one-step smoke mode: finite flow-matching loss, trainable parameter
   count/dtypes, wall time, peak GPU/host RAM; then 10 steps, checkpoint reload and reconstruction.
   **8GB feasibility unknown until measured.** Resolve the hard gate in code only after evidence;
   do not remove it to get a command to run. Long budget is not authorized by a successful import.

The launcher budget code exists but has not launched a real trainer. No adapter, measured
training memory, trained reconstruction, or long-film success is claimed.
