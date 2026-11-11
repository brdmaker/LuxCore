---
name: luxcore-scene-format
description: Use when writing or editing LuxCore SDL text files for luxcoreconsole - the render config (.cfg) and scene (.scn) - cameras, meshes (PLY), objects and transforms, materials (matte, glossy2, metal2, glass, disney...), textures and image maps, lights (sky, sun, HDR environment, area emission, spot...), volumes; includes a minimal working template and the format traps. Full source-verified property tables are in reference.md.
---

# Writing LuxCore scenes (.cfg + .scn)

`reference.md` in this folder is the complete, source-verified property reference (every
default, every type). Read the section you need; this page is the template and the traps.

## Minimal working pair

`render.cfg`
```
scene.file = scene.scn
renderengine.type = PATHCPU
film.width = 800
film.height = 600
batch.haltspp = 128
batch.halttime = 300
film.imagepipelines.0.0.type = TONEMAP_AUTOLINEAR
film.imagepipelines.0.1.type = GAMMA_CORRECTION
film.imagepipelines.0.1.value = 2.2
film.outputs.0.type = RGB_IMAGEPIPELINE
film.outputs.0.index = 0
film.outputs.0.filename = render.png
```

`scene.scn`
```
scene.camera.lookat.orig = 4 -6 3
scene.camera.lookat.target = 0 0 0.5
scene.camera.up = 0 0 1
scene.camera.fieldofview = 35

scene.textures.checks.type = checkerboard2d
scene.textures.checks.texture1 = 0.7 0.7 0.7
scene.textures.checks.texture2 = 0.2 0.2 0.2
scene.textures.checks.mapping.uvscale = 8 8

scene.materials.floor.type = matte
scene.materials.floor.kd = checks
scene.materials.red.type = glossy2
scene.materials.red.kd = 0.6 0.05 0.04
scene.materials.red.ks = 0.04 0.04 0.04
scene.materials.red.uroughness = 0.05
scene.materials.red.vroughness = 0.05
scene.materials.lamp.type = matte
scene.materials.lamp.kd = 0 0 0
scene.materials.lamp.emission = 1 1 1
scene.materials.lamp.emission.gain = 20 20 20

scene.shapes.floor.type = inlinedmesh
scene.shapes.floor.vertices = -5 -5 0  5 -5 0  5 5 0  -5 5 0
scene.shapes.floor.faces = 0 1 2  0 2 3
scene.shapes.floor.uvs = 0 0  1 0  1 1  0 1
scene.objects.floor.shape = floor
scene.objects.floor.material = floor

scene.shapes.part.type = mesh
scene.shapes.part.ply = part.ply
scene.objects.part.shape = part
scene.objects.part.material = red

# area light: a quad whose triangle normal points down (-Z) towards the scene
scene.shapes.lamp.type = inlinedmesh
scene.shapes.lamp.vertices = -1 -1 4  -1 1 4  1 1 4  1 -1 4
scene.shapes.lamp.faces = 0 1 2  0 2 3
scene.objects.lamp.shape = lamp
scene.objects.lamp.material = lamp

scene.lights.sky.type = sky2
scene.lights.sky.dir = 0.3 -0.4 0.8
scene.lights.sky.gain = 0.5 0.5 0.5
```
Run: `luxcoreconsole -d <folder> render.cfg`.

## Syntax rules
- `name = values`, one per line, `#` comments on their own line only. Last value wins.
- Strings with spaces in quotes. **Booleans `1`/`0`** (`true` reads as false).
- Colours are linear RGB triples; any texture slot also takes a float, a triple, or a texture name.
- **Define before use**: textures, materials, shapes are processed in first-definition order.
  A material naming a texture defined later fails with `Syntax error in texture name`.
- Paths inside the `.scn` resolve against the current directory and the `.cfg` folder,
  **not** the `.scn` folder. Keep cfg, scn and meshes in one folder and run with `-d` there.

## Geometry
- **Z is up.** Camera up is `scene.camera.up` (not `lookat.up`).
- `fieldofview` (degrees, perspective only) spans the **longer** image side; the shorter
  side gets tan(fov/2)/aspect. To frame a bounding sphere of radius r in a landscape image:
  distance = r / sin(atan(tan(fov/2) * height/width)) (x1.05 margin).
- Orthographic: `scene.camera.type = orthographic` and `scene.camera.screenwindow = -w w -h h`
  (half-extents in scene units).
- Depth of field: `lensradius`, `focaldistance` or `autofocus.enable = 1`.
- **Meshes load only from `.ply` and `.bpy`.** STL/OBJ must be converted
  (`luxcore-render-cad-part/scripts/luxcore_part_scene.py` does STL → PLY). PLY UVs are
  `s t`; normals `nx ny nz` (without them, faces are flat-shaded).
- Small geometry inline: `type = inlinedmesh`, `.vertices`, `.faces`, optional `.uvs`, `.normals`.
- **Matrices: 16 numbers, column-major, translation in values 13-15.** Move by (10,0,5):
  `1 0 0 0  0 1 0 0  0 0 1 0  10 0 5 1`. On a shape it is baked into the mesh; on an object
  it makes an instance (cheap copies: many objects, one shape).
- Modifiers are shapes with `.source`: `subdiv`, `displacement`, `bevel`, `simplify`,
  `pointiness`, `harlequin` (random colour per triangle, debugging).
- Very large or tiny scenes: set `scene.epsilon.min/max` (absolute distances; defaults
  1e-5 / 0.1). For mm-scale CAD of 10-1000 mm the defaults are fine.

## Materials (most used)

| Look | Definition |
|---|---|
| Diffuse paint, paper, clay | `type = matte`, `kd = 0.7 0.7 0.7` |
| Plastic | `type = glossy2`, `kd = <colour>`, `ks = 0.04 0.04 0.04`, `uroughness = vroughness = 0.05..0.2` |
| Metal | `type = metal2`, `preset = aluminium|silver|gold|copper` **or** `n = ...`, `k = ...`; `uroughness/vroughness` 0.02 (polished) .. 0.3 (bead-blasted); unequal = brushed |
| Glass | `type = glass`, `kr = 1 1 1`, `kt = 1 1 1`, `interiorior = 1.5` (rough: `roughglass`) |
| PBR | `type = disney`, `basecolor`, `metallic`, `roughness`, `specular`, `clearcoat`... |
| Coated (car paint, lacquer) | `type = glossycoating`, `base = <material>`, `ks`, `uroughness` / or `carpaint` with `preset` |
| Rubber | `type = roughmatte`, `kd = 0.03 0.03 0.03`, `sigma = 0.6` |
| Blend two | `type = mix`, `material1`, `material2`, `amount` (texture ok) |
| Area light | any material + `emission = r g b`, `emission.gain`, optional `emission.power` (W) + `emission.efficiency` (lm/W), `emission.id` (light group) |

Only `glossy2`/`metal2` exist (no `glossy`/`metal`). Steel has no preset: use
`n = 2.87 2.95 2.65`, `k = 3.12 2.93 2.81`. Brass: `n = 0.444 0.527 1.094`,
`k = 3.695 2.765 1.829`. Common to all: `bumptex`, `normaltex`, `transparency`,
`shadowcatcher.enable`, `visibility.indirect.*`, `volume.interior/exterior`.

## Textures
- `imagemap`: `file`, `gamma` (**default 2.2, also for .exr/.hdr: set `gamma = 1` for linear
  data, normal maps and HDR**), `mapping.uvscale`, `wrap` (`repeat`/`black`/`white`/`clamp`),
  `channel`.
- Procedural: `checkerboard2d/3d`, `fbm`, `wrinkled`, `marble`, `brick`, `blender_*`.
- Maths: `scale`, `add`, `mix` (`amount`), `clamp`, `remap`, `hsv`, `brightcontrast`.
- Without UVs (most CAD meshes) use `triplanar` or a 3D mapping
  (`mapping.type = globalmapping3d` / `localmapping3d` + `mapping.transformation`).

## Lights

| Light | Definition |
|---|---|
| Daylight | `type = sky2`, `dir` (towards the sun), `turbidity` 2-6; add `type = sun` with the same `dir` for hard shadows |
| HDR environment | `type = infinite`, `file = env.exr`, **`gamma = 1`**, `gain`, `transformation` to rotate |
| Uniform environment | `type = constantinfinite`, `color`, `gain` |
| Softbox / panel | emissive mesh (material `emission`); emits only on the side its triangle normal points to |
| Spot | `type = spot`, `position`, `target`, `coneangle`, `conedeltaangle`, `color`, `power` (W) |
| Point / sphere | `type = point` / `sphere` (`radius`), `position`, `color`, `power` |
| Parallel sun-like | `type = distant` (`direction` = travel direction, `theta` spread) / `sharpdistant` |
| IES profile | `type = mappoint` with `iesfile` |

The default light type is `sky2`; there is no `trianglearea` or `hdr` type. Give lights an
`id` and use radiance scales (`luxcore-cli-render`) to rebalance groups after the fact.

## Volumes
`scene.volumes.fog.type = homogeneous` (**always set `type`**: the default string is invalid),
`absorption`, `scattering`, `asymmetry`; attach with `scene.materials.X.volume.interior = fog`
or `scene.world.volume.default = fog`. `clear` volumes give coloured glass absorption.

## Checking a scene quickly
- Low-res preview: `luxcoreconsole -d dir -w 320 -e 240 -D batch.haltspp 8 render.cfg`.
- See what was parsed: `-D debug.scene.parse.print 1` (scene) / `-D debug.renderconfig.parse.print 1`.
- Normalize via export: FILESAVER TXT (see `luxcore-cli-render`).
- Example scenes for every feature: `scenes/` in the LuxCore repo (`luxball` materials and
  lights, `cornell` engines, `simple` AOVs and light groups, `bump`, `strands`, `media`...).
  Their paths are repo-root-relative: run them from the repo root.
