# CAD → text fallback (CPU only)

Implemented and tested on 2026-11-02. This is **not CAD-conditioned video**, a
geometric adapter, or a trained LoRA. No GPU, ML dependency, weight download,
renderer, inference-file change, film change, or harness change is involved.

## What works

`cad_prompt.py` uses Python's standard library to:

1. Verify exact size and SHA256 against the reviewed `assets.json` snapshot.
2. Extract conservative STEP syntax metadata, or STL triangle/vertex bounds.
3. Produce a deterministic engineering-subject text prompt and JSON provenance.
4. Optionally retrieve only allowlisted public GitHub CAD paths, at pinned
   40-character commits, using bounded HTTPS requests without credentials,
   proxies, cookies, redirects, subprocesses, or executing repository content.

The reviewed subject is manifest metadata, **not inferred from geometry**.
Arbitrary CAD labels and comments never enter the prompt. STEP entity counts
are not physical part counts. STEP control-point bounds are deliberately not
reported as physical bounds. STL has no unit definition. Neither parser proves
solid validity, manufacturing correctness, watertightness, or visual fidelity.
STL is supported by unit fixtures; no repository STL is approved in this small
manifest. STEP input has been exercised against real public native CAD.

All downloaded CAD and output reports must be on E:. The cache is
content-addressed, write-once, and rechecked if present. Existing reports are
never overwritten. A request error or hash mismatch stops processing; no fallback
to another commit, local copy, credential helper, or normalized bytes occurs.

## Commands

From this directory:

```powershell
python -B -m unittest -v test_cad_prompt.py

# Explicit network opt-in, approved reproducible snapshot:
python -B cad_prompt.py rotor_bell --fetch --output E:/OneLine_diffusion/cad_conditioning/reports/new_pinned.json

# Offline: exact approved bytes, e.g. already fetched content-addressed cache:
python -B cad_prompt.py rotor_bell --local E:/OneLine_diffusion/cad_conditioning/719dff49118d26f5586fb4922496c61a679d2648deba2238e8abecab3fee536b.cad --output E:/OneLine_diffusion/cad_conditioning/reports/new_offline.json

# Explicit opt-in live default HEAD, resolved once to a full commit:
python -B cad_prompt.py stator_housing --live-latest --output E:/OneLine_diffusion/cad_conditioning/reports/new_live_candidate.json
```

`--live-latest` is a discovery candidate, **not automatic asset approval**. It
does not edit `assets.json`, replace pinned bytes, or invoke inference. Its report
records the resolved commit, size, SHA256, and `approved_snapshot: false`.
Review a candidate and deliberately edit the source manifest to approve a new
snapshot. A completed live report is reproducible by its resolved commit/hash;
the act of selecting *latest* is time-dependent. Reports contain asset entries,
but the CLI intentionally does not auto-load them as trusted manifests.

## Actual source findings

- `D:/CodeProjects/drone-arm` origin: `https://github.com/iamdarshg/drone-arm.git`.
  Local HEAD `21378132d146a84984062535223d279153e284f5` returned HTTP 422 from
  the public commit API. Public default HEAD was
  `fc80ded19dd070b476866e84de6c872ee3480d89`; both selected native STEP paths
  returned HTTP 200 at that pinned raw URL and match `assets.json` exactly.
- Local motor STEP files have CRLF; GitHub/git blob files have LF. The local
  rotor is 203206 bytes versus the approved raw 198557 bytes. They compare
  equal after CRLF-to-LF conversion during investigation, but **the runtime
  does not normalize or accept this difference**. Use the verified cache for
  offline runs, not the checkout bytes.
- `D:/CodeProjects/drone-mech` origin:
  `https://github.com/iamdarshg/drone-mech.git`. Initial public API returned HTTP 404
  for both the commit and repository latest query. Could be private/unavailable;
  no attempt was made to obtain credentials. Local HEAD:
  `5246c90657071772e220b118967fa5f3e7c9ff7c`.
- Local tracked wing file
  `highspeed_edf/deliverables/phase15_geometry/step/lifting_wing_left_sector_with_duct_and_elevon_reliefs.step`
  is 713596 bytes, SHA256
  `b1fb7cd66f98e8b5e9c65ecb25c703993bb32218cf2ada2c3baa3d1559e7121b`;
  bytes match its local HEAD Git blob exactly. Subsequent public verification
  below supersedes the initial availability result; this exact wing asset is
  now approved in the public manifest.

### Public drone-mech recheck (2026-11-02)

Unauthenticated, credential-free requests to
`https://api.github.com/repos/iamdarshg/drone-mech` returned HTTP 200 with
`private: false`, `default_branch: main`. The latest commit API
`https://api.github.com/repos/iamdarshg/drone-mech/commits?per_page=1`
returned HTTP 200 and resolved commit
`81b1d20b0f45bd3c3c0118628c7bbb73a788c24e`.

Added **only** the verified `lifting_wing_left` Phase15 STEP asset:

- Public pinned URL:
  <https://raw.githubusercontent.com/iamdarshg/drone-mech/81b1d20b0f45bd3c3c0118628c7bbb73a788c24e/highspeed_edf/deliverables/phase15_geometry/step/lifting_wing_left_sector_with_duct_and_elevon_reliefs.step>
- Exact path:
  `highspeed_edf/deliverables/phase15_geometry/step/lifting_wing_left_sector_with_duct_and_elevon_reliefs.step`.
- Size: **713596 bytes**; SHA256:
  `b1fb7cd66f98e8b5e9c65ecb25c703993bb32218cf2ada2c3baa3d1559e7121b`.
- Metadata: 1 manifold-solid BREP entity, 51 advanced-face entities,
  millimetre unit hint; no geometric-validity guarantee.
- Exact raw bytes match the earlier locally investigated wing digest.
  No other Phase15 paths are claimed publicly verified by this recheck.

Pinned fetch, offline cache replay, and opt-in live latest all succeeded:

```powershell
python -B cad_prompt.py lifting_wing_left --fetch --output E:/OneLine_diffusion/cad_conditioning/reports/wing_public_pinned_20261102.json
python -B cad_prompt.py lifting_wing_left --local E:/OneLine_diffusion/cad_conditioning/b1fb7cd66f98e8b5e9c65ecb25c703993bb32218cf2ada2c3baa3d1559e7121b.cad --output E:/OneLine_diffusion/cad_conditioning/reports/wing_public_offline_20261102.json
python -B cad_prompt.py lifting_wing_left --live-latest --output E:/OneLine_diffusion/cad_conditioning/reports/wing_public_live_candidate_20261102.json
```

The live report resolved to the same commit but retains
`approved_snapshot: false`; it did not modify the pinned manifest. All CAD
bytes and reports are on E:. No visibility changes, tokens, full repository
downloads, model downloads, or GPU usage occurred. The expanded suite has
**10 passing CPU tests**, including manifest pin/allowlist validation.

## Tested evidence

- Initial 9 CPU unit tests passed: hash mismatch, repository/path/commit/size policy,
  prompt/provenance, label-injection exclusion, no implicit networking, ASCII
  and binary STL metadata, invalid data, endpoint/redirect policy, E: policy.
- Actual pinned fetch report:
  `E:/OneLine_diffusion/cad_conditioning/reports/rotor_bell_pinned_20261102.json`.
  Rotor: 1 manifold-solid BREP entity, 62 advanced-face entities,
  millimetre unit hint; geometry validity explicitly false.
- Actual live latest discovery report:
  `E:/OneLine_diffusion/cad_conditioning/reports/stator_live_candidate_20261102.json`.
  Stator: 1 manifold-solid BREP entity, 4 advanced-face entities,
  millimetre unit hint. It resolved to the same public commit, but remains an
  unapproved candidate. Both downloads total approximately 208 kB, stored on E:.
- Offline replay succeeded at
  `E:/OneLine_diffusion/cad_conditioning/reports/rotor_offline_20261102.json`.
  Attempting the CRLF checkout copy correctly exited 1 with a hash/size
  mismatch, before any report/cache write.

## Wan support and remaining blocker

Read-only inspection of `../wan_compact.py` shows:

- Lines 37–38: `Wan2.1-T2V-1.3B`, `pretrained_only=True`, `fine_tuned=False`.
- Lines 101–107: UMT5 tokenizes/encodes the supplied prompt as positive text
  conditioning; no CAD/mesh/image/depth reader is present.
- Lines 111–122: the T2V denoiser consumes text conditioning and a zero latent
  with sampled noise. There is no rendered geometry/control input or LoRA
  loading path. `../t2v_infer.py` simply dispatches to this implementation.

The real small supported path here is **text-only Wan2.1 T2V-1.3B**. The JSON
`prompt` can be explicitly passed to its existing `--prompt` interface by the
coordinating session once GPU scheduling permits. This prototype intentionally
does not launch it. The film's full narrative is not injected into this single-
subject diagnostic prompt; that is a separate editorial choice.

The user-preferred T2V fine-tune remains separate and unimplemented here.
A conventional T2V LoRA does not make STEP/STL readable or preserve geometry.
True visual conditioning needs a CAD-kernel import/tessellation and calibrated
render sequence, plus a *verified compatible* image/depth/control-conditioned
model/adapter and input wiring. That support is absent from the inspected
approved compact path, and extra model weights are not authorized. No renderer,
control condition generation, adapter training, or CAD-conditioned video is
claimed. **The delivered fallback is CAD-informed text and provenance only.**
