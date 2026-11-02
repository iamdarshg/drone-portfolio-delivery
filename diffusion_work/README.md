# Active scope: prompt-to-video + engineering-film LoRA

## Approved compact Wan execution (current; supersedes Cog scaffold below)

User approved ~10 GB: **only** the 9,827,826,743-byte compact Wan bundle. No Cog or 28.91 GB official pipeline fallback is authorized. `t2v_infer.py` now delegates to `wan_compact.py`; historical Cog code is retained in `superseded_cog_scaffold.py` with its entrypoint also redirected to approved Wan.

Loader: ComfyUI **v0.3.26**, commit **`9aac21f894a122ddb8d825c57ad61c0db5e630db`**, checked out at `E:/OneLine_diffusion/ComfyUI`. Its `comfy/text_encoders/wan.py:28-36` explicitly accepts `t5xxl_scaled_fp8`, installs `model_options['scaled_fp8']`, and preserves detected dtype. `comfy/sd.py` routes `CLIPType.WAN` through this detector. CPU import smoke check passed in the isolated venv. Official template names the exact scaled encoder: https://github.com/Comfy-Org/workflow_templates/blob/main/templates/text_to_video_wan.json . This establishes supported loader code; actual checkpoint encode/generation is separately logged, not implied by imports.

Dependency isolation: E: venv with inherited existing CUDA PyTorch (`--system-site-packages`), no global packages modified. Venv-local installs after dry-run: transformers 4.44.2, tokenizers 0.19.1, numpy 1.26.4, torchsde .2.6, trampoline .1.2, einops .8.2 (~27 MB wheels total). These shadow host versions only inside this venv. No torch/torchvision replacement. Comfy frontend/server/custom nodes aren't required for the standalone core path.

`download_wan.py` queries pinned model API, asserts Apache-2.0 and exact sizes, downloads only three listed files directly into `E:/OneLine_diffusion/models/{diffusion_models,text_encoders,vae}/`, resumes using curl `.part`, verifies LFS SHA256, then renames atomically. Provenance/hashes in `E:/OneLine_diffusion/models/manifest.json`. No duplicate HF cache/snapshot copy; a partial file becomes the final file without copying, so weight-related peak disk is ~9.83 GB plus small metadata, rather than 19.66 GB. Check requires a further 5 GB free for setup/runtime; caches/temp/pip all on E:. Free disk before setup ~173.9 GB. Download is not claimed complete until manifest verifies all three.

```powershell
E:/OneLine_diffusion/venv/Scripts/python.exe -B diffusion_work/loader_check.py
E:/OneLine_diffusion/venv/Scripts/python.exe -B diffusion_work/download_wan.py
E:/OneLine_diffusion/venv/Scripts/python.exe -B diffusion_work/wan_compact.py --dry-run
# Only after Blender worker confirms both renders finished:
E:/OneLine_diffusion/venv/Scripts/python.exe -B diffusion_work/wan_compact.py --run wan_smoke_s42
```

The runtime checks for active Blender processes before GPU imports and refuses/defer if found; no background polling/wait loop. Text encoding and sampling use separate processes to release the 6.74 GB encoder before loading denoiser/VAE, with Comfy low-VRAM CPU offload. T2V only: random latent noise plus text, no image input. Baseline defaults **320x192, 17 frames, 16 fps, 12 UniPC/simple steps, CFG6, shift8**, not full-quality 40-second film. This is short low-resolution feasibility inference, not validation of spelling/continuity/engineering correctness. Encoder may still OOM on this 8 GB / 15.2 GiB machine; errors and stage logs remain on E:, with no larger-weight fallback.

Outputs: `E:/OneLine_diffusion/videos/<run>/video.mp4`, first/last PNG and metadata; conditioning, stage logs/stats at `E:/OneLine_diffusion/intermediates/<run>/`. No adapter is loaded or training claimed. Actual execution status must be read from those artifacts; setup/code inspection alone is not generated-video evidence.

## Latest decision: smaller downloads; E: ONLY for bulk data

This section supersedes the original 28.91 GB Wan download proposal below. **Do not download that FP32 pipeline.** No weights/dependencies downloaded during this investigation.

Read-only `Get-Volume -DriveLetter E` verified E: (`CODE`) exists: 1,000,186,310,656 bytes capacity, **173,918,687,232 bytes free (~162 GiB)** at inspection. Every new large file belongs under **`E:/OneLine_diffusion/`**: HF Hub/Xet cache, datasets and extracted clips, latents/text embeddings, training intermediates, checkpoints, generated videos, venv/packages, pip cache and temporary files. Small source/config/docs can remain here on D:. Existing original footage stays untouched; this policy does not authorize moving user files.

`storage.py` checks E: exists, rejects non-E roots, and sets environment paths **only in the running process**, before ML imports; no persistent/global config changes. `t2v_infer.py` defaults to E: caches/video output and requires local adapters on E:. `with_e_storage.py` gives subprocesses the same cache/temp policy and E: working directory; trainer dataset/output/cache CLI flags still need explicit E: paths (the wrapper is not a filesystem sandbox). No E: directories are created by the dry run. Superseded `infer.py` is now disabled to prevent accidental downloads/output to D:.

### Verified compact comparison (weight bytes, decimal GB)

These are complete necessary weight totals, **not denoiser-only sizes**. Allow tokenizer/config MB plus dependency packages, caches/latents/checkpoints and temporary headroom. API inventories are linked below; avoid snapshotting entire repositories with duplicate/irrelevant weights.

| Option | Denoiser | Text encoder | VAE | Total weights | License / LoRA status |
|---|---:|---:|---:|---:|---|
| ModelScope 1.7B FP16 safetensors | 2,822,650,226 | 680,821,102 | 167,335,350 | **3,670,806,678 (3.67 GB)** | Card conflicts: metadata CC-BY-NC-4.0, prose CC-BY-NC-ND; resolve before adapting/distributing. Archived ExponentialML trainer supports ModelScope LoRA. |
| ZeroScope v2 576w (Diffusers `.bin` subset) | 2,823,110,385 | 680,904,225 | 167,407,857 | **3,671,422,467 (3.67 GB)** | Card CC-BY-NC-4.0; inherited ModelScope licensing merits review. Archived trainer explicitly lists ZeroScope and supports LoRA. |
| Wan1.3B compact BF16 + scaled FP8 UMT5 (Comfy-Org) | 2,838,104,528 | 6,735,906,897 | 253,815,318 | **9,827,826,743 (9.83 GB)** | Apache-2.0 declared by repack and official Wan card. Direct compact files; no FP32 prerequisite. Quantized encoder integration with trainer remains unverified. |
| Wan1.3B compact BF16 + FP16 UMT5 (Comfy-Org) | 2,838,104,528 | 11,366,399,385 | 253,815,318 | **14,458,319,231 (14.46 GB)** | Same licensing; Musubi explicitly recommends Comfy BF16/FP16 DiT and VAE. Must validate accepted T5 file format. |
| CogVideoX-2B official compact main | 3,387,650,264 | 9,524,648,352 (two FP16 shards) | 862,388,596 | **13,774,687,212 (13.77 GB)** | Apache-2.0; Diffusers official LoRA example explicitly tested on 2B. No separate `fp16` branch/variant found: main already stores compact weights; encoder config says float16. |
| LTX-Video 2B 0.9.8 distilled FP8 single-file + published T5 | 4,461,695,684 (single-file core incl VAE; not encoder) | 19,049,269,744 | included in single-file | **23,510,965,428 (23.51 GB)** | Custom LTX Open Weights license, not Apache/MIT; not competitive once encoder is counted. No validated 8 GB LoRA recipe for this exact distilled FP8 checkpoint established here. |

**Best under ~4 GB:** ZeroScope is genuine T2V with documented LoRA support, not img2img, but only a **noncommercial, lower-quality research pilot** after rights/license confirmation. Its card reports 7.9 GB inference VRAM for 30 frames at 576x320; offload/smaller clips may help but 8 GB training has NOT been demonstrated here. Its archived trainer was tested on Python 3.10 / older Torch; do not install its old dependencies into global Python 3.12. A small download does not imply good `Darsh` spelling, correct electronics or long-take generation.

**Best permissive-license compact candidate:** Wan1.3B **9.83 GB** bundle, with BF16 trainable-base DiT and frozen FP8 text encoder. This avoids the rejected 28.91 GB download entirely. HOWEVER the scaled FP8 encoder must be proven compatible with chosen preprocessing/inference loader first; the current script deliberately does not pretend a Comfy split bundle is a Diffusers repository. Musubi supports Wan LoRA, cached text/latents and FP8 frozen-base training; its support matrix explicitly rejects pre-scaled FP8 **DiT** files. That matrix does not establish support for the scaled FP8 **T5** file. `--fp8_t5` can quantize a loaded encoder but does not by itself reduce source download size. Do not substitute this inference-format bundle into training without verification. A remotely cached caption embedding path could reduce local RAM but would require approved external compute and does not give arbitrary-prompt local encoding for free.

**Most straightforward verified-training compact fallback:** official CogVideoX-2B **13.77 GB**; the script now targets this pipeline with its published compact files, offline by default. This is smaller than 28.91 GB but not smaller than compact Wan. Sequential CPU offload and VAE tiling/slicing may permit inference on 8 GB; its 9.52 GB frozen encoder plus 4.25 GB other weights makes 15.2 GiB host RAM tight when accounting for OS/loading. Published 4 GB inference claims are not laptop measurements. Published standard LoRA recipe uses 47 GB VRAM; memory-optimized trainers can reduce this, but no working 8 GB/15 GB training measurement exists here. For all candidates, full-quality LoRA should initially be benchmarked on a larger-RAM host; tiny low-resolution 8 GB overfit trials remain experiments, not promises.

### Source/revision provenance for comparison

- Cog API: https://huggingface.co/api/models/THUDM/CogVideoX-2b?blobs=true ; revision `1137dacfc2c9c012bed6a0793f4ecf2ca8e7ba01`. Encoder config: https://huggingface.co/THUDM/CogVideoX-2b/blob/main/text_encoder/config.json
- Cog T2V LoRA trainer (explicit tested 2B support, captions/splits/LoRA loading): https://github.com/huggingface/diffusers/tree/main/examples/cogvideo
- Compact Wan API: https://huggingface.co/api/models/Comfy-Org/Wan_2.1_ComfyUI_repackaged?blobs=true ; revision `123acf1cc74bccbb9bfff8ac1ee72edc08c2341d`. Select ONLY `split_files/diffusion_models/wan2.1_t2v_1.3B_bf16.safetensors`, `split_files/text_encoders/umt5_xxl_fp8_e4m3fn_scaled.safetensors`, `split_files/vae/wan_2.1_vae.safetensors` plus needed configs/tokenizer; not CLIP-vision/I2V/14B files.
- Musubi precise format matrix and pre-cache/train examples: https://github.com/kohya-ss/musubi-tuner/blob/main/docs/wan.md
- ZeroScope card/API: https://huggingface.co/cerspense/zeroscope_v2_576w ; revision `6963642a64dbefa93663d1ecebb4ceda2d9ecb28`. Download only `text_encoder/`, `unet/`, `vae/`, scheduler/tokenizer/configs; exclude duplicate `zs2_576w/` weights.
- ModelScope card/API: https://huggingface.co/damo-vilab/text-to-video-ms-1.7b ; revision `8227dddca75a8561bf858d604cc5dae52b954d01`. Select FP16 safetensors only, not FP32 or duplicate bin files; licensing inconsistency is a blocker, not an MIT license.
- Archived trainer documents actual LoRA modes and ZeroScope support: https://github.com/ExponentialML/Text-To-Video-Finetuning . It states no further updates since Dec 2023; LoRA formats are not interchangeable with PEFT without conversion.
- LTX API/card: https://huggingface.co/Lightricks/LTX-Video ; revision `8984fa25007f376c1a299016d0957a37a2f797bb`. T2V capability also documented in Diffusers `LTXPipeline`; not recommending I2V as a substitute. Core download alone hides the large encoder.

**Remaining decisions/blockers:** choose acceptable download ceiling and whether NC licenses are acceptable for this portfolio; verify compact Wan T5 loader if selecting 9.83 GB; authorize selected exact files to E:; provision/pin isolated trainer/dependencies with E: venv/temp/cache; curate final approved footage and captions; benchmark preprocessing and one LoRA step; verify checkpoint reload and held-out results. No model download or training was performed.

**No model downloaded, inference executed, training run, or fine-tuned checkpoint exists.** Earlier img2img files are retained solely as superseded work, not an alternative solution. Do not use `infer.py` or `requirements.txt` for this task. Nothing outside `diffusion_work/` was edited; especially not `film_scene.py`.

## Historical initial proposal / verified limits (superseded by compact comparison)

Recommend **Wan2.1 T2V 1.3B** as the first practical small modern T2V + LoRA candidate, not as the smallest model ever published. Official model card explicitly licenses it Apache-2.0; upstream LICENSE.txt contains Apache 2.0. Its 1.3B name describes the denoiser, NOT the whole pipeline. Musubi Tuner explicitly supports Wan LoRA, Windows, cached text/latents, and memory-saving block swapping. This is a recommendation for a larger training machine, **not a promise it trains on this laptop**.

Compared candidate: CogVideoX-2B is also Apache-2.0 and supports LoRA, but larger denoiser; its model card reports 47 GB VRAM for its published batch-one LoRA recipe (not a universal lower bound). It does advertise offloaded inference starting at 4 GB, which is not evidence of 8 GB training. Wan has the stronger small-denoiser / active memory-saving training path here. Neither model guarantees exact spelling or uninterrupted engineering topology.

Hardware evidence: RTX 4060 Laptop, 8188 MiB, driver 617.42; CUDA PyTorch 2.9.1+cu130 works. Python 3.12.2. Physical RAM **16,328,011,776 bytes (~15.2 GiB)**; D: free **72,830,550,016 bytes (~67.8 GiB)** at inspection. diffusers, peft, av, decord missing; accelerate 1.12.0, transformers 4.57.6, safetensors .7.0, Pillow 10.3.0, imageio 2.37.2, datasets 2.18.0 installed. FFmpeg/ffprobe and accelerate command available. No Wan cache found. No applicable repository AGENTS.md found along ancestors or inside OneLine.

The Wan card's **8.19 GB inference** figure leaves essentially no margin on an 8 GB display-driving laptop. Full Diffusers pipeline FP32 files are **28,907,334,284 weight bytes (~28.91 GB / 26.92 GiB)**: text encoder 22,723,671,744; transformer 5,676,070,648; VAE 507,591,892, plus tokenizer/configs. On-load BF16 casting does NOT reduce download size. API revision: `0fad780a534b6463e45facd96134c9f345acfa5b`. Do not start this download without size approval. The large FP32 text encoder alone exceeds physical RAM; offload/loading may page heavily or fail. Quantized/precomputed-text inference is a separate unvalidated setup, not already solved.

Musubi's general recommendation is **24+ GB VRAM for video training, 64+ GB RAM** (32 GB + swap may work); not a measured minimum for this 1.3B recipe. Recommend a 24 GB GPU / 64 GB RAM machine with at least 100 GB free scratch as an initial training target. For conservative headroom use 48 GB VRAM. Benchmark a single train step before renting long runs. No 30-minute training promise.

## Actual footage, not yet a curated dataset

Ten root MP4s found, ranging 395,656–7,119,924 bytes; these are versions of one film, not ten independent training examples. `one_line_v9.mp4`: ffprobe verified **40.5 s, 1280x720, 24 fps, 972 frames**, 3,192,210 bytes. Existing `render3d/` frame sequences and Blender scene exist. Rights of incorporated assets, clip quality and which version is the target need user review. No captioned/held-out T2V dataset was established. Film worker is changing the target, so freeze and hash the final approved footage before extraction.

## Proposed LoRA experiment (plan, not an invented working trainer)

1. Select final approved reference; visually timestamp stage boundaries. Split into 2–5 s contiguous clips that stay within each stage; include transition clips separately. Normalize to chosen frame rate and frame count of form 4k+1; start with 17 frames / low spatial resolution for memory profiling, then test 49/81 frames. Do not speed up the whole 40.5 s film into one short training sample. Save extraction commands and source hashes under this directory.
2. Caption every clip with `darsh_one_line`, exact visible stage, motion, materials, camera, and temporal order. Identify microcontroller -> ESC power stage -> motor windings from README; confirm subsequent stages from actual final footage rather than hallucinating a caption. Hold out complete render variants/seeds/cameras, NOT overlapping neighboring frames of the same video. Generate new Blender variations only through the film worker/user, not edits here.
3. A one-film adapter is a **prompt-specific overfit/personalization experiment**, not evidence of generalization to new engineering videos. Train rank-8 transformer LoRA, frozen VAE/text encoder, cached latents/text, batch 1, BF16, gradient checkpointing; trial LR 1e-4 and checkpoint every 100 steps. These are starting hypotheses, not tuned results. Text/latent preprocessing must fit separately. Full weights/optimizer states are not required for frozen base layers, but activations remain expensive.
4. Use Musubi's documented Wan scripts only after pinning an exact audited commit and reviewing that commit's `docs/wan.md`, dataset schema, dependencies and CLI `--help`. Do not paste an unverified launch command. Keep bulk clone/venv/data/cache/logs/LoRAs under `E:/OneLine_diffusion/`; only small source/configs may stay here. Use a clean venv on the training host: current Musubi main declares newer diffusers/transformers than the host; reusing global packages is unsafe. Review `pip install --dry-run` first; no large torch replacement is authorized.
5. Run one preprocessing batch and one training step; record peak GPU+host RAM, wall time, loss, trainable count. Then a 10-step checkpoint smoke test, reload adapter and compare to base with identical held-out prompt/seed. Only after an actual adapter file and provenance exist call it fine-tuned. Budget longer runs from measured steps/sec; stop on OOM, nonfinite loss or corrupt topology.
6. Evaluate exact `Darsh` spelling (case sensitive), pen-lift/branch count and continuity, stage order, motor/PCB/wing correctness, motion/flicker and camera stability. A 5-second generator has no established ability to emit the whole 40.5-second continuous narrative; short-clip training cannot establish that. Stitching short generations is NOT one continuous generated take. Document observed limitations clearly.

Target prompt template: "A single uninterrupted cinematic engineering one-line animation. One continuous copper line traces microcontroller circuitry, develops into an ESC power stage, winds a motor, then proceeds through the remaining approved engineering stages in the reference order, and finally writes the exact readable name Darsh. No cuts, no disconnected strokes, smooth deliberate camera movement, precise engineering geometry." Replace the vague remaining-stage clause only after footage annotation; it is not a ready training caption. Generated airflow/CFD pictures are illustrative, not CFD solutions or verified physical measurements; motor wiring/PCB geometry need engineering validation. Exact spelling/geometry/order cannot be guaranteed by prompting or LoRA.

## Current T2V inference scaffold (CogVideoX-2B, E:)

`t2v_infer.py` now uses text-only **CogVideoXPipeline**, offline by default; `--dry-run` validates E: storage and arguments without importing the ML stack. It is **not executed model inference**. It accepts an existing E: local LoRA path; supplying no LoRA means pretrained-only inference. No image input exists. Suggested dependency review: diffusers, transformers, accelerate, peft, imageio-ffmpeg, sentencepiece, safetensors; resolve/pin a compatible environment before running. These requirements are not installed or tested here. `with_e_storage.py` should wrap dependency installation as well so pip temp files/cache are E:-local.

```powershell
python diffusion_work/t2v_infer.py --dry-run
# On approved/provisioned host, after dependency isolation and download authorization:
python diffusion_work/t2v_infer.py --allow-download --output base_test
# After actual training produces an adapter, use its local directory:
python diffusion_work/t2v_infer.py --lora E:/OneLine_diffusion/checkpoints/approved_adapter --output adapter_test
```

Original 28.91 GB download is rejected; see the compact comparison and blockers above. Larger RAM/training hardware or a proven low-memory recipe, isolated dependencies, approved footage/captions/rights, pinned trainer/config and an actual adapter reload remain necessary. None are bypassed by the retained, disabled img2img setup.

Sources:
- https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B-Diffusers (card + API file inventory)
- https://raw.githubusercontent.com/Wan-Video/Wan2.1/main/LICENSE.txt
- https://github.com/kohya-ss/musubi-tuner (Wan LoRA / hardware / Windows)
- https://github.com/kohya-ss/musubi-tuner/blob/main/docs/wan.md
- https://huggingface.co/THUDM/CogVideoX-2b (alternative card / license / memory)
