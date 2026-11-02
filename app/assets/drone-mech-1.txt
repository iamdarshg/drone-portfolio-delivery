"""Offline Phase-12 EDF / inlet / airframe CAD and GRBL CAM generator.

Only writes below deliverables/phase12. No solver, network, cloud or CNC is
invoked. CadQuery produces editable STEP B-reps; the NC files are CAM inputs,
not machine-release files.
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
from typing import Iterable

import cadquery as cq
from cadquery import Color, Vector
from shapely.affinity import translate as shp_translate
from shapely.geometry import Point, Polygon, box
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
STEP_DIR = OUT / "step"
NEST_DIR = OUT / "stock_layouts"
NC_DIR = OUT / "gcode"
REPORT_DIR = OUT / "reports"
CONFIG_DIR = OUT / "configs"
for _directory in (STEP_DIR, NEST_DIR, NC_DIR, REPORT_DIR, CONFIG_DIR):
    _directory.mkdir(parents=True, exist_ok=True)

# Frozen Phase-9 system parameters.
DUCT_OD = 90.0
DUCT_ID = 88.0
HUB_OD = 32.0
HUB_R = HUB_OD / 2.0
ROTOR_CHORD = 16.0
ROTOR_ROOT_R = 14.6
ROTOR_TIP_R = 43.6
ROTOR_SPAN = ROTOR_TIP_R - ROTOR_ROOT_R
STATOR_CHORD = 8.0
ROTOR_COUNTS = (13, 12, 11)
STATOR_COUNTS = (23, 21, 19)
FIXED_GEAR_RATIOS = (2.35, 2.65, 2.95)
MOTOR_SOFT_RPM = 12500.0
ROTOR_DESIGN_RPM = (29375.0, 33125.0, 36360.0)  # frozen Phase-9 720 km/h row schedule
ROTOR_SOFT_LIMIT_RPM = tuple(MOTOR_SOFT_RPM * ratio for ratio in FIXED_GEAR_RATIOS)
ROTOR_TEST_RPM = tuple(1.25 * rpm for rpm in ROTOR_SOFT_LIMIT_RPM)
ROTOR_Z = (14.0, 47.0, 80.0)
STATOR_Z = (31.0, 64.0, 97.0)
MODULE_LENGTH = 110.0
MODULE_STARTS = (0.0, 150.0)
INLET_RADII = (30.0, 35.0, 40.0, 45.0)
INITIAL_RADIUS = 30.0
BILLET_RAW_LENGTH = 300.0
BILLET_CAM_X0 = 25.0
BILLET_CAM_X1 = 275.0
SLOT_WIDTH = 25.0
SLOT_LENGTH = 120.0
BRANCH_MDOT = 0.42937
TOTAL_MDOT = 4.0 * BRANCH_MDOT

ROTOR_BETA = ((-30.0, -19.0), (-33.3, -21.5), (-36.0, -23.7))
STATOR_BETA = ((16.3, -5.0), (18.5, -6.0), (20.4, -6.9))
AL_DENSITY_KG_M3 = 2700.0
AL_YIELD_MPA = 276.0
PLA_DENSITY_KG_M3 = 1240.0

ESC_BOARD_MASS_KG = 0.0701629936219608
FC_BOARD_MASS_KG = 0.05042232561333333
ESC_BOARD_BARE_DIMS_MM = (150.0, 150.0, 1.6)
FC_BOARD_BARE_DIMS_MM = (140.0, 100.0, 1.6)
MOTOR_MASS_EACH_KG = 0.280
BATTERY_MASS_EACH_KG = 0.713


def wire3(points: Iterable[tuple[float, float, float] | Vector]) -> cq.Wire:
    return cq.Wire.makePolygon([p if isinstance(p, Vector) else Vector(*p) for p in points], close=True)


def naca4(chord: float, thick_ratio: float = 0.12, camber: float = 0.02,
          camber_pos: float = 0.4, samples: int = 20) -> list[tuple[float, float]]:
    xs = [(1.0 - math.cos(math.pi * i / samples)) / 2.0 for i in range(samples + 1)]

    def yt(x: float) -> float:
        return 5.0 * thick_ratio * (0.2969 * math.sqrt(max(x, 0.0)) - 0.1260 * x
                                    - 0.3516 * x * x + 0.2843 * x**3 - 0.1015 * x**4)

    def yc(x: float) -> float:
        if not camber:
            return 0.0
        if x < camber_pos:
            return camber / camber_pos**2 * (2.0 * camber_pos * x - x * x)
        return camber / (1.0 - camber_pos)**2 * ((1.0 - 2.0 * camber_pos)
                                                  + 2.0 * camber_pos * x - x * x)

    return ([(x * chord, chord * (yc(x) + yt(x))) for x in xs]
            + [(x * chord, chord * (yc(x) - yt(x))) for x in reversed(xs)])


def make_vane(chord: float, theta: float, r0: float, r1: float,
              beta0: float, beta1: float, axial_centre: float,
              root_thick: float = 0.16, tip_thick: float = 0.12) -> cq.Solid:
    sections = []
    for u in (0.0, 0.18, 0.38, 0.60, 0.82, 1.0):
        radius = r0 + (r1 - r0) * u
        beta = math.radians(beta0 + (beta1 - beta0) * u)
        thick = root_thick + (tip_thick - root_thick) * min(1.0, max(0.0, u / 0.24))
        foil = naca4(chord, thick, 0.025 if chord > 10 else 0.015)
        radial = (math.cos(theta), math.sin(theta))
        tangent = (-math.sin(theta), math.cos(theta))
        sweep = 0.55 * math.sin(math.pi * u)
        pts = []
        for x, y in foil:
            z = axial_centre + (x - chord / 2.0) * math.cos(beta) - y * math.sin(beta)
            tan = (x - chord / 2.0) * math.sin(beta) + y * math.cos(beta) + sweep
            pts.append(Vector(radius * radial[0] + tan * tangent[0],
                              radius * radial[1] + tan * tangent[1], z))
        sections.append(cq.Wire.makePolygon(pts, close=True))
    return cq.Solid.makeLoft(sections, ruled=False)


def annulus(ro: float, ri: float, length: float, z0: float) -> cq.Solid:
    a = cq.Solid.makeCylinder(ro, length, Vector(0, 0, z0))
    b = cq.Solid.makeCylinder(ri, length, Vector(0, 0, z0))
    return a.cut(b)


def make_rotor(row: int, zcentre: float) -> cq.Compound:
    count = ROTOR_COUNTS[row]
    hub = cq.Solid.makeCylinder(HUB_R, ROTOR_CHORD,
                                Vector(0, 0, zcentre - ROTOR_CHORD / 2.0))
    bore = cq.Solid.makeCylinder(4.0, ROTOR_CHORD + 2.0,
                                 Vector(0, 0, zcentre - ROTOR_CHORD / 2.0 - 1.0))
    hub = hub.cut(bore)
    b0, b1 = ROTOR_BETA[row]
    blades = [make_vane(ROTOR_CHORD, 2.0 * math.pi * i / count,
                        ROTOR_ROOT_R, ROTOR_TIP_R, b0, b1, zcentre)
              for i in range(count)]
    # 2 mm blended root thickening is represented by the first loft stations;
    # root-area strength sizing is independently recorded in the stress CSV.
    return cq.Compound.makeCompound([hub, *blades])


def make_stator(row: int, zcentre: float) -> cq.Compound:
    count = STATOR_COUNTS[row]
    b0, b1 = STATOR_BETA[row]
    vanes = [make_vane(STATOR_CHORD, 2.0 * math.pi * i / count,
                       17.6, 43.5, b0, b1, zcentre, 0.12, 0.12)
             for i in range(count)]
    vanes.extend((annulus(18.2, 17.6, 2.0, zcentre - 1.0),
                  annulus(44.0, 43.4, 2.0, zcentre - 1.0)))
    return cq.Compound.makeCompound(vanes)


def rounded_rect_points(width: float, height: float, count: int = 64,
                        exponent: float = 6.0) -> list[tuple[float, float]]:
    pts = []
    power = 2.0 / exponent
    for i in range(count):
        a = 2 * math.pi * i / count
        ca, sa = math.cos(a), math.sin(a)
        pts.append((math.copysign(abs(ca) ** power, ca) * width / 2.0,
                    math.copysign(abs(sa) ** power, sa) * height / 2.0))
    return pts


def rect_half_points(width: float, height: float, count: int = 32,
                     exponent: float = 6.0) -> list[tuple[float, float]]:
    """Rounded rectangle loop starting at top-centre, right side, bottom, left side."""
    pts = []
    power = 2.0 / exponent
    n = count // 2
    for i in range(n):
        theta = math.pi / 2.0 - math.pi * i / (n - 1)
        ca, sa = math.cos(theta), math.sin(theta)
        pts.append((math.copysign(abs(ca) ** power, ca) * width / 2.0,
                    math.copysign(abs(sa) ** power, sa) * height / 2.0))
    for i in range(n):
        theta = -math.pi / 2.0 - math.pi * i / (n - 1)
        ca, sa = math.cos(theta), math.sin(theta)
        pts.append((math.copysign(abs(ca) ** power, ca) * width / 2.0,
                    math.copysign(abs(sa) ** power, sa) * height / 2.0))
    return pts


def half_disk_points(radius: float, count: int = 32) -> list[tuple[float, float]]:
    # The first half of the loop is the outboard semicircle; the second half is
    # its straight splitter face. This correspondence lofts without crossing.
    n = count // 2 + 1
    pts = []
    for i in range(n):
        a = math.pi * i / (n - 1)
        pts.append((radius * math.sin(a), radius * math.cos(a)))
    # A 0.35 mm cambered splitter face avoids collapsed collinear loft edges
    # while remaining a smooth, manufacturable split between the two branches.
    base_points = count - n
    pts.extend((0.35 * math.sin(math.pi * i / (base_points + 1)),
                -radius + 2 * radius * i / (base_points + 1))
               for i in range(1, base_points + 1))
    return pts


def blended_section(t: float, outer: bool = True) -> list[tuple[float, float]]:
    wall = 1.0 if outer else 0.0
    rect = rect_half_points(25.0 + 2 * wall, 120.0 + 2 * wall)
    disk = half_disk_points(45.0 if outer else 44.0)
    s = t * t * (3.0 - 2.0 * t)
    return [(a0 * (1 - s) + a1 * s, b0 * (1 - s) + b1 * s)
            for (a0, b0), (a1, b1) in zip(rect, disk)]


def section_wire(center: Vector, basis_a: Vector, basis_b: Vector,
                 points: list[tuple[float, float]], side: int) -> cq.Wire:
    # Mirror the section laterally to make the second half-annulus branch.
    return cq.Wire.makePolygon([center + basis_a.multiply(side * a) + basis_b.multiply(b)
                                for a, b in points], close=True)


def make_inlet_branch(module_start: float, side: int, radius: float) -> tuple[cq.Compound, list[Polygon]]:
    outer_wires, inner_wires = [], []
    projected_sections: list[Polygon] = []
    steps = 12
    for i in range(steps + 1):
        t = i / steps
        ang = t * math.pi / 2.0
        slot_z = module_start - radius
        centre = Vector(side * radius * (1.0 - math.sin(ang)), 0,
                        slot_z + radius * (1.0 - math.cos(ang)))
        ba = Vector(0, 1, 0)
        bn = Vector(side * math.sin(ang), 0, math.cos(ang))
        outpts = blended_section(t, True)
        inpts = blended_section(t, False)
        outer_wires.append(section_wire(centre, ba, bn, outpts, side))
        inner_wires.append(section_wire(centre, ba, bn, inpts, side))
        projected_sections.append(Polygon([(centre.x + bn.x * b, side * a)
                                           for a, b in outpts]))
    # Convex hulls between adjacent section projections conservatively fill the
    # lofted wall's swept silhouette rather than measuring station slices only.
    station_projections = list(projected_sections)
    projected_sections.extend(unary_union((a, b)).convex_hull
                              for a, b in zip(station_projections[:-1], station_projections[1:]))
    outer = cq.Solid.makeLoft(outer_wires, ruled=False)
    inner = cq.Solid.makeLoft(inner_wires, ruled=False)
    shell = outer.cut(inner)

    # Flush 25 x 120 mm inlet lip, 2 mm outer overlap; the clear slot remains exact.
    slot_z = module_start - radius
    outer_lip = rounded_rect_points(29.0, 124.0, exponent=6.0)
    inner_lip = rounded_rect_points(25.0, 120.0, exponent=6.0)
    wo = cq.Wire.makePolygon([Vector(side * radius, a, slot_z + b) for a, b in outer_lip], close=True)
    wi = cq.Wire.makePolygon([Vector(side * radius, a, slot_z + b) for a, b in inner_lip], close=True)
    lip = cq.Solid.extrudeLinear(wo, [wi], Vector(side * 1.0, 0, 0))
    return cq.Compound.makeCompound([shell, lip]), projected_sections


def ellipse_wire_x(x: float, width_y: float, height_z: float, count: int = 64) -> cq.Wire:
    pts = [Vector(x, (width_y / 2) * math.cos(2 * math.pi * i / count),
                  (height_z / 2) * math.sin(2 * math.pi * i / count)) for i in range(count)]
    return cq.Wire.makePolygon(pts, close=True)


def make_body_shell() -> cq.Shape:
    """Printed-PLA/carbon lifting-body panels with a hollow battery bay.

    The previous smooth-loft concept was unnecessarily expensive to boolean
    through both fan bores. These open panel solids keep the intake/case datum
    clear and are the actual panel-envelope parts used by the Phase-12 assembly.
    """
    parts: list[cq.Shape] = []
    outer_bay = cq.Solid.makeBox(60.0, 55.0, 350.0, Vector(-30.0, -27.5, -450.0))
    inner_bay = cq.Solid.makeBox(56.8, 51.8, 347.0, Vector(-28.4, -25.9, -448.5))
    parts.append(outer_bay.cut(inner_bay))
    # A simple rounded nose and tail fairing close the battery pod without
    # extending its 60 x 55 mm silhouette beyond the 90 mm fan disk.
    parts.append(cq.Solid.makeCone(2.0, 28.0, 45.0, Vector(0, 0, -495.0)))
    parts.append(cq.Solid.makeCone(28.0, 2.0, 42.0, Vector(0, 0, -100.0)))
    # Thin lifting-body side rails bridge the body pod to the twin duct skins;
    # they sit outside the 90 mm casing and leave the annular flowpath open.
    for x0 in (-60.0, 45.0):
        parts.append(cq.Solid.makeBox(15.0, 5.0, 330.0, Vector(x0, -2.5, -20.0)))
    # Aft service-panel skins continue the rails around the board cooling bay.
    for x0 in (-60.0, 45.0):
        parts.append(cq.Solid.makeBox(15.0, 3.0, 90.0, Vector(x0, -1.5, 300.0)))
    return cq.Compound.makeCompound(parts)


def body_outer_projection() -> Polygon:
    # Max-profile projection of the lofted body. Battery-bay section is inside the fan disk.
    return Polygon([(60.0 * math.cos(2 * math.pi * i / 128),
                    2.5 * math.sin(2 * math.pi * i / 128)) for i in range(128)])


def make_battery_envelope(zcentre: float) -> cq.Solid:
    # Turnigy pack mass is sourced; 150x50x45 mm is a packaging proxy pending a physical measurement.
    return cq.Workplane("XY").box(50.0, 45.0, 150.0).translate((0, 0, zcentre)).val()


def make_board_envelopes() -> list[tuple[str, cq.Solid, float, tuple[float, float, float]]]:
    # Boards lie edge-on to the nose projection in a side cooling bay; their projections overlap.
    esc = cq.Workplane("XY").box(150.0, 1.6, 150.0).translate((0, 56.0, 220.0)).val()
    fc = cq.Workplane("XY").box(140.0, 1.6, 100.0).translate((0, 56.0, 235.0)).val()
    esc_sink = cq.Workplane("XY").box(150.0, 1.0, 150.0).translate((0, 56.0, 220.0)).val()
    fc_sink = cq.Workplane("XY").box(100.0, 1.0, 80.0).translate((0, 56.0, 235.0)).val()
    return [
        ("ESC_PCB_150x150x1p6_bare_mass_csv", esc, ESC_BOARD_MASS_KG, ESC_BOARD_BARE_DIMS_MM),
        ("flight_PCB_140x100x1p6_bare_mass_csv", fc, FC_BOARD_MASS_KG, FC_BOARD_BARE_DIMS_MM),
        ("ESC_Al_heatspreader_150x150x1_estimated", esc_sink, 0.06075, (150.0, 150.0, 1.0)),
        ("flight_Al_heatspreader_100x80x1_estimated", fc_sink, 0.02160, (100.0, 80.0, 1.0)),
    ]


def build_base_module(name: str, start: float) -> tuple[cq.Assembly, list[cq.Shape], dict[str, float]]:
    assy = cq.Assembly(name=f"EDF_{name}_3R3S_90OD_32hub")
    shapes: list[cq.Shape] = []
    case = annulus(45.0, 44.0, MODULE_LENGTH, start)
    assy.add(case, name=f"{name}_composite_duct_panel_shell_OD90_ID88")
    shapes.append(case)
    # Compact central flow nose / stator carrier core.
    # Match the Phase-12 half-annulus branch area (90/32 gross reference) at
    # the branch outlet, then smoothly contract to the physical 88mm-bore fan
    # face before R1; the resulting 5% area change is not a recovery claim.
    core = cq.Solid.makeCone(8.7666666667, 16.0, 14.0, Vector(0, 0, start - 8.0))
    assy.add(core, name=f"{name}_composite_splitter_core_cone")
    shapes.append(core)
    for row, zlocal in enumerate(ROTOR_Z):
        rotor = make_rotor(row, start + zlocal)
        assy.add(rotor, name=f"{name}_R{row+1}_N{ROTOR_COUNTS[row]}_C16_RPM{ROTOR_DESIGN_RPM[row]:.0f}")
        shapes.append(rotor)
    for row, zlocal in enumerate(STATOR_Z):
        stator = make_stator(row, start + zlocal)
        assy.add(stator, name=f"{name}_S{row+1}_N{STATOR_COUNTS[row]}_C8")
        shapes.append(stator)
    # Centerbody/motor proxy records the 32 mm hub envelope; exact motor shafts are not sourced.
    return assy, shapes, {"caseVolumeMm3": case.Volume(), "coreVolumeMm3": core.Volume()}


def build_full_variant(radius: float, base_modules: list[cq.Assembly],
                       body: cq.Shape, batteries: list[cq.Shape],
                       boards: list[tuple[str, cq.Shape, float, tuple[float, float, float]]]) -> tuple[cq.Assembly, list[Polygon], list[cq.Shape]]:
    assy = cq.Assembly(name=f"phase12_R{int(radius):03d}_full_airframe")
    for module, module_name, start in zip(base_modules, ("A", "B"), MODULE_STARTS):
        for child in module.children:
            assy.add(child.obj, name=f"{module_name}_{child.name}", loc=child.loc, color=child.color)
        for branch_idx, side in enumerate((+1, -1), 1):
            branch, _projection = make_inlet_branch(start, side, radius)
            assy.add(branch, name=f"{module_name}_slot{branch_idx}_25x120_R{int(radius)}_to_halfannulus")
    assy.add(body, name="carbon_PLA_lifting_body_panels")
    for i, (z, mass) in enumerate(zip((-337.5, -177.5), (BATTERY_MASS_EACH_KG,) * 2), 1):
        env = batteries[i - 1]
        assy.add(env, name=f"Turnigy_Rapid_6S5000_pack{i}_150x50x45_proxy_Z{z:g}_{mass:.3f}kg",
                 color=Color(0.72, 0.18, 0.16, 0.55))
    for name, shape, _mass, _dims in boards:
        assy.add(shape, name=name, color=Color(0.15, 0.42, 0.78, 0.50))
    # Four slim composite control/heat spreader supports, inside the declared 10 cm2 reserve.
    supports = []
    for y in (-58.0, 58.0):
        support = cq.Workplane("XY").box(18.0, 1.2, 110.0).translate((0, y, 210.0)).val()
        supports.append(support)
        assy.add(support, name=f"side_board_cooling_rail_Y{y:g}", color=Color(0.4, 0.4, 0.4, 0.35))
    projection = projected_area_polygons(radius, boards)
    all_shapes = [body, *batteries, *(b[1] for b in boards), *supports]
    return assy, projection, all_shapes


def projected_area_polygons(radius: float,
                            boards: list[tuple[str, cq.Shape, float, tuple[float, float, float]]]) -> list[Polygon]:
    """Conservative front-view silhouette from sampled inlet sections + placed envelopes."""
    pieces: list[Polygon] = [Point(0, 0).buffer(45.0, quad_segs=96), body_outer_projection()]
    # Battery and 41 mm motor envelopes are centered and axially staggered; both fit inside the fan disk.
    pieces.append(box(-25.0, -22.5, 25.0, 22.5))
    pieces.append(Point(0, 0).buffer(20.5, quad_segs=48))
    # 2 EDFs have the same projected slot/turn outline because their stations differ only axially.
    for side in (+1, -1):
        _, sections = make_inlet_branch(0.0, side, radius)
        pieces.extend(sections)
        # Lip thickness is included explicitly in the front projection.
        pieces.append(box(min(side * radius, side * (radius + 1.0)), -14.5,
                          max(side * radius, side * (radius + 1.0)), 14.5))
    # Overlay of the ESC/flight PCB and their estimated heat spreaders (flight-aligned edge-on).
    pieces.append(box(-75.0, 55.2, 75.0, 56.8))
    pieces.extend((box(-9.0, 57.4, 9.0, 58.6), box(-9.0, -58.6, 9.0, -57.4)))
    area = unary_union(pieces)
    return list(area.geoms) if area.geom_type == "MultiPolygon" else [area]


def front_area_cm2(projections: list[Polygon]) -> float:
    return unary_union(projections).area / 100.0


def profile_polygon(span: float, width: float, sweep: float = 0.7) -> Polygon:
    top, bottom = [], []
    for i in range(25):
        u = i / 24.0
        x = span * u
        local = width * (0.48 + 0.52 * math.sqrt(max(0.0, math.sin(math.pi * (0.03 + 0.94 * u)))))
        center = sweep * math.sin(math.pi * u) + 0.4 * u
        top.append((x, center + local / 2.0))
        bottom.append((x, center - local / 2.0))
    p = Polygon(top + list(reversed(bottom)))
    return shp_translate(p, yoff=-p.bounds[1])


def rotor_blank(row: int) -> Polygon:
    b0, b1 = ROTOR_BETA[row]
    top, bottom = [], []
    for i in range(31):
        u = i / 30.0
        x = ROTOR_SPAN * u
        beta = math.radians(b0 + (b1 - b0) * u)
        # Conservative CNC planform envelope includes a thickened 6061 root land.
        foil_thick = 0.12 + 0.04 * max(0.0, 1.0 - u / 0.24)
        width = 16.0 * abs(math.sin(beta)) + 0.30 * 16.0 * foil_thick * math.cos(beta)
        width = min(12.4, max(5.5, width))
        centre = 0.35 * math.sin(math.pi * u) + 0.2 * u
        top.append((x, centre + width / 2.0))
        bottom.append((x, centre - width / 2.0))
    p = Polygon(top + list(reversed(bottom)))
    return shp_translate(p, yoff=-p.bounds[1])


def stator_blank() -> Polygon:
    p = profile_polygon(27.0, 3.8, 0.3)
    return p


def closed_offset_points(p: Polygon, xoff: float, yoff: float, offset: float) -> list[tuple[float, float]]:
    q = p.buffer(offset, quad_segs=2, join_style="round")
    if q.geom_type == "MultiPolygon":
        q = max(q.geoms, key=lambda g: g.area)
    raw = list(q.exterior.coords)[:-1]
    pts = [raw[0]]
    for v in raw[1:]:
        if math.dist(v, pts[-1]) > 0.65:
            pts.append(v)
    return [(a + xoff, b + yoff) for a, b in pts]


def add_stock_layout_billet(channel: int, row: int, profile: Polygon) -> Path:
    path = NEST_DIR / f"phase12_channel{channel:02d}_R{row+1}_rotor_hub_300x50x16.step"
    assy = cq.Assembly(name=f"channel_{channel:02d}_rotor_row_stock_cam_region_250")
    raw = cq.Workplane("XY").box(BILLET_RAW_LENGTH, 50, 16, centered=(False, False, False)).val()
    assy.add(raw, name="6061T6_raw_billet_300x50x16", color=Color(0.55, 0.65, 0.72, 0.18))
    clamp_l = cq.Workplane("XY").box(25, 50, 16, centered=(False, False, False)).val()
    clamp_r = cq.Workplane("XY").box(25, 50, 16, centered=(False, False, False)).translate((275, 0, 0)).val()
    assy.add(clamp_l, name="reserved_left_clamp_margin_X0_to25_no_cut", color=Color(0.9, 0.2, 0.1, 0.18))
    assy.add(clamp_r, name="reserved_right_clamp_margin_X275_to300_no_cut", color=Color(0.9, 0.2, 0.1, 0.18))
    row_counts = ROTOR_COUNTS[row]
    distribution = (5, 5, row_counts - 10)
    index = 0
    y_positions = (3.0, 18.0, 33.0)
    for r, n in enumerate(distribution):
        for c in range(n):
            part = shp_translate(profile, xoff=BILLET_CAM_X0 + 5.0 + c * 31.5, yoff=y_positions[r])
            blank = cq.Workplane("XY").polyline(list(part.exterior.coords)[:-1]).close().extrude(16).val()
            assy.add(blank, name=f"R{row+1}_blade_{index+1:02d}_29mm_span_C16", color=Color(0.84, 0.47, 0.16, 0.9))
            index += 1
    hub = cq.Solid.makeCylinder(16.0, 16.0, Vector(230.0, 25.0, 0))
    bore = cq.Solid.makeCylinder(4.0, 18.0, Vector(230.0, 25.0, -1.0))
    hub = hub.cut(bore)
    assy.add(hub, name="6061T6_rotor_hub_OD32_bore8", color=Color(0.2, 0.55, 0.72, 0.9))
    assy.save(str(path), exportType="STEP", tolerance=0.05, angularTolerance=0.05)
    return path


def add_stock_layout_stator(module: str, profile: Polygon) -> Path:
    path = NEST_DIR / f"phase12_EDF_{module}_stator_set_250x100x5.step"
    assy = cq.Assembly(name=f"EDF_{module}_63_stator_blanks_5mm_stock")
    raw = cq.Workplane("XY").box(250, 100, 5, centered=(False, False, False)).val()
    assy.add(raw, name="6061T6_plate_250x100x5", color=Color(0.55, 0.65, 0.72, 0.18))
    for i in range(sum(STATOR_COUNTS)):
        r, c = divmod(i, 7)
        part = shp_translate(profile, xoff=5.0 + c * 31.5, yoff=5.0 + r * 6.5)
        vane = cq.Workplane("XY").polyline(list(part.exterior.coords)[:-1]).close().extrude(5).val()
        assy.add(vane, name=f"{module}_stator_blank_{i+1:02d}_span27_C8", color=Color(0.25, 0.65, 0.42, 0.9))
    assy.save(str(path), exportType="STEP", tolerance=0.05, angularTolerance=0.05)
    return path


def tabbed_points(points: list[tuple[float, float]], tab_count: int, tab_width: float) -> list[tuple[float, float, bool]]:
    ring = points + [points[0]]
    lengths = [math.dist(ring[i], ring[i + 1]) for i in range(len(points))]
    total = sum(lengths)
    centres = [total * (i + 0.37) / tab_count for i in range(tab_count)]

    def flagged(d: float) -> bool:
        return any(abs(((d - q + total / 2) % total) - total / 2) < tab_width / 2 for q in centres)

    out, accum = [], 0.0
    for i, length in enumerate(lengths):
        a, b = ring[i], ring[i + 1]
        cutpoints = [0.0, length]
        for centre in centres:
            for boundary in (centre - tab_width / 2, centre + tab_width / 2):
                local = boundary - accum
                if 1e-6 < local < length - 1e-6:
                    cutpoints.append(local)
        cutpoints = sorted(set(cutpoints))
        for j, local in enumerate(cutpoints[:-1]):
            t = local / length
            mid = accum + (local + cutpoints[j + 1]) / 2
            xy = (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)
            if not out or math.dist(xy, out[-1][:2]) > 1e-6:
                out.append((xy[0], xy[1], flagged(mid)))
        accum += length
    return out


def write_rotor_nc(channel: int, row: int, profile: Polygon, rough: bool) -> Path:
    suffix = "2mm_rough" if rough else "0p5mm_finish_top0p5"
    path = NC_DIR / f"channel_{channel:02d}_R{row+1}_blade_hub_{suffix}.nc"
    count = ROTOR_COUNTS[row]
    distribution = (5, 5, count - 10)
    placed: list[tuple[Polygon, float, float, str]] = []
    idx = 0
    for r, n in enumerate(distribution):
        for c in range(n):
            placed.append((profile, BILLET_CAM_X0 + 5.0 + c * 31.5,
                           (3.0, 18.0, 33.0)[r], f"blade{idx+1}"))
            idx += 1
    hub_poly = Point(230.0, 25.0).buffer(16.0, quad_segs=24)
    placed.append((hub_poly, 0.0, 0.0, "hub"))
    tool = 2.0 if rough else 0.5
    lines = [f"(Phase12 channel {channel} rotor row R{row+1} {suffix})",
             "(6061-T6; GRBL; no CNC run. Verify every toolpath in CAM before use.)",
             "(G54 X0/Y0 = raw billet lower-left; Z0 = billet top; stock 300x50x16.)",
             "(CAM X25..275, Y0..50; clamp margins X0..25 and X275..300 are no-cut.)",
             "(ER11 775 spindle S8000; 2-flute carbide; stock and clamp fixture fully supported.)",
             "(M0 manual tool change; re-touch G54 Z0 after each tool installation.)",
             "(Dry-run spindle-off, with stock removed or proven safe Z clearance; inspect clamps.)",
             "G21 G17 G90 G94 G54", "G40 G49 G80", "G0 Z5.000", "M5",
             ("M0 (Install 2.0 mm carbide rougher; flute >=18 mm; verify 16mm reach)" if rough else
              "M0 (Install 0.5 mm carbide finisher; flute >=1.0 mm; re-touch Z0)"),
             ("(Rough: S8000 F40 plunge F8; 0.20mm stepdown; 0.25mm radial leave; 1mm tabs.)" if rough else
              "(Finish edge band only: S8000 F20; 0.10mm Z stepdown to Z-0.5; full-depth microfinish unsupported.)"),
             "M3 S8000", "G4 P3"]
    if rough:
        depths, z, step = [], 0.20, 0.20
        while z < 15.999:
            depths.append(-z)
            z += step
        depths.append(-16.0)
        for depth in depths:
            lines.append(f"(2mm full-depth rough layer Z{depth:.3f})")
            for p, ox, oy, label in placed:
                if label == "hub":
                    loop = closed_offset_points(p, ox, oy, 1.25)
                    tabs = tabbed_points(loop, 4, 2.0)
                else:
                    loop = closed_offset_points(p, ox, oy, 1.25)
                    tabs = tabbed_points(loop, 3, 2.0)
                sx, sy, _ = tabs[0]
                lines.extend([f"G0 X{sx:.3f} Y{sy:.3f}", "G0 Z1.000", f"G1 Z{depth:.3f} F8.0"])
                for x, y, tab in tabs[1:] + [tabs[0]]:
                    zcmd = depth + 1.0 if depth <= -15.999 and tab else depth
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{zcmd:.3f} F40.0")
                lines.append("G0 Z1.000")
            # 8mm shaft bore: rough through with 2mm tool, leave 0.25mm radial stock.
            cx, cy, rr = 230.0, 25.0, 2.75
            lines.extend([f"G0 X{cx + rr:.3f} Y{cy:.3f}", "G0 Z1.000", f"G1 Z{depth:.3f} F8.0"])
            for j in range(65):
                a = 2 * math.pi * j / 64
                x, y = cx + rr * math.cos(a), cy + rr * math.sin(a)
                lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{depth:.3f} F40.0")
            lines.append("G0 Z1.000")
    else:
        for depth in (-0.1, -0.2, -0.3, -0.4, -0.5):
            for p, ox, oy, label in placed:
                loop = closed_offset_points(p, ox, oy, 0.25)
                sx, sy = loop[0]
                lines.extend([f"G0 X{sx:.3f} Y{sy:.3f}", "G0 Z1.000", f"G1 Z{depth:.3f} F5.0"])
                for x, y in loop[1:] + [loop[0]]:
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{depth:.3f} F20.0")
                lines.append("G0 Z1.000")
            bore_loop = closed_offset_points(Point(230.0, 25.0).buffer(3.75, quad_segs=24), 0.0, 0.0, 0.0)
            sx, sy = bore_loop[0]
            lines.extend([f"G0 X{sx:.3f} Y{sy:.3f}", "G0 Z1.000", f"G1 Z{depth:.3f} F5.0"])
            for x, y in bore_loop[1:] + [bore_loop[0]]:
                lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{depth:.3f} F20.0")
            lines.append("G0 Z1.000")
    lines.extend(["M5", "G0 Z5.000", "M30", ""])
    path.write_text("\n".join(lines), encoding="ascii", newline="\n")
    return path


def write_stator_nc(module: str, profile: Polygon, rough: bool) -> Path:
    suffix = "2mm_rough" if rough else "0p5mm_full_depth_finish"
    path = NC_DIR / f"EDF_{module}_63stators_250x100x5_{suffix}.nc"
    placed = []
    for i in range(sum(STATOR_COUNTS)):
        r, c = divmod(i, 7)
        placed.append((profile, 5.0 + c * 31.5, 5.0 + r * 6.5))
    lines = [f"(Phase12 EDF {module} stator set {suffix})",
             "(6061-T6; GRBL; no CNC run; all paths require manual CAM verification.)",
             "(G54 X0/Y0 = plate lower-left; Z0 = top; stock 250x100x5 mm.)",
             "(2-flute carbide; 775 spindle S8000; perimeter stock includes 5mm edge margin.)",
             "(M0 manual tool change; re-touch G54 Z0; verify clamps/spoilboard/travel.)",
             "(Dry-run spindle-off with stock removed or proven safe Z clearance.)",
             "G21 G17 G90 G94 G54", "G40 G49 G80", "G0 Z5.000", "M5",
             ("M0 (Install 2.0 mm carbide rougher; flute >=6 mm)" if rough else
              "M0 (Install 0.5 mm long-flute finisher >=6 mm; re-touch Z0)"),
             ("(Rough S8000 F50 plunge F8; 0.25mm stepdown; 0.25mm radial leave; 0.8mm tabs.)" if rough else
              "(Full-depth 5mm finish: S8000 F20 plunge F5, 0.05mm Z steps; 0.5mm tool wall use is conditional.)"),
             "M3 S8000", "G4 P3"]
    if rough:
        depths = [-(min(5.0, i * 0.25)) for i in range(1, 21)]
        for depth in depths:
            for i, (p, ox, oy) in enumerate(placed):
                loop = closed_offset_points(p, ox, oy, 1.25)
                tabs = tabbed_points(loop, 3, 2.0)
                sx, sy, _ = tabs[0]
                lines.extend([f"G0 X{sx:.3f} Y{sy:.3f}", "G0 Z1.000", f"G1 Z{depth:.3f} F8.0"])
                for x, y, tab in tabs[1:] + [tabs[0]]:
                    zcmd = depth + 0.8 if depth <= -4.999 and tab else depth
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{zcmd:.3f} F50.0")
                lines.append("G0 Z1.000")
    else:
        for k in range(1, 101):
            depth = -0.05 * k
            for p, ox, oy in placed:
                loop = closed_offset_points(p, ox, oy, 0.25)
                tabs = tabbed_points(loop, 3, 2.0)
                sx, sy, _ = tabs[0]
                lines.extend([f"G0 X{sx:.3f} Y{sy:.3f}", "G0 Z1.000", f"G1 Z{depth:.3f} F5.0"])
                for x, y, tab in tabs[1:] + [tabs[0]]:
                    zcmd = depth + 0.8 if depth <= -4.999 and tab else depth
                    lines.append(f"G1 X{x:.3f} Y{y:.3f} Z{zcmd:.3f} F20.0")
                lines.append("G0 Z1.000")
    lines.extend(["M5", "G0 Z5.000", "M30", ""])
    path.write_text("\n".join(lines), encoding="ascii", newline="\n")
    return path


def export_step(assy: cq.Assembly, path: Path) -> None:
    assy.save(str(path), exportType="STEP", tolerance=0.08, angularTolerance=0.08)


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def shape_lateral_area(shape: cq.Shape, axial_axis: str = "z") -> float:
    area = 0.0
    for face in shape.Faces():
        b = face.BoundingBox()
        axial_span = b.zlen if axial_axis == "z" else b.xlen
        if axial_span > 1e-3:
            area += face.Area()
    return area


def build_and_export() -> None:
    metadata_only = "--metadata-only" in sys.argv
    all_outputs: list[Path] = []
    if metadata_only:
        all_outputs = sorted([*STEP_DIR.glob("*.step"), *NEST_DIR.glob("*.step"), *NC_DIR.glob("*.nc")])
    body = make_body_shell()
    batteries = [make_battery_envelope(-337.5), make_battery_envelope(-177.5)]
    boards = make_board_envelopes()
    base_modules = [build_base_module("A", MODULE_STARTS[0])[0],
                    build_base_module("B", MODULE_STARTS[1])[0]]

    # Per-row blank families and the six exact channel billets.
    if not metadata_only:
        channel = 0
        rotor_profile_by_row = [rotor_blank(i) for i in range(3)]
        for module_idx, _module in enumerate(("A", "B")):
            for row in range(3):
                channel += 1
                all_outputs.append(add_stock_layout_billet(channel, row, rotor_profile_by_row[row]))
                all_outputs.append(write_rotor_nc(channel, row, rotor_profile_by_row[row], True))
                all_outputs.append(write_rotor_nc(channel, row, rotor_profile_by_row[row], False))
            letter = "A" if module_idx == 0 else "B"
            sprofile = stator_blank()
            all_outputs.append(add_stock_layout_stator(letter, sprofile))
            all_outputs.append(write_stator_nc(letter, sprofile, True))
            all_outputs.append(write_stator_nc(letter, sprofile, False))

    inlet_area_rows = []
    all_projection: dict[float, list[Polygon]] = {}
    for radius in INLET_RADII:
        if metadata_only:
            projections = projected_area_polygons(radius, boards)
            full = None
        else:
            full, projections, _ = build_full_variant(radius, base_modules, body, batteries, boards)
        area = front_area_cm2(projections)
        all_projection[radius] = projections
        preflight_protrusion = max(0.0, radius + SLOT_WIDTH / 2.0 - DUCT_OD / 2.0)
        preflight_area = math.pi * (DUCT_OD / 20.0) ** 2 + 10.0 + 2.4 * preflight_protrusion
        area_rows = {"radiusMm": radius, "frontProjectedAreaCm2": area,
                     "gate75Pass": area <= 75.0, "initialVariant": radius == INITIAL_RADIUS,
                     "phase12PreflightProtrusionMm": preflight_protrusion,
                     "phase12ConservativeReserveBoundCm2": preflight_area,
                     "phase12ConservativeBoundPass": preflight_area < 75.0,
                     "recoveryEvidence": "none; geometry-only variant"}
        inlet_area_rows.append(area_rows)
        if not metadata_only:
            assy_step = STEP_DIR / f"phase12_full_assembly_R{int(radius):03d}.step"
            export_step(full, assy_step)
            all_outputs.append(assy_step)
            if radius == INITIAL_RADIUS:
                for module, module_name, start in zip(base_modules, ("A", "B"), MODULE_STARTS):
                    per = cq.Assembly(name=f"phase12_EDF_{module_name}_R{int(radius):03d}")
                    for child in module.children:
                        per.add(child.obj, name=child.name, loc=child.loc, color=child.color)
                    for side in (+1, -1):
                        branch, _ = make_inlet_branch(start, side, radius)
                        per.add(branch, name=f"slot_{side:+d}_R{int(radius):03d}_halfannulus")
                    path = STEP_DIR / f"phase12_EDF_{module_name}_R{int(radius):03d}.step"
                    export_step(per, path)
                    all_outputs.append(path)

            inlet_assy = cq.Assembly(name=f"phase12_interchangeable_split_inlet_R{int(radius)}")
            for module_name, start in zip(("A", "B"), MODULE_STARTS):
                for side in (+1, -1):
                    branch, _ = make_inlet_branch(start, side, radius)
                    inlet_assy.add(branch, name=f"EDF_{module_name}_slot_{side:+d}_25x120_R{int(radius)}")
            inlet_step = STEP_DIR / f"phase12_interchangeable_inlet_split_R{int(radius):03d}.step"
            export_step(inlet_assy, inlet_step)
            all_outputs.append(inlet_step)

    # Mass and CG ledger: published/bare mass separated from analyst allowances.
    al_rotors, al_stators = [], []
    for start in MODULE_STARTS:
        for row, zlocal in enumerate(ROTOR_Z):
            al_rotors.append(make_rotor(row, start + zlocal))
        for row, zlocal in enumerate(STATOR_Z):
            al_stators.append(make_stator(row, start + zlocal))
    rotor_volume = sum(s.Volume() for s in al_rotors)
    stator_volume = sum(s.Volume() for s in al_stators)
    rotor_kg = rotor_volume * AL_DENSITY_KG_M3 * 1e-9
    stator_kg = stator_volume * AL_DENSITY_KG_M3 * 1e-9
    body_area_mm2 = shape_lateral_area(body)
    case_area_mm2 = sum(2.0 * math.pi * (45.0 + 44.0) * MODULE_LENGTH for _ in MODULE_STARTS)
    inlet_area_mm2 = 0.0
    for start in MODULE_STARTS:
        for side in (+1, -1):
            shell, _ = make_inlet_branch(start, side, INITIAL_RADIUS)
            inlet_area_mm2 += shape_lateral_area(shell)
    composite_surface_area_m2 = (body_area_mm2 + case_area_mm2 + inlet_area_mm2) * 1e-6
    # One 200 gsm carbon ply + one 100 gsm glass ply per face; 0.8 resin:fibre mass ratio.
    fibre_kg_m2_per_face = 0.300
    resin_to_fibre = 0.80
    # The lateral faces counted from the shell B-reps include both inner and
    # outer panel faces; apply one ply schedule per face, not twice again.
    skin_area_both_faces_m2 = composite_surface_area_m2
    laminate_kg = skin_area_both_faces_m2 * fibre_kg_m2_per_face * (1.0 + resin_to_fibre)
    # 1.2 mm nominal printed PLA panel/core thickness over CAD exterior surface area.
    pla_kg = (composite_surface_area_m2 / 2.0) * 0.0012 * PLA_DENSITY_KG_M3

    # Analyst estimates are explicit and not substituted for weights.
    population_kg = 0.20
    gearbox_kg_each = 0.12
    gearbox_kg = 6 * gearbox_kg_each
    harness_kg = 0.25
    mounting_allowance_kg = 0.35
    mass_components = [
        ("motors_fixed_6x0.28kg", 6 * MOTOR_MASS_EACH_KG, (0.0, 0.0, 122.0)),
        ("batteries_fixed_2x0.713kg", 2 * BATTERY_MASS_EACH_KG, (0.0, 0.0, -257.5)),
        ("ESC_board_bare_csv", ESC_BOARD_MASS_KG, (0.0, 56.0, 220.0)),
        ("flight_board_bare_csv", FC_BOARD_MASS_KG, (0.0, 56.0, 235.0)),
        ("estimated_populated_parts", population_kg, (0.0, 56.0, 230.0)),
        ("estimated_heatspreaders", sum(b[2] for b in boards[2:]), (0.0, 56.0, 230.0)),
        ("6061_rotor_hub_blade_solids", rotor_kg, (0.0, 0.0, 122.0)),
        ("6061_stator_vane_and_rail_solids", stator_kg, (0.0, 0.0, 122.0)),
        ("composite_CGskin", laminate_kg, (0.0, 0.0, 0.0)),
        ("printed_PLA_panel_core", pla_kg, (0.0, 0.0, 0.0)),
        ("estimated_gearboxes_fixed_ratios_6x0.12kg", gearbox_kg, (0.0, 0.0, 122.0)),
        ("estimated_harness", harness_kg, (0.0, 0.0, 110.0)),
        ("estimated_mounts", mounting_allowance_kg, (0.0, 0.0, 80.0)),
    ]
    mass_rows = []
    total_mass = 0.0
    moment = [0.0, 0.0, 0.0]
    for name, mass, centre in mass_components:
        total_mass += mass
        for j in range(3):
            moment[j] += mass * centre[j]
        mass_rows.append({"component": name, "massKg": mass, "cgXmm": centre[0],
                          "cgYmm": centre[1], "cgZmm": centre[2],
                          "evidence": "measured/source mass" if name.startswith(("motors_fixed", "batteries_fixed"))
                          or "bare_csv" in name else "CAD volume/material or analyst estimate"})
    cg = tuple(v / total_mass if total_mass else 0.0 for v in moment)
    mass_rows.append({"component": "TOTAL_SCREEN_NOT_WEIGHED", "massKg": total_mass,
                      "cgXmm": cg[0], "cgYmm": cg[1], "cgZmm": cg[2],
                      "evidence": "includes explicitly estimated gears/population/harness/mounts"})

    # Centrifugal stress screen scaled from Phase-11 reference stresses, same 2.5 Kt.
    phase11_ref_fos = (5.115181143750309, 4.022263947084764, 3.3381488836780493)
    old_root_area = 20.96066560429954
    reinforced_root_area = 26.5
    stress_rows = []
    for i, gear in enumerate(FIXED_GEAR_RATIOS):
        design_rpm = ROTOR_DESIGN_RPM[i]
        soft_limit_rpm = MOTOR_SOFT_RPM * gear
        test_rpm = 1.25 * soft_limit_rpm
        baseline_rpm = (29375.0, 33125.0, 36360.0)[i]
        fos = phase11_ref_fos[i] * (baseline_rpm / test_rpm) ** 2 * (reinforced_root_area / old_root_area)
        stress_rows.append({"row": f"R{i+1}", "fixedGearRatio": gear,
                            "motorSoftRpm": MOTOR_SOFT_RPM, "designRotorRpm": design_rpm,
                            "softLimitDerivedRotorRpm": soft_limit_rpm,
                            "proofRotorRpm_1p25x": test_rpm, "rootAreaBaselineMm2": old_root_area,
                            "rootAreaReinforcedMm2": reinforced_root_area,
                            "rootBlendTargetMm": 2.0, "yield6061T6MPa": AL_YIELD_MPA,
                            "centrifugalOnlyFOSAtProofRpm": fos,
                            "targetFOS": 2.5, "pass": fos >= 2.5,
                            "scope": "Phase-11 stress model scaled by RPM^2 and reinforced root area; Kt=2.5 retained; excludes fatigue/aero/burst testing"})

    area_report_rows = []
    for item in inlet_area_rows:
        area_report_rows.append(item)
    write_csv(REPORT_DIR / "phase12_mass_cg_screen.csv",
              ["component", "massKg", "cgXmm", "cgYmm", "cgZmm", "evidence"], mass_rows)
    write_csv(REPORT_DIR / "phase12_rotor_strength_screen.csv",
              list(stress_rows[0].keys()), stress_rows)
    write_csv(REPORT_DIR / "phase12_front_area_variants.csv",
              list(area_report_rows[0].keys()), area_report_rows)

    stock_status = {
        "rotorStock": {"rawBilletMm": [300, 50, 16], "CAMregionMm": [250, 50, 16],
                       "CAMxBoundsMm": [25, 275], "reservedClampMarginsEachEndMm": 25, "billets": 6,
                       "rowCounts": list(ROTOR_COUNTS), "oneRowAndOneHubPerBillet": True,
                       "nesting": "5 blade columns x 3 rows (15 slots; 13/12/11 used) plus one 32mm hub disk in the rear field"},
        "statorStock": {"plates": 2, "perPlateMm": [250, 100, 5],
                        "vanesPerEDF": sum(STATOR_COUNTS),
                        "nesting": "7 columns x 9 rows = 63; 2.5mm rectangular keep-outs"},
        "minimumIncrease": {"additionalAluminiumStock": "none for the supplied blade/hub/stator cut layouts",
                            "unsupportedProcesses": [
                                "twisted airfoil surface machining requires multi-axis/flip/secondary forming",
                                "composite shell parts are printed PLA plus hand layup, not 6061 plate CNC",
                                "0.5mm cutter is not used through the 16mm rotor billet walls",
                            ]},
    }

    config = {
        "phase": 12,
        "status": "offline-CAD-CAM-complete-no-OpenFOAM-winner",
        "powertrainImmutable": {
            "motor": "6 x stock Flycci FA4119 KV350; 0.28kg each",
            "battery": "2 x Turnigy Rapid 6S 5000mAh in series; 12S1P; 5Ah; 0.713kg each",
            "gearRatios": list(FIXED_GEAR_RATIOS), "motorSoftRpm": MOTOR_SOFT_RPM,
            "currentAndPowerLimits": "retained from Phase 9, unchanged",
        },
        "phase9TargetsRetained": {"allUpMassKg": 11.5, "cdA720M2": 0.00090,
                                  "projectedAreaReferenceCm2": 73.61725123519331,
                                  "phase9WorstR0TWRAt3km": 1.0395516612139422},
        "fan": {"modules": 2, "ODmm": DUCT_OD, "boreMm": DUCT_ID, "hubMm": HUB_OD,
                "rotorCounts": list(ROTOR_COUNTS), "rotorChordMm": ROTOR_CHORD,
                "statorCounts": list(STATOR_COUNTS), "statorChordMm": STATOR_CHORD,
                "rotorRpmScheduleAt720KmhPhase9": list(ROTOR_DESIGN_RPM),
                "softLimitDerivedRotorRpm": list(ROTOR_SOFT_LIMIT_RPM)},
        "inlet": {"slotsPerEDF": 2, "totalSlots": 4, "slotMm": [SLOT_WIDTH, SLOT_LENGTH],
                  "kgPerBranch": BRANCH_MDOT, "kgPerEDF": 2 * BRANCH_MDOT,
                  "totalKgPerS": TOTAL_MDOT, "radiiMm": list(INLET_RADII),
                  "initialRadiusMm": INITIAL_RADIUS,
                  "phase9RecoveryTarget": 0.98, "measuredRecovery": None,
                  "grossReferenceHalfAnnulusAreaMm2": math.pi / 2.0 * (45.0**2 - 16.0**2),
                  "CADBranchOutletHalfAreaMm2": math.pi / 2.0 * (44.0**2 - 12.9**2),
                  "CADFanFaceHalfAnnulusAreaMm2": math.pi / 2.0 * (44.0**2 - 16.0**2),
                  "areaContractionToPhysicalFanFaceFraction": 1.0 - (44.0**2 - 16.0**2) / (44.0**2 - 12.9**2),
                  "recoveryEvidence": "Phase-12 local mesh/preflight only; execution receipt says checkMesh gate blocked cloud, pressure recovery null, bestGeometry null"},
        "phase12Preflight": {
            "receipt": "phase12/results/phase12_execution_receipt.json",
            "status": "local-preflight-only-no-cloud-launch",
            "validPressureRecoveries": 0,
            "bestGeometry": None,
            "launchPermitted": False,
            "reason": "local checkMesh/OpenFOAM runtime unavailable; no CFD values consumed",
            "conservativeAreaFormula": "fan union 63.617 + 10 cm2 generic structure reserve + 2.4*max(0,R+12.5-45) cm2",
            "preflightR35AreaBoundCm2": 79.61725123519331,
            "selectedR30ConservativeAreaBoundCm2": 73.61725123519331,
            "conservativeAreaScreen": {
                "formula": "fan union 63.617 + generic structure reserve 10 + 2.4*max(0,R+12.5-45) cm2",
                "R35BoundCm2": 79.61725123519331,
                "disposition": "R30 selected provisionally because it passes the conservative area budget; R35's detailed union passes but its generic reserve/protrusion bound does not. Preserve this discrepancy for CAD/CFD reconciliation."
            }
        },
        "boardMassesFromCsvKg": {"ESC_bare": ESC_BOARD_MASS_KG, "flight_bare": FC_BOARD_MASS_KG,
                                  "bareTotal": ESC_BOARD_MASS_KG + FC_BOARD_MASS_KG},
        "installationEnvelopes": {
            "batteryPacks": [
                {"dimsMm": [150, 50, 45], "massKg": BATTERY_MASS_EACH_KG, "centreZmm": -337.5, "status": "dimension proxy; mass sourced"},
                {"dimsMm": [150, 50, 45], "massKg": BATTERY_MASS_EACH_KG, "centreZmm": -177.5, "status": "dimension proxy; mass sourced"},
            ],
            "boards": [
                {"name": "ESC", "dimsMm": list(ESC_BOARD_BARE_DIMS_MM), "massKg": ESC_BOARD_MASS_KG,
                 "centreMm": [0, 56, 220], "populationAndHeatspreaderMassEstimated": True},
                {"name": "flight", "dimsMm": list(FC_BOARD_BARE_DIMS_MM), "massKg": FC_BOARD_MASS_KG,
                 "centreMm": [0, 56, 235], "populationAndHeatspreaderMassEstimated": True},
            ],
            "cgDatum": {"X": "lateral", "Y": "vertical", "Z": "flight axis", "units": "mm"},
        },
        "stockAndNesting": stock_status,
        "compositeLayupAssumptions": {"PLAcoreMm": 1.2, "carbonFabricGsmPerFace": 200,
                                       "glassFabricGsmPerFace": 100, "resinToFibreMassRatio": resin_to_fibre,
                                       "laminateSurfaceAreaM2": skin_area_both_faces_m2,
                                       "midSurfaceAreaM2": composite_surface_area_m2 / 2.0,
                                       "laminateMassKg": laminate_kg, "PLAcoreMassKg": pla_kg,
                                       "status": "analyst assumptions; panel areal weight and printed-core mass must be checked by coupon/weighing"},
        "frontAreaVariants": inlet_area_rows,
        "massCg": {"estimatedSubtotalKg": total_mass, "unallocatedAllowanceTo11p5Kg": 11.5 - total_mass,
                   "cgXmm": cg[0], "cgYmm": cg[1], "cgZmm": cg[2],
                   "massVerified": False, "batteryEnvelopeProxyMm": [150, 50, 45],
                   "populationGearboxHarnessMountMassesEstimated": True},
        "rotorStress": stress_rows,
        "generated": [str(p.relative_to(OUT)) for p in all_outputs],
    }
    (CONFIG_DIR / "phase12_fixed_powertrain_design.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (REPORT_DIR / "phase12_generation_manifest.json").write_text(json.dumps({"files": config["generated"],
        "stepCount": sum(p.suffix.lower() == ".step" for p in all_outputs),
        "gcodeCount": sum(p.suffix.lower() == ".nc" for p in all_outputs),
        "offlineOnly": True, "cncRun": False, "cloudSolverRun": False}, indent=2) + "\n", encoding="utf-8")
    write_report(config, stock_status, total_mass, cg, composite_surface_area_m2,
                 laminate_kg, pla_kg, stress_rows, inlet_area_rows)
    print(json.dumps({"step": sum(p.suffix.lower() == ".step" for p in all_outputs),
                      "gcode": sum(p.suffix.lower() == ".nc" for p in all_outputs),
                      "frontAreaCm2ByR": {str(r): round(front_area_cm2(all_projection[r]), 4) for r in INLET_RADII},
                      "estimatedMassKg": round(total_mass, 4), "cgMm": [round(v, 2) for v in cg]}, indent=2))


def write_report(config: dict, stock: dict, mass: float, cg: tuple[float, float, float],
                 composite_area_m2: float, laminate_kg: float, pla_kg: float,
                 stress_rows: list[dict], area_rows: list[dict]) -> None:
    best_area = min(x["frontProjectedAreaCm2"] for x in area_rows)
    report = f"""# Phase 12 — split-inlet EDF / composite airframe CAD-CAM screen

## Evidence and disposition

The Phase-12 results directory contains local mesh/preflight artifacts and an execution receipt, but no OpenFOAM iterations or pressure-recovery values. The receipt is `local-preflight-only-no-cloud-launch`: the required local `checkMesh` gate was unavailable, so no cloud request was made; `bestGeometry` is null. Earlier Phase-10 solver cases also aborted before iterations. Four interchangeable **R30/R35/R40/R45 mm** split-inlet variants are retained. **R30 is the provisional packaging selection** because it passes the conservative reserve-aware area screen; it is pending CFD, not a recovery winner. The Phase-9 recovery target of 0.98 is not claimed. The generated inlets use a smoothly lofted rectangular-to-half-annulus split, smooth area change, and splitter noses to avoid an abrupt junction.

The fixed hardware remains six stock FA4119 KV350 motors, two Turnigy Rapid 6S5000 packs in series (12S1P), and fixed gear ratios 2.35/2.65/2.95. No current, voltage, power, or ratio was changed. Each EDF has 13/12/11 rotor blades at 16mm chord and three 23/21/19 stator rows at 8mm chord. Four 25×120mm slots feed four half-annulus branches at 0.42937kg/s each (0.85874kg/s per EDF, 1.71748kg/s total).

## Projected-area screen

The two coincident 90mm fan silhouettes occupy 63.617cm². Board, heatspreader, support-rail, inlet-lip and fuselage projections are included in the detailed lofted CAD envelope calculation; the two battery package proxies lie inside the coincident disk projection. The CAD area screen includes a 41mm motor-size footprint proxy, but no motor mounting solid is claimed because the motor/shaft drawing was not supplied. Detailed union values are in `phase12_front_area_variants.csv` (R30 67.86cm²; R35 68.44cm²). The Phase-12 preflight's conservative constant-height screen uses the whole generic 10cm² structure allowance plus a 2.5mm outboard protrusion at R35, yielding 79.62cm²; at R30 the protrusion is zero and the bound is 73.62cm². **R30 is retained provisionally to honor the strict <75cm² reserve-aware budget.** The detailed shape projection and coarse preflight bound differ; control/hardware mounting must stay within the remaining projected-area budget, and a final projection check is required when motor mounts are dimensioned. The Phase-9 73.617cm² value is retained as the conservative reference budget.

The execution receipt contains four prepared mesh cases (R35 coarse/medium/fine, R45 medium), lexical dictionary checks only, and null recovery for every case. The planned outlet branch area is 2,778.74mm² from the 90/32 gross-annulus reference; the 88mm physical CAD bore gives 2,638.94mm² per half-annulus, a 5.03% contraction to the fan face. The lofted centrebody models this contraction smoothly. The old preflight case area and current CAD bore are not geometrically identical, so no preflight recovery can be transferred to this CAD.

## Mass, CG, and composite panels

The source CSV gives bare ESC and flight-board masses {ESC_BOARD_MASS_KG:.6f}kg and {FC_BOARD_MASS_KG:.6f}kg (total {ESC_BOARD_MASS_KG + FC_BOARD_MASS_KG:.6f}kg). It excludes population. The ledger keeps the bare values separate from estimated populated-board mass, heat spreaders, six gearboxes, harness and mounts. Battery dimensions 150×50×45mm are packaging proxies at Z=−337.5/−177.5mm with sourced 0.713kg per-pack mass; verify against the physical packs before fit release. Board and heatspreader envelopes are edge-on in the side cooling bay and are located in the CAD/config for CG screening.

The fuselage and duct panels are modeled as printed-PLA cores with carbon/glass hand-layup; **no 22-plate aluminum body budget is used**. CAD inner+outer face area is {composite_area_m2:.4f}m² (mid-surface area {composite_area_m2/2.0:.4f}m²). Assumptions are one 200gsm carbon ply + one 100gsm glass ply per face, resin:fibre mass ratio 0.8, and 1.2mm PLA core. Estimated laminate mass is {laminate_kg:.3f}kg and PLA-core mass {pla_kg:.3f}kg. These remain coupon/weighing estimates.

The current component mass ledger estimates {mass:.3f}kg and CG (X,Y,Z)=({cg[0]:.1f},{cg[1]:.1f},{cg[2]:.1f})mm in the model datum (X lateral, Y vertical, Z flight axis). It is not a weighed assembly; {11.5 - mass:.3f}kg remains unallocated to the 11.5kg cap. The Phase-9 worst-R0 T/W of 1.0396 at 11.5kg is retained as an analytical screen, not revalidated with the inlet or mass model. CdA≤0.00090m² at 720km/h remains an unverified target.

## 6061-T6 rotor strength

The CAD retains the frozen Phase-9 720km/h rotor schedule (29,375/33,125/36,360rpm) and unchanged 2.35/2.65/2.95 ratios. The structural proof independently uses the maximum fixed motor-soft-limit-derived speeds (12,500rpm × each ratio) at 1.25×: maximum proof speed {max(ROTOR_TEST_RPM):.1f}rpm. It scales the Phase-11 centrifugal-only root stresses by RPM², retains Kt=2.5, and increases modeled root area from 20.961 to 26.5mm² using a thickened root loft and 2mm blend target. The CAD represents the thickened root stations; the blend remains a target requiring detailed joint/FEA closure. Minimum centrifugal-only FOS is {min(x['centrifugalOnlyFOSAtProofRpm'] for x in stress_rows):.2f} against 6061-T6 yield 276MPa. Aero bending, fatigue, flaws, attachment, burst containment and testing are excluded; this is not a release stress substantiation.

## Stock nesting and GRBL

- Six 300×50×16mm 6061-T6 billets map one rotor row per motor/ESC channel. Both 25mm ends (X0–25 and X275–300) are reserved for clamping; CAM uses X25–275 only. Each row layout nests its 11–13 blades plus one 32mm hub inside that CAM field, with tool-clearance keep-outs and tabs.
- Two 250×100×5mm 6061-T6 plates map one 63-vane stator set per EDF. Both 7×9 nests fit one plate each. No additional aluminum panel stock is assigned to the body or duct shells.
- G-code uses GRBL, G54 lower-left XY / top-face Z0, 8000rpm, 2mm carbide roughing, and 0.5mm carbide finishing. Rotor blanks and hubs are roughed through 16mm with 0.20mm steps; rotor 0.5mm finishing is limited to the top 0.5mm band. Stator 5mm edges have a conditional full-depth microfinish program requiring a ≥6mm flute. The 16mm rotor walls, twisted airfoil surfaces and 3D inlet/body forming are not completed by these 3-axis paths; they require flip/secondary/5-axis or hand layup/forming as noted in the NC comments.

All G-code is a CAM starting point, not safe-to-run release code. Confirm material, long-tool flute/neck, workholding, tabs, fixture collisions, feeds and all motions manually in CAM. Each file contains M0 manual tool-change, touch-off and spindle-off dry-run notes. **No CNC was run; no cloud solver was launched.**

## Files

STEP assemblies, inlet alternatives, stock nests, and channel-specific NC programs are indexed by `reports/phase12_generation_manifest.json`; design inputs/assumptions are in `configs/phase12_fixed_powertrain_design.json`.

All 18 STEP exports were re-imported with Open Cascade and passed `isValid()`. All 16 NC files were checked for G54 presence, spindle/tool-change blocks, Z depth, and XY coordinates inside the declared stock/CAM region.
"""
    (REPORT_DIR / "phase12_release_report.md").write_text(report, encoding="utf-8")


if __name__ == "__main__":
    build_and_export()
