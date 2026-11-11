---
name: luxcore-cli-render
description: Use when running renders with luxcoreconsole (the LuxCore CLI) - command-line flags, overriding properties with -D, choosing a render engine and sampler, halt conditions so the render ends, film outputs and AOVs, denoising, resume files, scene export with FILESAVER, reading the log, and fixing common errors.
---

# Rendering with luxcoreconsole

Get the binary first (`luxcore-cli-start`). The full property reference is
`../luxcore-scene-format/reference.md`; this skill is the working subset plus the traps.

## Command line

```
luxcoreconsole [options] <file.cfg | file.lxs | file.bcf | file.rsm>
```

| Option | Effect |
|---|---|
| `-d <dir>` | `chdir` to `<dir>` first. **Use it**: relative paths in the config, the scene and the outputs then resolve inside `<dir>`. |
| `-D <name> <value>` | set one render-config property (applied on top of the file) |
| `-w <n>` / `-e <n>` | `film.width` / `film.height` |
| `-f <scene.scn>` | `scene.file` |
| `-o <file>` | config file (same as the positional argument) |
| `-c` | drop unused meshes, image maps, materials, textures before rendering |
| `-s` | print per-device stats (OpenCL/CUDA) each second |
| `-k` | (re)compile the OpenCL kernel cache for the OCL engines, then exit |
| `-h` | usage |

Input types: `.cfg` (LuxCore SDL config, loads `scene.file`), `.lxs` (old LuxRender scene),
`.bcf` (binary config + scene from FILESAVER BIN), `.rsm` (resume file). Anything else exits 1.

**`-D` traps (verified):**
- One value only. `-D batch.haltspp 64` works; colours, points, matrices and the 2-value
  `batch.haltspp A B` can't be passed.
- It reaches render-config properties only. A `scene.*` value written in the `.scn`
  (camera, materials, lights) is **not** changed by `-D`; edit the `.scn` (or a copy) instead.
- Booleans are `1`/`0`; `true` reads as false.

Exit code: 0 after `Done.`, 1 on any error (`RUNTIME ERROR: ...`). Everything is logged to
**stderr**: redirect with `2>&1` and filter, e.g.
`luxcoreconsole -d out render.cfg 2>&1 | grep -E "Samples|ERROR|Done"`.

Progress, once a second:
`[Elapsed time: 59/300sec][Samples 128/128][Convergence 100%][Avg. samples/sec 1.04M on 7.3K tris]`.

## Every batch render needs a halt condition

**With no halt condition luxcoreconsole renders forever.** Set at least one (they are OR-ed):

| Property | Meaning |
|---|---|
| `batch.haltspp = 256` | stop at 256 samples per pixel (best for reproducible quality) |
| `batch.halttime = 600` | stop after 600 s (safety net, always add one) |
| `batch.haltnoisethreshold = 0.02` | stop when the noise estimate is below the threshold (legacy name `batch.haltthreshold`) |

Rough CPU budget (4 threads, PATHCPU, simple scene): ~1 M samples/s, so 800x600 @ 128 spp
≈ 60 s. Time scales with pixels x spp; glossy metals and small lights need more spp.
For previews use `-w 400 -e 300 -D batch.haltspp 16`.

## Engines and samplers

| `renderengine.type` | Use | `sampler.type` |
|---|---|---|
| `PATHCPU` | default; general path tracing on CPU | `SOBOL` (default), `RANDOM`, `METROPOLIS` |
| `BIDIRCPU` | caustics, light through small openings | SOBOL/RANDOM/METROPOLIS |
| `BIDIRVMCPU` | heavy caustics (vertex merging) | SOBOL/RANDOM/METROPOLIS |
| `LIGHTCPU` | light tracing only | SOBOL/RANDOM/METROPOLIS |
| `TILEPATHCPU` | tile renders, AA via `tilepath.sampling.aa.size` | **must set `TILEPATHSAMPLER`** |
| `BAKECPU` | bake light maps / textures (`bake.maps.*`) | SOBOL/RANDOM/METROPOLIS |
| `PATHOCL`, `TILEPATHOCL`, `RTPATHOCL` | GPU (OpenCL/CUDA) | PATHOCL: SOBOL...; TILE/RT: **`TILEPATHSAMPLER`** |
| `RTPATHCPU` | interactive, for GUIs; not for batch | `RTPATHCPUSAMPLER` |
| `FILESAVER` | export the scene instead of rendering | n/a |

- The OCL engines **do not fall back to CPU**: without a GPU they exit with
  `RUNTIME ERROR: No hardware device selected or available`. In containers use `PATHCPU`.
  CPU OpenCL (PoCL) needs `-D opencl.cpu.use 1`. First OCL run compiles kernels (minutes);
  `luxcoreconsole -k` pre-fills the cache (`$XDG_CACHE_HOME/luxcorerender.org`, else
  `~/.config/luxcorerender.org`).
- Wrong sampler → `RUNTIME ERROR: TILEPATHCPU render engine can use only TILEPATHSAMPLER sampler`.
- Threads: `native.threads.count` (default: all hardware threads).
- Path depth: `path.pathdepth.total` (6), `.diffuse` (4), `.glossy` (4), `.specular` (6).
  Glass and stacked reflections need higher specular/total.
- Fireflies: `path.clamping.variance.maxvalue = 10` (0 = off).
- Reproducible noise pattern: `renderengine.seed = 1`.

## Film outputs (what gets written)

```
film.width = 1200
film.height = 900                       # always set both: height defaults to width
film.outputs.0.type = RGB_IMAGEPIPELINE  # display-ready image through pipeline .index
film.outputs.0.index = 0
film.outputs.0.filename = render.png
film.outputs.1.type = RGBA_IMAGEPIPELINE # same with alpha (background transparent)
film.outputs.1.filename = render_alpha.png
film.outputs.2.type = DEPTH              # HDR-only types need .exr/.hdr
film.outputs.2.filename = depth.exr
```
- Filenames are relative to the current directory (so use `-d`), or absolute.
  `-D film.outputs.0.filename /abs/path.png` works.
- Defining any `film.outputs.*` replaces the default (`image.png`).
- HDR only (`.exr`/`.hdr`): `RGB`, `RGBA`, `DEPTH`, `POSITION`, `GEOMETRY_NORMAL`,
  `SHADING_NORMAL`, `DIRECT_*`, `INDIRECT_*`, `EMISSION`, `CAUSTIC`.
  Non-HDR only: `MATERIAL_ID`, `OBJECT_ID`. Any: `ALPHA`, `ALBEDO`, `AVG_SHADING_NORMAL`,
  `OBJECT_ID_MASK`/`BY_OBJECT_ID` (+ `.id`), `RADIANCE_GROUP` (+ `.id` light group),
  `SAMPLECOUNT`, `CONVERGENCE`, `NOISE`, `UV`, `IRRADIANCE`.

### Image pipeline (tone mapping, denoise, effects)
```
film.imagepipelines.0.0.type = INTEL_OIDN          # optional denoiser, first
film.imagepipelines.0.1.type = TONEMAP_AUTOLINEAR  # or TONEMAP_LINEAR + .scale = 1.0
film.imagepipelines.0.2.type = GAMMA_CORRECTION
film.imagepipelines.0.2.value = 2.2
```
- No pipeline given → `TONEMAP_AUTOLINEAR` + gamma 2.2.
- `TONEMAP_AUTOLINEAR` exposes for the average: a scene that is mostly white floor comes out
  mid-grey. Use `TONEMAP_LINEAR` with a fixed `.scale` for a consistent look across renders.
- Several pipelines at once (`film.imagepipelines.1.*` + an output with `.index = 1`) let one
  render produce e.g. raw and denoised, or several exposures, in one go.
- `INTEL_OIDN` (bundled) cleans 64-128 spp renders well; add `ALBEDO` and
  `AVG_SHADING_NORMAL` outputs so it gets the feature channels. It runs on every film update,
  which costs ~1-3 s each. `BCD_DENOISER` also exists; `OPTIX_DENOISER` needs CUDA.
- Others: `TONEMAP_REINHARD02`, `TONEMAP_LUXLINEAR` (sensitivity/exposure/fstop),
  `WHITE_BALANCE` (.temperature), `BLOOM`, `VIGNETTING`, `CAMERA_RESPONSE_FUNC`,
  `BACKGROUND_IMG`, `COLOR_LUT`, `MIST`, `OUTPUT_SWITCHER`, `TONEMAP_OPENCOLORIO`.
- Per-light-group brightness without re-rendering geometry:
  `film.imagepipelines.0.radiancescales.<id>.globalscale = 0.5` (group id from
  `scene.lights.X.id` / `scene.materials.X.emission.id`).

## Resume, periodic save, export

- Save images while rendering: `periodicsave.film.outputs.period = 30` (seconds). Useful with
  a long `batch.halttime`: you always have the latest image on disk.
- **Known issue in this build (checked 2026-11-11 on the luxcore-cli-2026-11-11 package):
  binary serialization is broken.** `periodicsave.resumerendering.period` writes a
  `rendering.rsm`, but loading it fails with `ERROR: class version
  St10unique_ptrIN3slg12RenderConfig...`; `FILESAVER` with `filesaver.format = BIN` writes a
  58-byte `.bcf` that fails the same way. Don't rely on resume or `.bcf`: render to a
  halt condition in one go, and re-check this on newer builds.
- Export instead of render (works): `-D renderengine.type FILESAVER -D filesaver.format TXT
  -D filesaver.directory exported` (the directory **must exist**) writes `render.cfg`,
  `scene.scn`, every mesh as `mesh-NNNNN.ply` and image maps. The result renders as is
  (`luxcoreconsole -d exported render.cfg`): handy to normalize, inspect or ship a scene.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Never finishes | no halt condition; add `batch.haltspp` and `batch.halttime` |
| `Unable to open properties file` | wrong config path (relative to cwd after `-d`) |
| Mesh/texture not found, or `Unknown file extension while loading a mesh` | paths inside `.scn` resolve against the cwd and the `.cfg` folder only (not the `.scn` folder); meshes must be `.ply`/`.bpy` (convert STL/OBJ first) |
| `Syntax error in texture name` | material refers to a texture defined later or not at all; define it first |
| Square image | only `film.width` set |
| `ERROR: class version St10unique_ptr...RenderConfig...` | loading a `.rsm`/`.bcf`: binary serialization is broken in this build (see above) |
| All black | lights face away (area emission is one-sided, along the triangle normal), `gain` 0, or camera inside geometry |
| HDR environment too dark / too contrasty | image maps get gamma 2.2 removed by default, `.exr`/`.hdr` too: set `scene.lights.X.gamma = 1` |
| Image grey / dull | auto exposure on a bright background: use `TONEMAP_LINEAR` with a scale |
| Fireflies / speckles on metal | more spp, `path.clamping.variance.maxvalue`, larger lights, or `INTEL_OIDN` |
| `No hardware device selected or available` | OCL engine without GPU; use `PATHCPU` |
| `Unknown volume type` | volume without explicit `type` (`clear`, `homogeneous`, `heterogeneous`) |
| Stray `normal.png`/`denoised.png` in the repo | sample scenes write outputs to cwd; run with `-d` and an output dir |
