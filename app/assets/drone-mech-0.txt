# Phase-15 geometry generation and manufacturing report

Generated from `design/HANDOFF_GEOMETRY_AGENT.md`. Coordinate convention: X lateral, Y vertical, +Z aft,
Z=0 at the first rotor plane. Units are mm unless noted. CAD is a mechanical layout
model and envelope set; it is not a fabrication or flight-release design.

## Delivered CAD

- `step/phase15_airframe_full_assembly.step` — airframe, two independent 80 mm fan paths, rotor/stator rows, effectors, battery bay, motors as sourced envelopes, and landing/board support geometry.
- `step/phase15_esc_cooling_assembly.step` — 150×150 mm six-channel ESC, 36 MOSFET envelopes, six fuses/busbars, 150×150 spreader, flight board, 100×80 spreader, open-ended cooling tunnel and mounts.
- `step/*.step` — each registered part/subassembly exported separately; all stock nests are in `stock_nests/`.
- `reports/projected_frontal_silhouette.svg` — projected union drawing with the twin through-ducts visibly open around physical fan hardware.
- `reports/mass_cg.csv`, `reports/step_reimport_validation.csv`, `reports/phase15_parameter_register.json`.

## Nominal selections and manufacturing process

- Fan tubes use Ø82 OD / Ø78 bore (2 mm radial wall), two axes at X=±44; the 82 mm OD is inside the 72–90 band and keeps a true 2 mm composite wall. The inlet mouths are Ø84 mm side-facing ports, 55.4 cm² each (110.8 cm² total), with a 2.5 mm toroidal lip and a 100 mm segmented elbow into the axial ducts.
- Body and wing are modeled as 1.2 mm skins over cold-side PLA core, with the two EDF passages kept clear. The fuselage is a 640 mm master shell with internal frames at Z=-100/+100 mm; section the master at those planes into ≤260 mm FDM pieces and use sealed scarf/flange joints. Split the 520 mm wing on the X=0 joiner web into two 260 mm panels. Main shell and wing use composite wrap; no PLA is assigned to the duct, nozzle, motor bay or hot-side insert.
- Duct/nozzle hot-side shell is represented as high-temperature CF composite; qualify core/resin service temperature and hoop strength before manufacture. A 6061 insert/capture ring is required at every rotor-retention station. The exact high-temperature material and insert fastener details are not present in the source data.
- All 72 rotor and 126 stator blanks are nested on the stated 250×120×5 and 300×120×5 sheets, split evenly (36+63 per sheet), with at least 1.5 mm blank clearance and 1 mm sheet-edge margin. Profile bounds are used when placing the blanks; the previous rotor origin put the first row 3.1 mm beyond the lower sheet edge. Native STEP verification is recorded in `reports/phase15_stock_nest_bounds_validation.json`, with the correction documented in `reports/phase15_stock_nest_bounds_fix.md`. The nests are geometry-only: rough blanks require indexed/two-sided machining, deburring, root retention, balance and overspeed qualification. The 300 mm sheet consumes the nominal X travel of a 3018-class machine; side clamps/vacuum fixture and tool overtravel must be validated before CAM.
- Six Ø40×16 hubs fit the 300×50×16 bar inside a 250 mm usable length with 25 mm end clamp zones. Hub turning/bore finishing and rotor balancing are separate operations. No production G-code is emitted from an unverified fixture.

## Constraint audit / unavoidable incompatibilities

1. The body section height is 88 mm rather than the 78 mm nominal because the 80+ mm outer duct pair must fit; 88 mm is within the 72–90 mm section band. Body outline area is approximately 140 cm² for exponent 2.6, within the stated 126–185 cm² band.
2. The 200×135×75 mm reserved bay is aligned with Z as its 200 mm axis. The two supplied 185×65×55 packs fit side-by-side in X with 5 mm total width clearance and are slid to Z=-207.5 so their aft faces clear the side-inlet passages. Full-section body from the forward bay boundary to aft keeps this envelope inside the shell; body length is selected at the 640 mm upper bound.
3. The 72 mm motor envelopes are placed immediately aft of their rotor hubs. Rotor stations are 36 mm apart, so adjacent motor envelopes overlap axially by 36 mm. This violates physical buildability; the sourced motor size and rotor-row pitch cannot both be met with coaxial direct drive. The STEP intentionally shows the envelope collision; no overlap is hidden or boolean-subtracted.
4. Four separate vanes plus two elevons and one rudder require seven servos. All seven mounts/horns are modeled. The fixed flight-board interface has six PWM channels (F-05 remains unresolved), so one surface has no assigned command channel. No common-exit redesign is assumed.
5. The ESC and flight-board locations (Y≈52, Z≈220/345) are outside the 88 mm body section and are carried by the specified dorsal, open-ended cooling tunnel. The duct bleed-air inlet/flow rate remains a thermal design item; the tunnel has forward and aft open ports.
6. The 640 mm body length and 200 mm bay leave only about 60 mm between the forward bay boundary and the nose tip in this datum. The specified 2.5–5 nose-fineness ratio cannot be achieved simultaneously with this bay placement and length band; the nose is a packaging-driven short loft, not a drag-qualified ogive.
7. Stator vane angles are a neutral adjustable seed because no phase-15 metal-angle schedule was found in the supplied authoritative files. Blade-angle/performance, rotor containment, flutter and composite hoop strength are not validated by CAD.
8. CAD projected frontal solid union is 248.0 cm² versus the 242–296 cm² target. The fan bores are modeled as through-holes; the physical duct rings, fan annuli, hubs and fins remain in the union. This measured CAD projection is reported as-is; no solid area is added to force the target.
9. CAD mass properties give 6.541 kg including the 1 kg payload, and 7.522 kg with the specified 15% growth reserve. CG is (0.1, 6.7, -4.0) mm from the fan datum. The 1 kg payload is a point mass at Z=-320 mm, 20 mm forward of the bay; its envelope and mount must be checked against the installed part. Motor, pack and servo masses are explicit source/analyst overrides; this is not a weighed aircraft.

## STEP validation

Reimport test results: 81/81 files passed positive-volume/valid-solid checks. See `reports/step_reimport_validation.csv` for per-file solid counts and volumes.

## Geometry is complete, hardware compatibility is not

The requested airframe and ESC CAD, mounts, toleranced stock nests, silhouette,
mass/CG estimate and source/assumption register are present. The numbered
interference/channel issues above are design gates from mutually incompatible
inputs, not missing CAD parts.
