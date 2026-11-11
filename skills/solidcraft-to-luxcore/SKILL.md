---
name: solidcraft-to-luxcore
description: Use when rendering a SolidCraft part or assembly (script .json, design .sc or STEP) photorealistically in LuxCore with the materials and looks assigned in SolidCraft - setting up solidcraft-cli, luxcoreconsole and solidcraft_to_luxcore.py, describing materials in SolidCraft (physical grade + PBR look, per body or face), adding looks to a STEP or generated part with --looks, LuxCore overrides in render.json, reading materials.json, checking mass, and fixing grey or wrong-looking bodies.
---

# SolidCraft → LuxCore with the model's own materials

`solidcraft_to_luxcore.py` renders a SolidCraft model in LuxCore using the materials described
**in the model**. It drives `solidcraft-cli` only (no SolidCraft code is linked or copied):

1. run the source + `inspect.measure` → bodies, physical material, density, volume, mass;
2. on the saved result: `appearance.list` per body (resolved look of body and faces:
   face > body > component > material) + `file.export` as `3mf-tagged` (triangles carry their
   B-rep face, world placement, so assemblies come out assembled);
3. converts each look to a LuxCore material, smooths normals inside each B-rep face only
   (curved faces smooth, CAD edges sharp), and writes a studio scene with
   `luxcore_part_scene.py`.

## 1. Setup (once per session, ~2 min)

Two CLIs and two Python files (stdlib only).

```bash
# solidcraft-cli: prebuilt on the orphan `binaries` branch of brdmaker/solidcraft
SC=$HOME/solidcraft-bin; mkdir -p $SC
git -C /home/user/solidcraft fetch -q origin binaries
git -C /home/user/solidcraft show origin/binaries:linux-x86_64/solidcraft-cli.gz > $SC/solidcraft-cli.gz
gunzip -f $SC/solidcraft-cli.gz && chmod +x $SC/solidcraft-cli
export SOLIDCRAFT_CLI=$SC/solidcraft-cli

# luxcoreconsole + the scripts: newest orphan luxcore-cli-<date> branch of brdmaker/LuxCore
L=/home/user/LuxCore                     # attach brdmaker/LuxCore to the session if missing
git -C $L fetch -q origin 'refs/heads/luxcore-cli-*:refs/remotes/origin/luxcore-cli-*'
BR=$(git -C $L branch -r --list 'origin/luxcore-cli-*' | sort | tail -1 | tr -d ' ')
LX=$HOME/luxcore-bin; mkdir -p $LX
git -C $L show $BR:luxcore-cli-linux-x86_64.tar.xz | tar -xJ -C $LX
export PATH=$LX/luxcore-cli-linux-x86_64/bin:$PATH
T=$HOME/sc2lux; mkdir -p $T
for f in luxcore_part_scene.py solidcraft_to_luxcore.py; do
  git -C $L show $BR:skills/luxcore-render-cad-part/scripts/$f > $T/$f; done
X=$T/solidcraft_to_luxcore.py
```
Check: `$SOLIDCRAFT_CLI --version`, `luxcoreconsole -h`, `python3 $X -h`.
In a LuxCore checkout that has `.claude/skills/luxcore-render-cad-part/scripts/`, you can use
those two files instead of fetching them. Details: `luxcore-cli-start` (LuxCore) and
`solidcraft-cli-start` (3dassets). Never commit either binary.

## 2. Describe the materials in SolidCraft

Two separate things, both saved in the design:

| What | Command | Used for |
|---|---|---|
| **Physical material** = the grade | `material.create {name, density_g_cm3}` + `material.assign {bodies, material}` | mass (`inspect.measure`), documentation |
| **Look** = the finish, PBR | `color` (sRGB hex) + `pbr {metallic 0-1, roughness 0.045-1, dielectric_ior 1-3}` on the material (default look, inherited by its bodies) or with `appearance.assign` on bodies / components / faces | the render |

```json
{"command":"material.create","params":{"name":"EN AW-6082-T6","density_g_cm3":2.70,
  "color":"#c8cacc","pbr":{"metallic":1,"roughness":0.25,"dielectric_ior":1.5}}}
{"command":"material.assign","params":{"bodies":["Housing"],"material":"EN AW-6082-T6"}}
{"command":"appearance.assign","params":{"bodies":["Cover"],"color":"#141416",
  "pbr":{"metallic":0,"roughness":0.35,"dielectric_ior":1.5}}}
{"command":"appearance.assign","params":{"faces":[{"body":"Housing","point":[0,0,20]}],
  "color":"#b02020","pbr":{"metallic":0,"roughness":0.3,"dielectric_ior":1.5}}}
```
- Faces are picked by **a point on the face** (`model.faces {body}` lists a `point` per face).
  Pass `faces` **without** `bodies`: with both, the whole body gets the look too.
- An `appearance.assign` replaces the whole look (not a partial patch).
- Ready-made finishes: `appearance.library` (`starter.*` IDs: woods, metals, plastics).
- Name the grade, not the look, in the material; state the density source in the README.

**Where to put these commands**
- In the part's own script, if the part should carry its materials (3dassets: then re-render
  `iso.png` as CLAUDE.md requires, since the script changed).
- In a separate **`looks.json`** passed with `--looks` when the source is a STEP, a generated
  script you don't want to touch, or a quick experiment. Same `{"commands": [...]}` format; it
  runs after the source.

### Starting values (typical; check your grade)

| Finish | color | metallic | roughness | Grade, density g/cm³ |
|---|---|---|---|---|
| Machined aluminium | `#c8cacc` | 1 | 0.25 | EN AW-6082 2.70 |
| Bead-blasted aluminium | `#bfc1c3` | 1 | 0.45 | |
| Black anodised | `#141416` | 0 | 0.35 | (aluminium) |
| Ground steel | `#9a9ca0` | 1 | 0.2 | C45 / 1.0503 7.85 |
| Polished stainless | `#c4c6c8` | 1 | 0.08 | 1.4301 (304) 7.93 |
| Brass | `#d4b06a` | 1 | 0.2 | CuZn39Pb3 8.47 |
| Copper | `#d08a68` | 1 | 0.2 | Cu-ETP 8.96 |
| Black oxide steel | `#2a2b2d` | 1 | 0.4 | (steel) |
| POM white | `#eeede8` | 0 | 0.3 | POM-C 1.41 |
| ABS / PA black | `#1a1a1c` | 0 | 0.4 | ABS 1.04, PA6 1.13 |
| Rubber | `#0e0e0e` | 0 | 0.8 | NBR ~1.0-1.3 |
| Paint (RAL 7035 grey) | `#cbd0cc` | 0 | 0.4 | |

`dielectric_ior` 1.5 suits paints and plastics; metals ignore it.

## 3. Run

```bash
cd <part folder>              # scripts may open files relatively (doc.open); or pass --cwd
python3 $X part.json --out /tmp/r/part --denoise
luxcoreconsole -d /tmp/r/part render.cfg 2>&1 | grep -E "Samples|ERROR|Done" | tail -2
```
Sources: script `.json`, design `.sc`, or `.step` (started with `--in`).

| Exporter option | Meaning |
|---|---|
| `--out DIR` | output folder (required) |
| `--looks FILE` | extra SolidCraft commands after the source (materials, looks) |
| `--overrides FILE` | `render.json`: raw LuxCore materials (below) |
| `--bodies A B` | only these bodies |
| `--quality standard\|fine\|finest` | export tessellation (default `fine`) |
| `--cwd DIR` | folder the script runs in (default: the source's folder) |

Every other option goes to the scene writer: `--view iso|front|low|top|...`, `--zoom`,
`--width/--height` (portrait for tall parts), `--spp`, `--time`, `--exposure 1`,
`--env studio|sky`, `--env-map pano.exr --env-rotate 180`, `--floor`, `--transparent`,
`--denoise`. See `luxcore-render-cad-part`.

## 4. Check before using the picture

1. **Warnings** on stderr: bodies with no look (rendered neutral grey) and bodies on
   SolidCraft's placeholder `Default` material (1.29 g/cm³, mass not real). Fix them in
   SolidCraft or `--looks`; don't ship a render with placeholder grey unintentionally.
2. **`materials.json`** in the output: per body and look group, the physical material,
   density, volume, mass, the SolidCraft look and the LuxCore material used (`from: look` or
   `override`). Compare mass with a hand calculation (e.g. leadscrew Ø8 x 310 mm steel:
   π·4²·310 = 15 582 mm³ x 7.85 = 122.3 g; the tool reported 122.27 g).
3. **Look at the PNG**: right parts in the right finish, face overrides on the right faces.

## 5. When a PBR look is not enough: `render.json`

```json
{"bodies":     {"LeadScrew": {"type": "metal2", "n": "2.87 2.95 2.65", "k": "3.12 2.93 2.81",
                              "uroughness": "0.04", "vroughness": "0.04"}},
 "materials":  {"EN AW-6082-T6": {"type": "metal2", "preset": "aluminium",
                                  "uroughness": "0.2", "vroughness": "0.2"}},
 "appearances": {"Smoked glass": {"type": "glass", "kr": "1 1 1", "kt": "0.35 0.35 0.35",
                                  "interiorior": "1.5"}}}
```
Precedence: body > physical material > appearance name > converted look. Values are LuxCore
material properties as strings (`luxcore-scene-format`). A body override covers the whole
body, face looks included. Keep `render.json` next to the part; it is render-only.

## How looks are converted

| SolidCraft | LuxCore |
|---|---|
| `color` sRGB hex | `disney.basecolor`, linearized |
| `pbr.metallic` | `disney.metallic` |
| `pbr.roughness` | `disney.roughness` (both perceptual, squared internally) |
| `pbr.dielectric_ior` | `disney.specular = ((ior-1)/(ior+1))² / 0.08` |
| no `pbr` (scalar look) | `disney`, metallic 0, roughness 0.5 |
| `opacity` < 1 | `glass` with `kt` = colour (approximation: SolidCraft alpha is not physical glass; prefer an override) |
| no look | grey `#a0a0a0` placeholder + warning |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `solidcraft-cli run ... failed: error: step N (...)` | the source (or `--looks`) has a bad step; the message is SolidCraft's. Run the script alone with `solidcraft-cli run` |
| File not found inside the script | relative `doc.open` path: run from the part folder or `--cwd` |
| Whole body took a face colour | `appearance.assign` had `bodies` as well as `faces` |
| Body grey | no look on face/body/component/material: add one, or an override |
| Metal looks dull | roughness too high, or the studio lighting shows little to reflect: try `--env-map` |
| Wrong body coloured | names are SolidCraft body names (`inspect.measure` lists them; see `materials.json`) |
| Slow on big assemblies | the per-face normal pass is pure Python: `--quality standard`, or `--bodies` |
| `warning: no mesh exported for body X` | the body has no solid mesh (e.g. a sketch-only or empty body); it is skipped |

Checked 2026-11-11 with solidcraft-cli 0.27.1 and the luxcore-cli-2026-11-11 build: script
with material look, body and face overrides; `.sc`; STEP + `--looks`; the 3dassets NEMA17
assembly with a `metal2` override; a failing script reports SolidCraft's error.
