"""Render and visually validate the Phase-12 STEP set into Phase-13 evidence.

Input is read-only under deliverables/phase12. PNGs and the visual note are
written only under deliverables/phase13/reports.
"""

from __future__ import annotations

import math
import logging
from pathlib import Path

import cadquery as cq
import numpy as np
import pyvista as pv


HERE = Path(__file__).resolve().parent
PHASE12 = HERE.parent / "phase12"
SCREEN_DIR = HERE / "reports" / "screenshots"
SCREEN_DIR.mkdir(parents=True, exist_ok=True)

WINDOW = (1500, 950)
logging.getLogger().setLevel(logging.ERROR)
COLORS = {
    "default": "#b8c4cf",
    "case": "#6f7f8b",
    "rotor": "#d88943",
    "stator": "#5ca982",
    "inlet": "#49a7bd",
    "body": "#d7d3c8",
    "battery": "#c75050",
    "board": "#386eb0",
    "clamp": "#df6b5f",
    "blank": "#df9d55",
    "hub": "#4f8fba",
    "plate": "#788692",
}


def mesh_solid(solid: cq.Shape, tolerance: float = 0.8) -> pv.PolyData | None:
    vertices, triangles = solid.tessellate(tolerance, 0.35)
    if not vertices or not triangles:
        return None
    points = np.asarray([[v.x, v.y, v.z] for v in vertices], dtype=float)
    tri = np.asarray(triangles, dtype=np.int64)
    faces = np.column_stack((np.full(len(tri), 3, dtype=np.int64), tri)).ravel()
    return pv.PolyData(points, faces)


def group_for_solid(solid: cq.Shape, context: str) -> str:
    b = solid.BoundingBox()
    spans = sorted((b.xlen, b.ylen, b.zlen))
    volume = solid.Volume()
    if "stock" in context:
        if b.xlen > 290 and b.ylen > 48 and b.zlen > 15:
            return "plate"
        if 24.5 <= b.xlen <= 25.5 and b.ylen > 48 and b.zlen > 15:
            return "clamp"
        if b.xlen > 100 and b.ylen > 80 and b.zlen > 4.5:
            return "plate"
        if b.zlen > 14.5 and b.xlen > 28 and b.xlen < 34 and b.ylen > 28:
            return "hub"
        return "blank"
    if min(spans) < 2.1 and max(spans) > 90:
        return "board"
    if 140 < b.zlen < 160 and 45 < b.xlen < 55 and 40 < b.ylen < 50:
        return "battery"
    if b.xlen > 82 and b.ylen > 82 and 90 < b.zlen < 125:
        return "case"
    if 11 < b.zlen < 18 and volume < 40000 and max(spans) < 55:
        return "rotor"
    if 5 < b.zlen < 11 and volume < 15000 and max(spans) < 55:
        return "stator"
    if volume < 25000 and b.zlen > 15 and b.xlen < 130 and b.ylen < 90:
        return "inlet"
    if b.xlen > 100 or b.zlen > 250:
        return "body"
    return "default"


def add_step_shape(plotter: pv.Plotter, step_path: Path, context: str,
                   opacity: float = 1.0, tolerance: float = 0.8) -> tuple[cq.Shape, int]:
    shape = cq.importers.importStep(str(step_path)).val()
    solids = shape.Solids()
    groups: dict[str, list[pv.PolyData]] = {}
    for solid in solids:
        mesh = mesh_solid(solid, tolerance)
        if mesh is None:
            continue
        groups.setdefault(group_for_solid(solid, context), []).append(mesh)
    for category, meshes in groups.items():
        combined = meshes[0] if len(meshes) == 1 else meshes[0].merge(meshes[1:], merge_points=False)
        category_opacity = opacity
        if category in ("body", "case", "plate", "clamp") and "stock" in context:
            category_opacity = 0.18 if category == "plate" else 0.25
        elif category == "case":
            category_opacity = min(opacity, 0.28)
        elif category == "body":
            category_opacity = min(opacity, 0.42)
        elif category == "battery":
            category_opacity = min(opacity, 0.62)
        plotter.add_mesh(combined, color=COLORS[category], opacity=category_opacity,
                         smooth_shading=False, show_edges=False, ambient=0.22,
                         diffuse=0.78, specular=0.12)
    return shape, len(solids)


def normalized(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n else v


def add_scale_bar(plotter: pv.Plotter, focal: tuple[float, float, float],
                  camera_position: tuple[float, float, float], view_up: tuple[float, float, float],
                  parallel_scale: float, length_mm: float = 50.0) -> None:
    focus = np.asarray(focal, dtype=float)
    pos = np.asarray(camera_position, dtype=float)
    up_hint = normalized(np.asarray(view_up, dtype=float))
    forward = normalized(focus - pos)
    right = normalized(np.cross(forward, up_hint))
    screen_up = normalized(np.cross(right, forward))
    aspect = WINDOW[0] / WINDOW[1]
    start = focus - right * (parallel_scale * aspect * 0.40) - screen_up * (parallel_scale * 0.78)
    end = start + right * length_mm
    line = pv.Line(start, end).tube(radius=max(0.4, parallel_scale / 300.0))
    plotter.add_mesh(line, color="#101820", line_width=4)
    label = end + screen_up * max(3.0, parallel_scale * 0.025)
    plotter.add_point_labels([label], [f"{length_mm:g} mm"], font_size=12,
                             text_color="#101820", shape=None, always_visible=True)


def render_view(step_path: Path, output: Path, title: str, context: str,
                camera_position: tuple[float, float, float], focal: tuple[float, float, float],
                view_up: tuple[float, float, float], parallel_scale: float,
                axis_note: str, opacity: float = 1.0, scale_mm: float = 50.0,
                tolerance: float = 0.8) -> dict:
    plotter = pv.Plotter(off_screen=True, window_size=WINDOW)
    plotter.set_background("#f3f6f8")
    shape, nsolids = add_step_shape(plotter, step_path, context, opacity, tolerance)
    if context == "inlet":
        radius = 30.0
        for module_start in (0.0, 150.0):
            slot_z = module_start - radius
            for side, color in ((1, "#c54b45"), (-1, "#336ea4")):
                pts = []
                for i in range(41):
                    a = (math.pi / 2.0) * i / 40.0
                    pts.append((side * radius * (1.0 - math.sin(a)), 0.0,
                                slot_z + radius * (1.0 - math.cos(a))))
                route = pv.Spline(np.asarray(pts), 100).tube(radius=0.75)
                plotter.add_mesh(route, color=color, opacity=1.0, smooth_shading=False)
                slot = pv.Line((side * radius, 0, slot_z - 60),
                               (side * radius, 0, slot_z + 60)).tube(radius=0.55)
                plotter.add_mesh(slot, color=color, opacity=1.0)
    plotter.camera_position = [camera_position, focal, view_up]
    plotter.camera.parallel_projection = True
    plotter.camera.parallel_scale = parallel_scale
    plotter.add_text(title, position="upper_left", font_size=16, color="#152330")
    plotter.add_text(axis_note, position="upper_right", font_size=11, color="#243746")
    add_scale_bar(plotter, focal, camera_position, view_up, parallel_scale, scale_mm)
    plotter.add_axes(line_width=2, labels_off=False, viewport=(0.82, 0.02, 0.98, 0.18))
    plotter.screenshot(str(output), return_img=False)
    plotter.close()
    b = shape.BoundingBox()
    return {"image": str(output.relative_to(HERE)), "sourceStep": str(step_path.relative_to(HERE.parent)),
            "validBrep": shape.isValid(), "solidCount": nsolids,
            "bboxMm": [round(v, 3) for v in (b.xmin, b.xmax, b.ymin, b.ymax, b.zmin, b.zmax)],
            "view": axis_note}


def main() -> None:
    stepdir = PHASE12 / "step"
    nestdir = PHASE12 / "stock_layouts"
    focus_z = -52.5  # visual centre of the full airframe envelope
    rendered = []

    full = stepdir / "phase12_full_assembly_R030.step"
    rendered.append(render_view(full, SCREEN_DIR / "01_full_assembly_isometric_R030.png",
        "Phase 12 full assembly — R30 packaging variant", "assembly",
        (900, -1200, 700), (0, 0, focus_z), (0, 1, 0), 520,
        "ISO view; X lateral, Y vertical, Z flight; 100 mm scale bar", opacity=0.9, scale_mm=100, tolerance=1.0))

    rendered.append(render_view(full, SCREEN_DIR / "02_front_projection_R030.png",
        "Front projection — two coincident 90 mm ducts", "assembly",
        (0, 0, 1200), (0, 0, 0), (0, 1, 0), 78,
        "View +Z; X lateral/Y vertical; CAD union 67.86 cm2; 50 mm scale bar",
        opacity=0.85, scale_mm=50, tolerance=0.6))

    inlet = stepdir / "phase12_interchangeable_inlet_split_R030.step"
    rendered.append(render_view(inlet, SCREEN_DIR / "03_inlet_routing_top_R030.png",
        "Split inlet routing — top view", "inlet",
        (0, 1000, 0), (0, 0, 45), (0, 0, 1), 150,
        "View +Y; X lateral/Z flight; centerline overlay; 50 mm scale bar", opacity=0.95,
        scale_mm=50, tolerance=0.5))

    rendered.append(render_view(inlet, SCREEN_DIR / "04_inlet_routing_side_R030.png",
        "Split inlet routing — side view", "inlet",
        (1000, 0, 0), (0, 0, 45), (0, 1, 0), 150,
        "View +X; Y vertical/Z flight; recovery unmeasured; 50 mm scale bar",
        opacity=0.95, scale_mm=50, tolerance=0.5))

    for module, zc in (("A", 55.0), ("B", 205.0)):
        module_step = stepdir / f"phase12_EDF_{module}_R030.step"
        rendered.append(render_view(module_step, SCREEN_DIR / f"0{5 + (module == 'B')}_EDF_{module}_rotor_stator_closeup_R030.png",
            f"EDF {module} — 3 rotor / 3 stator rows", "assembly",
            (230, -260, zc + 190), (0, 0, zc), (0, 0, 1), 145,
            "Isometric; 16 mm rotor / 8 mm stator chord; 30 mm scale bar", opacity=1.0,
            scale_mm=30, tolerance=0.35))

    module_a = stepdir / "phase12_EDF_A_R030.step"
    rendered.append(render_view(module_a, SCREEN_DIR / "07_rotor_R1_hub_blade_assembly_detail_R030.png",
        "EDF A rotor R1 — assembled blade/hub interface", "assembly",
        (190, -240, 130), (0, 0, 14), (0, 0, 1), 120,
        "Isometric close-up; nominal root engagement shown; 20 mm scale bar",
        opacity=1.0, scale_mm=20, tolerance=0.3))

    rotor_nest = nestdir / "phase12_channel01_R1_rotor_hub_300x50x16.step"
    rendered.append(render_view(rotor_nest, SCREEN_DIR / "08_rotor_billet_nest_channel01.png",
        "Channel 01 billet nest — full stock and clamp zones", "stock",
        (150, 25, 1000), (150, 25, 8), (0, 1, 0), 110,
        "Top +Z; 300x50 billet, CAM X25..275; 25 mm end margins; 50 mm scale bar",
        opacity=1.0, scale_mm=50, tolerance=0.65))

    stator_nest = nestdir / "phase12_EDF_A_stator_set_250x100x5.step"
    rendered.append(render_view(stator_nest, SCREEN_DIR / "09_stator_plate_nest_EDF_A.png",
        "EDF A stator vane set — plate nest", "stock",
        (125, 50, 900), (125, 50, 2.5), (0, 1, 0), 85,
        "Top +Z; 250x100x5 plate; 63 vanes; 50 mm scale bar",
        opacity=1.0, scale_mm=50, tolerance=0.45))

    receipt = {
        "renderer": "CadQuery STEP import + OpenCascade tessellation + PyVista/VTK offscreen raster",
        "windowPixels": list(WINDOW), "screenshots": rendered,
        "phase12Openfoam": "No iterations/recovery results; phase12 execution receipt is local-preflight-only-no-cloud-launch.",
        "frontAreaReferenceCm2": 67.85874663337762,
        "conservativePreflightAreaCm2": 73.61725123519331,
    }
    report = f"""# Phase-13 screenshot-based visual validation of Phase-12 CAD

## Render method

Rendered locally from the existing Phase-12 STEP B-reps using CadQuery/Open Cascade tessellation and PyVista/VTK offscreen rasterization at {WINDOW[0]}×{WINDOW[1]} pixels. The Phase-12 STEP and G-code sources were read-only. Screenshots include orientation notes and a physical scale bar; no solver, GCP, or CNC was used.

## Screens inspected

""" + "\n".join(f"- `{Path(item['image']).name}` — {item['view']}; {item['solidCount']} solids, STEP re-import valid={item['validBrep']}." for item in rendered) + """

## Visual findings and unresolved items

- Front view shows the two 90 mm duct rims coincident within one disk outline, with the side lips and board strips visible at the perimeter. Its detailed CAD area overlay is 67.86 cm2 against 75 cm2; the Phase-12 R30 conservative reserve screen is 73.62 cm2. Neither is a CFD result. The preflight's coarser R35 outboard/reserve bound exceeds 75 cm2, so R30 remains the provisional area-focused assembly.
- Top routing view overlays both R30 branch centerlines. No gross centerline crossover is visible; each pair reaches the outlet splitter region. The branch-to-half-annulus seam, sealing surface and minimum wall clearance are not shown as a validated interference fit and remain CAD checks.
- Side routing view shows the slot-mouth edges at each EDF axial station. The STEP includes thin transition shells, whose open-edge/lip closure is not obvious in the side projection; sealing flanges and practical clamp/seam details need completion.
- EDF A/B closeups show all three rotor/stator stations inside the transparent case. The rotor roots intentionally engage the hub in the assembly; the screenshots do not establish a fused root fillet, blade tip clearance under load, or rotor-to-stator clearance. A/B are visually identical geometry at different axial stations.
- The R1 detail view shows the 6061 rotor blades engaging the OD32 hub with the nominal 8mm bore proxy; root contact is an assembly overlap and needs a finalized fillet/retention detail.
- The billet nest shows 13 R1 blanks and a separate hub bore within the raw 300x50x16 billet; both X end-clamp reservations are visible, with cutting contained in X25..275. The stator plate view shows the 63-vane 7x9 nest within the 250x100 plate. These are stock-overlay STEP views, not machining simulations; NC tab removal and cutter engagement still need CAM verification.
- The full-assembly view includes batteries and edge-on ESC/flight-board/heatspreader envelopes. The board plate is visibly larger than its small support rails; fasteners, connector clearance, heat path and vibration mounting are unresolved. Six motor/gearbox solids are absent because no mounting/shaft drawing was supplied; only the 41 mm area-screen proxy and mass points are used. This is a packaging gap, not visually validated hardware.
- Visual images do not establish pressure recovery, structural laminate quality, rotor containment, thermal performance, sealing, fatigue, or dynamic clearance. Phase-12 CFD did not run and no recovery claim is made.

## Artifacts

Screenshots are under `reports/screenshots/`; the per-image render metadata is in `reports/phase13_visual_validation_manifest.json`.
"""
    (HERE / "reports" / "phase13_visual_validation.md").write_text(report, encoding="utf-8")
    (HERE / "reports" / "phase13_visual_validation_manifest.json").write_text(
        __import__("json").dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"rendered {len(rendered)} screenshots in {SCREEN_DIR}")


if __name__ == "__main__":
    main()
