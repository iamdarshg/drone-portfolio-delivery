# Drone engineering delivery

Curated local demo and experimental diffusion source. This repository is **public** and can be cloned without authentication. The app runs locally; no hosted backend is provided. No credentials, model weights, caches, local test screenshots, or generated training datasets are bundled.

## Run the app

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
