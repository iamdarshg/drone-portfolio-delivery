# Drone engineering delivery

Curated local demo and experimental diffusion source. This repository is **public** and can be cloned without authentication. The app runs locally; no hosted backend is provided. No credentials, model weights, caches, local test screenshots, or generated training datasets are bundled.

## Run the app

**[Download the local app ZIP](https://github.com/iamdarshg/drone-portfolio-delivery/raw/refs/heads/main/downloads/DroneEngineering-local-app.zip)** (590,806 bytes). This is the exact final upload package, SHA256 `a835a82034a8fe632ce55a72d7deb783cb8dd7106c691318195cb26e8851cc31`.

Extract the ZIP, then open a terminal inside its `DroneEngineering` folder. Nothing runs automatically. On Windows run `py -3 serve.py`; on Linux/macOS run `python3 serve.py` (Python 3.10+). Open the loopback URL printed by the server. Alternatively, manually launch the included `Start.cmd` (Windows), `Start.command` (macOS), or `bash Start.sh` (Linux). Review scripts before running them. Git is optional for viewing the app; install Git only if you want the clone helpers. No weights are included and no completed fine-tuned LoRA is claimed.

Public code URL for screenshot captions: **https://github.com/iamdarshg/drone-portfolio-delivery**. If the submission portal accepts only images/video, use that URL in the caption rather than attaching this ZIP to the portal.

Python 3.10+; no third-party Python packages are required for the local server.

```sh
git clone https://github.com/iamdarshg/drone-portfolio-delivery.git
cd drone-portfolio-delivery/app
python serve.py --help
python serve.py
```

Use the loopback URL printed by the server. The demo includes bundled engineering previews and can query GitHub for current source trees. Live GitHub requests depend on repository visibility, network access, and API rate limits; bundled data is a snapshot, not a promise of current remote state. The app's existing expiry configuration is preserved.

## Experimental diffusion work

`diffusion_work/` contains a pretrained Wan text-to-video pipeline, CPU training orchestration harness, and CAD-to-text prompt fallback. **No completed fine-tuned LoRA exists or is included.** CAD metadata becomes text; this is not geometric CAD-conditioned diffusion. Byte-identical replay is copying, not generation. The film is not represented as diffusion output.

### Diffusion model: what was built and what was demonstrated

The experimental loader targets the compact **Wan 2.1 T2V 1.3B** split-file bundle (about **9.83 GB** total): BF16 video denoiser, scaled-FP8 UMT5 text encoder, and Wan VAE. The implementation uses ComfyUI's pinned Wan text-encoder detection code because the scaled-FP8 encoder is not assumed to be a standard Diffusers checkpoint. The loader/import compatibility check is distinct from successful prompt encoding or video generation. The bundle is external and is not stored in this repository.

The T2V smoke run used pretrained weights only: text prompt plus random latent initialization, 320×192, 17 frames, 16 fps, 12 sampling steps. Its output was an abstract linework clip that did not reach the target engineering sequence and readable-name. It is a deferred feasibility experiment—not a showcase result, not an image-conditioned run, and not the OneLine Blender film. No fine-tuned adapter/checkpoint was produced. The LoRA harness and CAD-to-text prompt tools are research prototypes; they do not establish trained-model performance or geometric CAD conditioning.

To inspect the complete evidence, setup constraints, command references, current status, and proposed next experiments, see [`diffusion_work/README.md`](diffusion_work/README.md), [`diffusion_work/lora_harness/README.md`](diffusion_work/lora_harness/README.md), and [`diffusion_work/cad_conditioning/README.md`](diffusion_work/cad_conditioning/README.md). In particular, model downloads require a separately prepared Windows E: storage layout and roughly 9.83 GB of model files; do not start a download or GPU run just to browse this repository.

Start with the component READMEs. The inference setup expects a separately provisioned Windows E: bulk-storage directory, pinned ComfyUI checkout, external pretrained model downloads (approximately 9.83 GB), and suitable GPU resources. Those dependencies are deliberately not shipped. Do not run downloads or GPU jobs merely to view the app.

CPU-only checks from the repository root:

```sh
python -B -m unittest discover -s diffusion_work/lora_harness -v
python -B -m unittest discover -s diffusion_work/cad_conditioning -v
```

Harness training commands are experimental and gated; read its limitations before attempting training. Source-model and external CAD licenses remain the responsibility of their respective upstream projects; this delivery grants no new license to third-party content.

## Film status

The revised **v10s** full encode is pending verification and is not bundled yet. Superseded v10r is intentionally excluded. See `media/STATUS.json`. A later verified media commit may add v10s if below GitHub's 100 MiB per-file limit; large model weights will never be committed.

## Source scope

App source is a sanitized copy of the final local demo. Diffusion code and documentation are copied from the experimental work area; original source repositories were not modified. Machine-specific checkout paths were removed from this delivery. Bulk-storage E: defaults are intentionally retained as explicit runtime requirements. The repository includes no hosted backend or promise that external referenced repositories are public.
