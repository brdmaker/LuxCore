---
name: luxcore-render-cad-part
description: Use when making a photoreal render (product shot) of a CAD part or assembly with luxcoreconsole - rendering a SolidCraft design with the materials and looks assigned in it (solidcraft_to_luxcore.py), converting STL (e.g. from solidcraft-cli) to PLY with smooth crease-angle normals, framing the camera from the bounding box, studio or daylight lighting, metal and plastic materials, denoising, and judging the result. Ships scripts/luxcore_part_scene.py which writes a ready-to-render scene.
---

# Photoreal renders of CAD parts

LuxCore cannot read STL, so `scripts/luxcore_part_scene.py` (Python stdlib only) converts
the part and writes a complete, tuned studio scene around it. Get the CLI first
(`luxcore-cli-start`).

## Quick path

```bash
S=/home/user/LuxCore/.claude/skills/luxcore-render-cad-part/scripts/luxcore_part_scene.py
X=/home/user/LuxCore/.claude/skills/luxcore-render-cad-part/scripts/solidcraft_to_luxcore.py
python3 $S part.stl --material aluminium --out /tmp/r/part --denoise
luxcoreconsole -d /tmp/r/part render.cfg 2>&1 | grep -E "Samples|ERROR|Done" | tail -2
# -> /tmp/r/part/render.png   (1200x900, 256 spp, ~2-3 min on 4 CPU threads)
```
Then **look at the image** (Read the PNG) before using it. For SolidCraft parts prefer
`solidcraft_to_luxcore.py` (next section): it takes the materials from the model.

Assemblies: one argument per body, each with its own material:
```bash
python3 $S housing.stl:plastic-black shaft.stl:steel-polished nut.stl:brass --out /tmp/r/asm
```

Getting the STL from SolidCraft (in a 3dassets-style repo):
`solidcraft-cli run part.json --out /tmp/r/part.stl` (mm, Z up), or use a stored `.stl`.

## From a SolidCraft design, with its own materials (preferred)

`scripts/solidcraft_to_luxcore.py` renders a SolidCraft script (`.json`), design (`.sc`) or
STEP with the looks assigned in SolidCraft, so materials are described once, in the CAD model:
```bash
export SOLIDCRAFT_CLI=$HOME/solidcraft-bin/solidcraft-cli   # see solidcraft-cli-start in 3dassets
cd <part folder>                                          # scripts may open files relatively
python3 $X part.json --out /tmp/r/part [--overrides render.json] [any scene option below]
luxcoreconsole -d /tmp/r/part render.cfg
```
It only drives `solidcraft-cli` (no SolidCraft code is copied or linked), in two runs:
1. the script + `inspect.measure` (body names, physical material, density, volume, mass),
   saved to a temporary design;
2. on that design: `appearance.list {body}` per body (the resolved look of the body and of each
   face: face > body > component > material) and one `file.export` as **`3mf-tagged`**, whose
   triangles carry their B-rep face index, in world placement (assemblies come out assembled).

Each body is split by look (so a face override renders on that face only) and normals are
**smoothed within each B-rep face only**: curved faces are smooth, every real CAD edge is sharp,
with no crease-angle guess. Output: the usual `render.cfg`/`scene.scn`/`part_*.ply`, plus
`materials.json` (per body: physical material, density, volume, mass, SolidCraft look and the
LuxCore material used) for README rows.

### How a SolidCraft look becomes a LuxCore material

| SolidCraft look | LuxCore |
|---|---|
| `color` (sRGB hex) | `disney.basecolor`, sRGB → linear |
| `pbr.metallic` | `disney.metallic` |
| `pbr.roughness` (perceptual 0.045-1) | `disney.roughness` (same scale; LuxCore squares it, like SolidCraft) |
| `pbr.dielectric_ior` | `disney.specular = ((ior-1)/(ior+1))^2 / 0.08` (1.5 → 0.5) |
| scalar look (no `pbr`) | `disney`, metallic 0, roughness 0.5 |
| `opacity` < 1 | `glass`, `kt` = colour, `interiorior` = IOR (an approximation: SolidCraft's alpha is not physical glass) |
| no look at all | neutral grey **placeholder**, with a warning |

`--overrides render.json` replaces the converted material with raw LuxCore properties where a
PBR look is not enough (measured metal n/k, real glass, textures), keyed by body, physical
material or appearance name (body wins, then material, then appearance):
```json
{"bodies": {"LeadScrew": {"type": "metal2", "n": "2.87 2.95 2.65", "k": "3.12 2.93 2.81",
                          "uroughness": "0.04", "vroughness": "0.04"}},
 "materials": {"EN AW-6082-T6": {"type": "metal2", "preset": "aluminium",
                                 "uroughness": "0.2", "vroughness": "0.2"}}}
```
Warnings name bodies without a look and bodies on SolidCraft's placeholder `Default` material
(1.29 g/cm³: the mass is not real). `--bodies A B` renders a subset; `--quality` sets the
export tessellation (default `fine`).

### Describing materials in SolidCraft (the convention this tool expects)
1. **Physical material = the grade**, for mass: `material.create {name: "EN AW-6082-T6",
   density_g_cm3: 2.70}` then `material.assign`. State the source of the density.
2. **Appearance = the finish**, as PBR, preferably as the material's default look so its bodies
   inherit it: `material.create/edit {..., color: "#c8cacc", pbr: {metallic: 1,
   roughness: 0.25, dielectric_ior: 1.5}}`; override per body or face with `appearance.assign`
   (faces by a point on them: `faces: [{body, point: [x,y,z]}]`, without `bodies`, or the whole
   body changes too). The `starter.*` looks (`appearance.library`) are a good palette.
3. **Render-only physics** (n/k, glass, textures, lighting) in `render.json` next to the part.

Checked 2026-11-11 with solidcraft-cli 0.27.1: material default look, body override, face
override (top face only), the 3dassets NEMA17 assembly (3 bodies, placements correct) and a
metal2 override.

## Options

| Option | Default | Notes |
|---|---|---|
| `FILE[:material]` | | `.stl` (ASCII/binary) or `.ply`; repeat for several bodies |
| `--material` | `aluminium` | for files without `:material` |
| `--view` | `iso` | `iso`, `iso-back`, `front`, `back`, `left`, `right`, `top`, `low` |
| `--zoom` | 1.0 | >1 moves closer; camera auto-frames the bounding sphere |
| `--fov` | 30 | degrees, spans the longer image side |
| `--width/--height` | 1200/900 | |
| `--spp` / `--time` / `--noise` | 256 / 600 / off | halt conditions (spp or time, whichever first) |
| `--env` | `studio` | `studio`: key + rim softboxes (camera-invisible, seen in reflections) and a dim fill; `sky`: sun and sky (blue cast, hard shadows) |
| `--env-map FILE` | off | equirectangular (360°x180°) environment image (`.exr`/`.hdr`, or `.jpg`/`.png`): lights the part, shows behind it and in reflections; copied into `--out` as `environment.<ext>`; replaces `--env` |
| `--env-rotate` | 0 | turn the environment about Z (degrees); try 0/90/180/270 at low res and pick |
| `--env-gain` | 1 | environment brightness |
| `--floor` | `white` (`shadowcatcher` with `--env-map`) | `white`, `grey`, `shadowcatcher`, `none` |
| `--exposure` | auto | `TONEMAP_LINEAR` scale instead of auto exposure; `1` suits both `studio` and `sky` (the sky is pre-scaled to match); use one value for a consistent series |
| `--denoise` | off | Intel OIDN (+ albedo/normal AOVs); 128 spp + denoise looks clean |
| `--transparent` | off | also `render_alpha.png` (RGBA); pair with `--floor shadowcatcher` (keeps a soft, partly transparent floor shading near the part) or `none` (clean cut-out) |
| `--crease` | 30 | smooth-normal crease angle in degrees; 0 = flat facets |
| `--up` | `z` | `y` for Y-up exports (rotated to Z-up) |

Materials: `aluminium`, `aluminium-brushed`, `steel`, `steel-polished`, `brass`, `copper`,
`gold`, `anodized-black`, `plastic-black|white|grey|red|blue`, `rubber`, `glass`, `clay`
(neutral grey, good for checking form). The script prints the bounding box and triangle
counts; the `.scn` it writes is plain text, so edit it for anything else (colours, roughness,
extra lights; see `luxcore-scene-format`).

## Environment maps (image-based lighting)

```bash
python3 $S part.stl:steel --env-map warehouse.jpg --env-rotate 180 --view low --denoise --out /tmp/r/wh
```
- The script sets `gamma = 1` for `.exr`/`.hdr` (already linear) and keeps LuxCore's default
  2.2 for 8-bit `.jpg`/`.png`, so both come out right.
- A true HDR (`.exr`/`.hdr`) is much better: an 8-bit JPEG clips the bright parts (windows,
  lamps), so shadows and highlights come out weak and the part tends to look like it floats.
- `--view low` shows the surroundings behind the part; `iso`/`top` mostly show the map's
  floor. Facing a bright door or window makes auto exposure darken the part: rotate the map
  or set `--exposure`.
- The map is a distant sphere: its floor is not a real floor. The shadowcatcher floor adds
  contact shadows only where the map has a clearly brighter direction.
- Background sharpness depends on map resolution vs field of view: a 2.5k-wide map at
  `--fov 30` looks soft (about 7 map pixels per degree, stretched over ~40 image pixels per
  degree at 1200 px); use 8k+ maps, a wider `--fov`, or accept a "depth of field" look.
- Checked with a 2576x1288 JPEG warehouse panorama (2026-11-11): all four rotations render;
  1200x800, 128 spp + OIDN took 2.5 min on 4 threads.

## What the script does (so you can do it by hand)
1. Reads STL/PLY, writes `part_<n>.ply` (binary, unshared vertices, **per-corner normals
   averaged over faces within the crease angle**). Without normals, cylinders and fillets
   show facets; with plain averaging, sharp CAD edges go soft. The crease angle fixes both.
2. Frames a perspective camera on the bounding box: projects the 8 corners onto the view
   plane and takes the smallest distance at which all fit (5% margin), looking at the box
   centre along the view direction (Z up). LuxCore's FOV spans the longer image side.
3. Floor = big quad at the part's lowest Z. Softboxes = emissive quads 4r away whose triangle
   normal faces the part (emission is one-sided: reversed winding = no light), marked
   `camerainvisible = 1` so they show only in reflections.
4. `render.cfg`: PATHCPU, depths 8/4/6/8, `path.clamping.variance.maxvalue = 10` (tames
   fireflies on metal), epsilon scaled to the part size, outputs relative to the folder.

## Judging and fixing the image

| Looks like | Fix |
|---|---|
| Everything mid-grey, low contrast | auto exposure averaging a big white floor: `--exposure 1` (studio, try 0.7-1.5) |
| Metal looks flat grey | metals only show what they reflect: keep `studio` (softboxes give highlights); raise roughness for a satin look; `--env sky` for outdoor reflections |
| Faceted cylinders | STL too coarse or `--crease 0`; export finer tessellation; keep crease 30 |
| Soft, rounded-looking edges | crease too high (>60): lower it |
| Speckles / fireflies | more `--spp`, or `--denoise`; metals under `--env sky` (tiny bright sun) need the most |
| Part too small | the camera fits the whole bounding box; a tall part in a landscape frame comes out thin: use portrait (`--width 600 --height 1200`) or `--zoom 1.3` |
| Part floating or sunk | the floor sits at min Z; parts modelled below the origin are fine. For a part that should lie on a side, rotate the STL first (or set `.transformation` on the object) |
| Black image | lights facing away after manual edits; check the softbox `faces` order |
| Takes too long | preview at `--width 480 --height 360 --spp 32`, final at full size |

Timing reference (4 threads, PATHCPU, 7k triangles): 800x600 @ 128 spp ≈ 60-80 s.
Large meshes (1M+ triangles) load slowly in pure Python (the normal pass); decimate in the
CAD tool or pass `--crease 0` for speed.

## Storing renders
Renders are derived images: commit them only where the repo wants them (e.g. a `render.png`
next to a part, linked from its README), and say they are LuxCore renders with the
material/lighting used. Never commit the LuxCore binary.
