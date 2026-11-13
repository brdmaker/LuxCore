# LuxCore SDL reference (.cfg / .scn) for `luxcoreconsole`

Source-verified against the LuxCore tree (`src/`, `samples/`, `scenes/`). Every section names the
file it was read from. "Default" = the value used when the property is absent.

---

## 0. Text property syntax (both .cfg and .scn)

Source: `src/luxrays/utils/properties.cpp` (`Properties::SetFromStream`, `Property::FromString`, `Property::Get<Matrix4x4>`), `include/luxrays/utils/strutils.h` (`FromString`).

- One property per line: `name = v1 v2 v3 ...`. Values are split on spaces/tabs.
- Lines whose first non-blank char is `#` are comments; blank lines ignored. No inline comments.
- Strings may be quoted with `"` or `'` (needed for values containing spaces). `{[ ... ]}` is a base64 blob (e.g. `.iesblob`).
- Setting the same name twice: last value wins (position in the list is the first definition's).
- **Booleans: use `1` / `0`.** Strings are converted with `istringstream >> bool` (no `boolalpha`), so `true`/`false` read as **false**. All shipped scenes use `1`/`0`.
- Numbers are read with the C locale (`.` decimal separator).
- **Matrices (16 numbers) are column-major**: values 0-3 are column 0, ..., values 12-14 are the translation (`Matrix4x4(v0,v4,v8,v12, v1,v5,v9,v13, ...)`). Example translation by (-6,0,0): `1 0 0 0  0 1 0 0  0 0 1 0  -6 0 0 1`.
- Colors are 3 floats (RGB). A texture-valued property accepts: a texture name, a single float, 3 floats, or a color-space-prefixed constant (see §3.5).

---

## 1. Render configuration (.cfg)

Defaults are from `RenderConfig::ToProperties` (`src/slg/renderconfig.cpp`) plus the per-subsystem `GetDefaultProps()`.

### 1.1 General

| Property | Default | Notes |
|---|---|---|
| `scene.file` | `scenes/luxball/luxball.scn` | Resolved through the file name resolver (§5.3). |
| `scene.epsilon.min` / `scene.epsilon.max` | `1e-5` / `1e-1` | `DEFAULT_EPSILON_MIN/MAX` (`include/luxrays/core/epsilon_types.cl`); read in `RenderEngine::Start`. |
| `scene.images.resizepolicy.type` | `NONE` | `NONE`, `FIXED`, `MINMEM`, `MIPMAPMEM`; plus `.scale` (1.0), `.minsize` (64). `src/slg/imagemap/resizepolicies/resizepolicy.cpp` |
| `accelerator.type` | `AUTO` | `AUTO`, `BVH`, `MBVH`, `EMBREE`, `OPTIX` (`src/luxrays/core/accelerator.cpp`) |
| `accelerator.instances.enable` / `accelerator.motionblur.enable` | `1` / `1` | |
| `accelerator.bvh.builder.type` | `EMBREE_BINNED_SAH` | also `accelerator.bvh.treetype` 4, `.costsamples` 0, `.isectcost` 80, `.travcost` 10, `.emptybonus` 0.5 |
| `context.verbose` | `1` | all `context.*` and `accelerator.*` props are forwarded to the LuxRays context (`renderengine.cpp`) |
| `renderengine.seed` | (random) | if set, seeds the engine (min 1) |
| `resumerendering.filesafe` | `1` | safe-save (write temp then rename) for `.rsm` |
| `debug.renderconfig.parse.print` / `debug.scene.parse.print` | `0` / `0` | |
| `screen.refresh.interval` | `100` | GUI only; luxcoreconsole forces it to 2500 (non-FILESAVER) |

Deprecated but accepted: `image.width`/`image.height` (→ film.width/height), `image.filename` (adds an RGB(A)_IMAGEPIPELINE output), `film.alphachannel.enable`, `film.gamma` (warns, no effect).

### 1.2 `renderengine.type`

Registry: `src/slg/engines/renderengine.cpp` (`OBJECTSTATICREGISTRY_REGISTER`), tags in `include/slg/engines/*/*.h`. Default `PATHCPU`.

| Value | Device | Required `sampler.type` | Notes |
|---|---|---|---|
| `PATHCPU` | CPU | `RANDOM`, `SOBOL` (default), `METROPOLIS` | general path tracer |
| `LIGHTCPU` | CPU | RANDOM/SOBOL/METROPOLIS | light tracing |
| `BIDIRCPU` | CPU | RANDOM/SOBOL/METROPOLIS | bidirectional |
| `BIDIRVMCPU` | CPU | RANDOM/SOBOL/METROPOLIS | bidir + vertex merging |
| `TILEPATHCPU` | CPU | **`TILEPATHSAMPLER` (must be set explicitly)** | default SOBOL makes it throw "can use only TILEPATHSAMPLER sampler" |
| `RTPATHCPU` | CPU | **`RTPATHCPUSAMPLER` (explicit)** | real-time/interactive; meant for GUIs |
| `BAKECPU` | CPU | RANDOM/SOBOL/METROPOLIS | texture/lightmap baking (`bake.*`, `bake.maps.*`) |
| `PATHOCL` | OpenCL/CUDA (+ native CPU threads) | RANDOM/SOBOL/METROPOLIS | not registered in OpenCL-less builds |
| `TILEPATHOCL` | OpenCL/CUDA | **`TILEPATHSAMPLER` (explicit)** | |
| `RTPATHOCL` | OpenCL/CUDA | **`TILEPATHSAMPLER` (explicit)** (subclass of TILEPATHOCL) | real-time |
| `FILESAVER` | none | n/a | exports the scene instead of rendering (§1.10) |

OpenCL-less builds (`LUXRAYS_DISABLE_OPENCL`, which also disables CUDA) throw `"<type> render engine is not supported by OpenCL-less version of the binaries..."` (`RenderConfig::AllocRenderEngine`).

### 1.3 Sampler (`sampler.*`)

Source: `src/slg/samplers/{sampler,sobol,random,metropolis}.cpp`.

| Property | Default | Applies to |
|---|---|---|
| `sampler.type` | `SOBOL` | `RANDOM`, `SOBOL`, `METROPOLIS`, `TILEPATHSAMPLER`, `RTPATHCPUSAMPLER` |
| `sampler.imagesamples.enable` | `1` | all |
| `sampler.sobol.adaptive.strength` | `0.95` (clamped 0..0.95) | SOBOL; >0 adds the NOISE channel (adaptive sampling uses `film.noiseestimation.*`) |
| `sampler.sobol.adaptive.userimportanceweight` | `0.75` | SOBOL |
| `sampler.sobol.bucketsize` / `.tilesize` / `.supersampling` / `.overlapping` | `16` / `16` / `1` / `1` | SOBOL |
| `sampler.random.*` | same names and defaults as sobol | RANDOM |
| `sampler.metropolis.largesteprate` | `0.4` | METROPOLIS |
| `sampler.metropolis.maxconsecutivereject` | `512` | METROPOLIS |
| `sampler.metropolis.imagemutationrate` | `0.1` | METROPOLIS |
| `sampler.metropolis.addonlycaustics` | `0` | METROPOLIS |

### 1.4 Path / light tracing (`path.*`, `light.*`)

Source: `src/slg/engines/pathtracer.cpp` (`PathTracer::GetDefaultProps/ParseOptions`) used by PATHCPU, PATHOCL, TILEPATH*, LIGHTCPU, BAKECPU; RT engines override some defaults.

| Property | Default | Notes |
|---|---|---|
| `path.pathdepth.total` | `6` (RT engines: 5) | |
| `path.pathdepth.diffuse` / `.glossy` / `.specular` | `4` / `4` / `6` (RT: 3/3/3) | |
| `path.maxdepth` | — | legacy: if set and **none** of `path.pathdepth.*` is set, all four depths = this value |
| `path.russianroulette.depth` / `.cap` | `3` / `0.5` | |
| `path.clamping.variance.maxvalue` | `0` (off) | legacy alias `path.clamping.radiance.maxvalue` |
| `path.forceblackbackground.enable` | `0` | |
| `path.hybridbackforward.enable` | `0` | adds light tracing for caustics; `.partition` 0.8, `.glossinessthreshold` 0.05 |
| `path.albedospecular.type` | `REFLECT_TRANSMIT` | also `NO_REFLECT_TRANSMIT`, `ONLY_REFLECT`, `ONLY_TRANSMIT` (`src/slg/bsdf/bsdf.cpp`); `.glossinessthreshold` 0.05 |
| `path.photongi.*` | caches off | `src/slg/engines/caches/photongi/pgicproperties.cpp`: `.indirect.enabled` 0, `.caustic.enabled` 0, `.photon.maxcount` 1e8, `.photon.maxdepth` 4, `.sampler.type` METROPOLIS, `.persistent.file` "", `.debug.type` none, etc. |

BIDIRCPU (`src/slg/engines/bidircpu/bidircpu.cpp`): `path.maxdepth` 5, `light.maxdepth` 5, `path.aovs.warmup.spp` 0, `path.russianroulette.depth` 3 / `.cap` 0.5, clamping and albedospecular as above.
BIDIRVMCPU adds `bidirvm.lightpath.count` 16384, `bidirvm.startradius.scale` 0.003, `bidirvm.alpha` 0.95.
TILEPATH*: `tilepath.sampling.aa.size` 3 (RTPATHOCL: 1), `tilepathocl.devices.maxtiles` 16 (RTPATHOCL: 1); tiles (`src/slg/engines/tilerepository.cpp`): `tile.size` 32 (or `tile.size.x/.y`, min 8), `tile.multipass.enable` 1, `tile.multipass.convergencetest.threshold` 6/256 (or `.threshold256` 6), `.threshold.reduction` 0, `.warmup.count` 32.
RTPATHCPU: `rtpathcpu.zoomphase.size` 4, `.weight` 0.1. RTPATHOCL: `rtpath.resolutionreduction.preview` 4, `.preview.step` 8, `rtpath.resolutionreduction` 4.
BAKECPU (`bakecpu.cpp`): `bake.minmapautosize` 32, `bake.maxmapautosize` 1024, `bake.powerof2autosize.enable` 1, `bake.skipexistingmapfiles` 0, `bake.margin` 0, `bake.marginsamplesthreshold` 0, plus `bake.maps.*`.

### 1.5 Light strategy (`lightstrategy.*`)

Source: `src/slg/lights/strategies/*.cpp`. One strategy is used for emit, illuminate and infinite sampling (`LightSourceDefinitions::SetLightStrategy`).

| Property | Default |
|---|---|
| `lightstrategy.type` | `LOG_POWER`; also `UNIFORM`, `POWER`, `DLS_CACHE` |
| DLS_CACHE only: `lightstrategy.entry.radius` 0 (auto), `.entry.normalangle` 25, `.entry.maxpasses` 1024, `.entry.convergencethreshold` 0.05, `.entry.warmupsamples` 24, `lightstrategy.targetcachehitratio` 0.995, `lightstrategy.maxdepth` 4, `lightstrategy.maxsamplescount` 10000000, `lightstrategy.persistent.file` "", `lightstrategy.persistent.safesave` 1 | |

### 1.6 Halt conditions (`batch.*`)

Source: `src/slg/film/filmparse.cpp` (`Film::Parse`), `src/slg/film/film.cpp` (`Film::RunTests`), `src/slg/film/filmproperties.cpp`.

| Property | Default | Meaning |
|---|---|---|
| `batch.halttime` | `0` (off) | seconds (double); stop when film total time > value |
| `batch.haltspp` | `0` (off) | 1 value: stop when average samples/pixel of the rendered region > N. 2 values `A B`: A = eye-path (pixel-normalized) SPP, B = light-path (screen-normalized) SPP; each 0 means "ignore" |
| `batch.haltnoisethreshold` | `-1` (off) | legacy alias `batch.haltthreshold`. Convergence test on image pipeline output; stops when the test reports all pixels converged |
| `batch.haltnoisethreshold.warmup` | `64` | alias `batch.haltthreshold.warmup` |
| `batch.haltnoisethreshold.step` | `64` | alias `batch.haltthreshold.step` |
| `batch.haltnoisethreshold.filter.enable` | `1` | alias `batch.haltthreshold.filter.enable` |
| `batch.haltnoisethreshold.stoprendering.enable` | `1` | alias `...haltthreshold.stoprendering.enable` |
| `batch.haltnoisethreshold.index` | `0` | image pipeline used for the test (falls back to 0 if out of range) |

How it works: `Film::RunTests()` runs on every film update; the first condition met (time, then SPP, then noise) sets convergence = 1, the render threads finish and `HasDone()` becomes true. Conditions are OR-ed. **With no halt condition, a `luxcoreconsole` batch render never ends** (the loop waits on `HasDone()`); TILEPATH engines also finish when all tiles converge.

Adaptive sampling / noise estimation (`film.noiseestimation.*`, parsed when any such key is present): `.warmup` 32, `.step` 32, `.filter.scale` 4, `.index` 0.

### 1.7 CPU threads and OpenCL/CUDA devices

Sources: `src/slg/engines/cpurenderengine.cpp`, `src/slg/engines/oclrenderengine.cpp`, `src/slg/engines/pathocl/pathocl.cpp`, `src/slg/engines/pathoclbase/pathoclbase.cpp`, `src/luxrays/core/context.cpp`.

| Property | Default | Notes |
|---|---|---|
| `native.threads.count` | hardware thread count | CPU engines (min 1) |
| `opencl.cpu.use` | `0` | use OpenCL CPU devices (needed for e.g. PoCL) |
| `opencl.gpu.use` | `1` | use OpenCL and CUDA GPUs |
| `opencl.devices.select` | `""` | string of `0`/`1`, one char per device in the OpenCL+CUDA device list; length must equal the device count or it throws "Hardware device selection string has the wrong length". Overrides cpu/gpu.use |
| `cuda.optix.devices.select` | `""` | one char per CUDA device: `1` use OptiX, `0` don't, `A` auto |
| `opencl.native.threads.count` | hardware thread count | extra CPU threads added next to the GPUs (PATHOCL) |
| `opencl.cpu.workgroup.size` | `0` (macOS `1`) | 0 = driver choice |
| `opencl.gpu.workgroup.size` | `32` | |
| `opencl.task.count` | `AUTO` | PATHOCL |
| `pathocl.pixelatomics.enable` | `1` | |
| `opencl.outofcore.enable` / `opencl.outofcore.film.enable` | `0` / `0` | |
| `opencl.memory.maxpagesize` | 512 MB | only if defined |
| `opencl.kernel.writetofile` | `0` | debug |
| `opencl.platform.index` | `-1` | in the defaults, but the Context reads **`context.opencl.platform.index`** (-1 = all platforms). Set the `context.` name to restrict the platform |
| `film.hw.enable` | `1` | legacy `film.opencl.enable`; image pipeline on GPU when a hardware device exists, else CPU |
| `film.hw.device` | `-1` | legacy `film.opencl.device` |

If no device is selected/available, the OCL engine throws `"No hardware device selected or available"` (the check happens **before** native threads are added). If at least one CUDA device is found and no selection string is given, only CUDA devices are used.

### 1.8 Film size and pixel filter

Sources: `src/slg/film/filmproperties.cpp`, `src/slg/film/filters/*.cpp`.

| Property | Default | Notes |
|---|---|---|
| `film.width` | `640` | |
| `film.height` | `480` in ToProperties, **but** `Film::GetFilmSize` uses `film.width` as the fallback: if only `film.width` is set, the film is square. Always set both |
| `film.subregion` | full frame | 4 ints `xmin xmax ymin ymax` |
| `film.safesave` | `1` | safe-save for `.flm` |
| `film.outputs.safesave` | `1` | safe-save for image outputs |
| `film.filter.type` | `BLACKMANHARRIS` | `NONE`, `BOX`, `GAUSSIAN`, `MITCHELL`, `MITCHELL_SS`, `BLACKMANHARRIS`, `SINC`, `CATMULLROM` |
| `film.filter.width` | `2.0` | or `film.filter.xwidth` / `film.filter.ywidth` |
| `film.filter.gaussian.alpha` | `2.0` | |
| `film.filter.mitchell.b` / `.c` | `1/3` / `1/3` | MITCHELL |
| `film.filter.mitchellss.b` / `.c` | `1/3` / `1/3` | MITCHELL_SS |
| `film.filter.sinc.tau` | `3.0` | SINC |

### 1.9 Periodic save and resume (.flm / .rsm)

> Checked on the 2026-11-11 Linux build: writing `.rsm` works but loading it (and loading a FILESAVER `BIN` `.bcf`) fails with `ERROR: class version St10unique_ptrIN3slg12RenderConfig...`. Binary serialization is broken there; TXT export works.

Source: `src/slg/renderconfig.cpp` (defaults), `src/slg/rendersession.cpp` (`CheckPeriodicSave`, `SaveResumeFile`).

| Property | Default | Effect |
|---|---|---|
| `periodicsave.film.outputs.period` | `0` (off) | seconds; writes all `film.outputs.*` |
| `periodicsave.film.period` | `0` | seconds; serialized film |
| `periodicsave.film.filename` | `film.flm` | |
| `periodicsave.resumerendering.period` | `0` | **seconds; > 0 enables writing a resume file** |
| `periodicsave.resumerendering.filename` | `rendering.rsm` | |

Each enabled save also runs once when the session stops (`RenderSession::Stop` calls `CheckPeriodicSave(true)`), so a period > 0 always leaves a final `.rsm`/`.flm`. The `.rsm` holds the render config + scene + render state + film. Resume with `luxcoreconsole file.rsm` (more `-D` props are applied on top). Note: `periodicsave.*` is checked from `RenderSession::UpdateStats`, which luxcoreconsole calls every 1 s.

### 1.10 FILESAVER engine (scene export)

Source: `src/slg/engines/filesaver/filesaver.cpp`.

| Property | Default | Notes |
|---|---|---|
| `renderengine.type = FILESAVER` | | |
| `filesaver.format` | `TXT` | `TXT` or `BIN` (anything else throws) |
| `filesaver.directory` | `luxcore-exported-scene` | TXT: **must already exist** (throws "Directory doesn't exist") |
| `filesaver.filename` | `luxcore-exported-scene.bcf` | BIN output file |
| `filesaver.renderengine.type` | `PATHCPU` | engine written into the exported config |

TXT writes `render.cfg` (with `scene.file = scene.scn`, `renderengine.type = <filesaver.renderengine.type>`, `filesaver.directory` removed), `scene.scn`, every image map, and every real mesh as `mesh-NNNNN.ply`. BIN writes one `.bcf` (`RenderConfig::SaveSerialized`). luxcoreconsole skips `SaveOutputs` for FILESAVER. glTF export (`ExportSceneGLTF`) exists only through the API (`RenderConfig::ExportGLTF`), not as a FILESAVER format.

---

## 2. Film outputs and image pipelines

Sources: `src/slg/film/filmparse.cpp` (`ParseOutputs`, `CreateImagePipeline`, `ParseRadianceGroupsScale`), `src/slg/film/filmoutputs.cpp`, `src/slg/film/filmoutput.cpp`, `src/slg/film/filmproperties.cpp`.

### 2.1 `film.outputs.<name>.*`

- Keys: `film.outputs.<name>.type` (default `RGB_IMAGEPIPELINE`), `.filename` (default **`image.png` for every output**), `.index` (image pipeline, for `*_IMAGEPIPELINE`), `.id` (for ID-based outputs). `<name>` is any label (usually 0, 1, ...).
- With no `film.outputs.*` at all, the film gets `film.outputs.0.type = RGB_IMAGEPIPELINE`, `film.outputs.0.filename = image.png`. Any `film.outputs.*` in a parse replaces the whole set.
- "HDR" means the file extension is `.exr` or `.hdr`. Images are written with OpenImageIO, so any OIIO-writable extension works for LDR (png, jpg, tif, ...).

| Type | File constraint | Extra keys |
|---|---|---|
| `RGB`, `RGBA` | HDR only | |
| `RGB_IMAGEPIPELINE` (alias `RGB_TONEMAPPED`) | any | `.index` (0) |
| `RGBA_IMAGEPIPELINE` (alias `RGBA_TONEMAPPED`) | any | `.index` (0) |
| `ALPHA` | any | |
| `DEPTH`, `POSITION`, `GEOMETRY_NORMAL`, `SHADING_NORMAL` | HDR only | |
| `MATERIAL_ID`, `OBJECT_ID` | **non-HDR only** | |
| `DIRECT_DIFFUSE`, `DIRECT_DIFFUSE_REFLECT`, `DIRECT_DIFFUSE_TRANSMIT`, `DIRECT_GLOSSY`, `DIRECT_GLOSSY_REFLECT`, `DIRECT_GLOSSY_TRANSMIT`, `EMISSION`, `INDIRECT_DIFFUSE`, `INDIRECT_DIFFUSE_REFLECT`, `INDIRECT_DIFFUSE_TRANSMIT`, `INDIRECT_GLOSSY`, `INDIRECT_GLOSSY_REFLECT`, `INDIRECT_GLOSSY_TRANSMIT`, `INDIRECT_SPECULAR`, `INDIRECT_SPECULAR_REFLECT`, `INDIRECT_SPECULAR_TRANSMIT`, `CAUSTIC` | HDR only | |
| `MATERIAL_ID_MASK`, `BY_MATERIAL_ID`, `OBJECT_ID_MASK`, `BY_OBJECT_ID` | any | `.id` (default 255) |
| `RADIANCE_GROUP` | any | `.id` (light group, default 0) |
| `DIRECT_SHADOW_MASK`, `INDIRECT_SHADOW_MASK`, `UV`, `RAYCOUNT`, `IRRADIANCE`, `SAMPLECOUNT`, `CONVERGENCE`, `MATERIAL_ID_COLOR`, `ALBEDO`, `AVG_SHADING_NORMAL`, `NOISE`, `USER_IMPORTANCE` | any | |
| `SERIALIZED_FILM` | `.flm` (serialized film) | |

### 2.2 Image pipelines

- Single pipeline: `film.imagepipeline.<step>.type` (old syntax). Several: `film.imagepipelines.<pipeline>.<step>.type` (new syntax). Steps are sorted numerically.
- No pipeline defined: `TONEMAP_AUTOLINEAR` then `GAMMA_CORRECTION` 2.2.
- A new pipeline definition in a parse deletes all old pipeline props.

| Plugin `type` | Params (default) |
|---|---|
| `TONEMAP_LINEAR` | `.scale` (1.0) |
| `TONEMAP_REINHARD02` | `.prescale` (1.0), `.postscale` (1.2), `.burn` (3.75) |
| `TONEMAP_AUTOLINEAR` | — |
| `TONEMAP_LUXLINEAR` | `.sensitivity` (100), `.exposure` (0.001), `.fstop` (2.8) |
| `TONEMAP_OPENCOLORIO` | `.mode` (`COLORSPACE_CONVERSION`): `.config` (""), `.src` (OCIO `ROLE_RENDERING`), `.dst` (OCIO `ROLE_INTERCHANGE_DISPLAY`). `LUT_CONVERSION`: `.lutfile` (file.lut). `DISPLAY_CONVERSION`: `.config`, `.src`, `.display`, `.view`, `.look` (""). `LOOK_CONVERSION`: `.config`, `.src`, `.look` ("look") |
| `GAMMA_CORRECTION` | `.value` (2.2), `.table.size` (4096) |
| `NOP` | — |
| `OUTPUT_SWITCHER` | `.channel` (`DEPTH`; any film channel name from `filmchannels.cpp`, or `CAUSTIC`), `.index` (0) |
| `GAUSSIANFILTER_3x3` | `.weight` (0.15) |
| `CAMERA_RESPONSE_FUNC` | `.name` (`Advantix_100CD`; a built-in preset name or a `.crf` file path) |
| `CONTOUR_LINES` | `.scale` (179), `.range` (100), `.steps` (8), `.zerogridsize` (8) |
| `BACKGROUND_IMG` | `.file` (or `.blob` + `.blob.width/.height/.channelcount`), `.gamma`/colorspace, `.storage`, `.wrap`, `.filter` (ImageMap props, §3.5) |
| `BLOOM` | `.radius` (0.07), `.weight` (0.25) |
| `OBJECT_ID_MASK` | `.id` (0) |
| `VIGNETTING` | `.scale` (0.4) |
| `COLOR_ABERRATION` | `.amount` (0.005; 1 or 2 values) |
| `PREMULTIPLY_ALPHA` | — |
| `MIST` | `.color` (1 1 1), `.amount` (0.005), `.startdistance` (0), `.enddistance` (10000), `.excludebackground` (0) |
| `BCD_DENOISER` | `.warmupspp` (2), `.histdistthresh` (1), `.patchradius` (1), `.searchwindowradius` (6), `.mineigenvalue` (1e-8), `.userandompixelorder` (1), `.markedpixelsskippingprobability` (1), `.threadcount` (0 = all), `.scales` (3), `.filterspikes` (0), `.applydenoise` (1), `.spikestddev` (2) |
| `INTEL_OIDN` (unless built with `LUXCORE_DISABLE_OIDN`) | `.filter.type` (`RT`), `.oidnmemory` (6000 MB), `.sharpness` (0.1), `.prefilter.enable` (1), `.firefly.sigma` (0) |
| `OPTIX_DENOISER` (CUDA builds only) | `.sharpness` (0.1), `.minspp` (0) |
| `WHITE_BALANCE` | `.temperature` (6500, clamp 1000..40000), `.reverse` (1), `.normalize` (0) |
| `BAKEMAP_MARGIN` | `.margin` (2), `.samplesthreshold` (0) |
| `COLOR_LUT` | `.file` (`lut.cube`), `.strength` (1.0) |
| `PATTERNS` | `.index` (0) |

The denoisers are named exactly `INTEL_OIDN`, `OPTIX_DENOISER`, `BCD_DENOISER`; the camera response plugin is `CAMERA_RESPONSE_FUNC`. Any other name throws "Unknown image pipeline plugin type".

### 2.3 Radiance group scales

`film.imagepipeline.radiancescales.<lightgroup>.*` or `film.imagepipelines.<p>.radiancescales.<lightgroup>.*`:
`.globalscale` (1.0), `.temperature` (0 = off), `.rgbscale` (1 1 1), `.reverse` (1), `.normalize` (0), `.enabled` (1). Light group ids come from `scene.lights.X.id` and `scene.materials.X.emission.id`.

---

## 3. Scene (.scn)

Parse order is fixed (`src/slg/scene/scene.cpp`, `Scene::Parse`): textures, volumes, materials, camera, shapes, objects, lights. Within textures/materials/volumes/shapes/objects, names are processed in **first-definition order**, so define a referenced texture/material/shape before the one that uses it (no forward references; an unknown texture name falls into constant parsing and fails with "Syntax error in texture name").

### 3.1 Camera (`scene.camera.*`)

Source: `src/slg/scene/parsecamera.cpp`, `src/slg/cameras/projective.cpp`.

| Property | Default | Notes |
|---|---|---|
| `scene.camera.type` | `perspective` | `perspective`, `orthographic`, `environment`, `stereo` |
| `scene.camera.lookat.orig` | (0 10 0) | if absent, camera-to-world is identity |
| `scene.camera.lookat.target` | (0 0 0) | |
| `scene.camera.up` | (0 0 1) | **not** `lookat.up`. Legacy `scene.camera.lookat` (6 values) forces up = Z |
| `scene.camera.fieldofview` | 45 | degrees, **perspective only**; applies to the **longer** image side (`ProjectiveCamera::Update` in `src/slg/cameras/projective.cpp` sets the screen window to ±1 on the long axis, ±1/aspect on the short one; checked by rendering). Stereo ignores it (stays 45) |
| `scene.camera.screenwindow` | auto from aspect | 4 floats; perspective/orthographic/environment |
| `scene.camera.lensradius` | 0 | not environment |
| `scene.camera.focaldistance` | 10 | not environment |
| `scene.camera.autofocus.enable` | 0 | traces a ray at the image center |
| `scene.camera.clippingplane.enable` | 0 | then `.clippingplane.center` (point), `.clippingplane.normal` |
| `scene.camera.cliphither` / `.clipyon` | 1e-3 / 1e30 | all types |
| `scene.camera.shutteropen` / `.shutterclose` | 0 / 1 | |
| `scene.camera.autovolume.enable` | 1 | if 0, `scene.camera.volume` = volume name |
| `scene.camera.bokeh.blades` / `.power` | 0 / 3 | perspective |
| `scene.camera.bokeh.distribution.type` | `NONE` | custom: `.bokeh.distribution.image` |
| `scene.camera.bokeh.scale.x` / `.y` | 1 / 1 | |
| `scene.camera.oculusrift.barrelpostpro.enable` | 0 | perspective, stereo |
| `scene.camera.environment.degrees` | 360 | environment |
| `scene.camera.stereo.type` | `perspective` | also `environment_180`, `environment_360` |
| `scene.camera.eyesdistance` / `.lensdistance` | 0.0626 / 0.2779 | stereo |
| `scene.camera.motion.<i>.time` / `.transformation` | — | camera motion blur; times strictly increasing |

### 3.2 Shapes (`scene.shapes.<name>.*`)

Source: `src/slg/scene/parseshapes.cpp`, `src/luxrays/core/exttrianglemeshfile.cpp`.

Mesh files: **only `.ply` (ASCII or binary) and `.bpy` (LuxCore serialized mesh)** load (`ExtTriangleMesh::Load`); anything else throws "Unknown file extension while loading a mesh". No `.obj`/`.stl`. PLY: element `vertex` with `x y z`, optional `nx ny nz`, UVs as **`s t`** (`s1 t1`... for extra UV sets), `red green blue` (uchar /255 or float), `alpha`, `vertaov`; element `face` with list `vertex_indices` (triangles; quads split; other polygon sizes skipped); optional `faceaov` elements.

| `type` | Params (default) |
|---|---|
| `mesh` (default) | `.ply` (file path), `.transformation` (16, **baked into the vertices**) or `.appliedtransformation` (16, only records local-to-world) |
| `inlinedmesh` | `.vertices` (x y z ...), `.faces` (i j k ...), optional `.normals` (3/vertex), `.uvs` (2/vertex), `.transformation`/`.appliedtransformation` |
| `group` | `.<i>.shape` (name), `.<i>.transformation` |
| `pointiness` | `.source`, `.aovindex` (none) |
| `strands` | `.file` (`strands.hair`, cyHair), `.tessellation.type` (`ribbon`; `ribbonadaptive`, `solid`, `solidadaptive`), `.tessellation.adaptive.maxdepth` (8), `.tessellation.adaptive.error` (0.1), `.tessellation.solid.sidecount` (3), `.tessellation.solid.capbottom`/`.captop` (0), `.tessellation.usecameraposition` (0); misspelled `tesselation.*` accepted |
| `subdiv` | `.source`, `.maxlevel` (2), `.maxedgescreensize` (0), `.sharpnessthreshold` (0.512 rad), `.creaseweight` (10), `.creases` (`computed`; `none`, `imported`), `.matslot` (-1) |
| `subdiv_old` | `.source`, `.maxlevel` (2) |
| `tessellate` | `.source`, `.rate` (4) |
| `displacement` | `.source`, `.map` (texture), `.map.type` (`height`; `vector`), `.map.channels` (2 0 1), `.scale` (1), `.offset` (0), `.uvindex` (0), `.normalsmooth` (1) |
| `harlequin` | `.source` |
| `simplify` | `.source`, `.target` (0.25), `.edgescreensize` (0, clamp 0..1), `.preserveborder` (0) |
| `simplify_old` | same params, deprecated |
| `islandaov` | `.source`, `.dataindex` (0) |
| `randomtriangleaov` | `.source`, `.srcdataindex` (0), `.dstdataindex` (0) |
| `edgedetectoraov` | `.source`, `.aovindex0/1/2` (0/1/2) |
| `bevel` | `.source`, `.bevel.radius` (0). Rounds convex edges at render time (CPU engines). Builds before 2026-11-13 segfault when the source has no convex edge (flat panel, concave fold); fixed in `src/luxrays/core/exttrianglemeshbevel.cpp`, test `BevelShapeWithoutConvexEdges` in `pyunittests/.../shapes/testsingle.py` |
| `cameraprojuv` | `.source`, `.uvindex` (0) |
| `mergeondistance` | `.source`, `.tolerance` (1), `.importnormals` (0) |

Modifier shapes take another shape's name in `.source`, so the source must be defined earlier.

### 3.3 Objects (`scene.objects.<name>.*`)

Source: `src/slg/scene/parseobjects.cpp`.

| Property | Notes |
|---|---|
| `.material` | **required**, must already be defined |
| `.shape` | shape name, or legacy `.ply` (file, loaded directly; `.appliedtransformation` honored) or legacy inline `.vertices`/`.faces` |
| `.transformation` | 16 floats; creates an **instance** of the shape (shape not copied) |
| `.motion.<i>.time` / `.motion.<i>.transformation` | motion blur; times strictly increasing |
| `.id` | object id (default: harlequin color from a counter) |
| `.camerainvisible` | default 0 |
| `.bake.combined.file` / `.bake.lightmap.file` (+ `.uvindex`, ImageMap props) | baked maps |

An object whose material has `emission` becomes an area light (one triangle light per triangle). There is no `trianglearea` light type to declare.

### 3.4 Materials (`scene.materials.<name>.*`)

Source: `src/slg/scene/parsematerials.cpp`. Default type `matte`. All channel params are textures (§3.5); defaults below.

| `type` | Params (default) |
|---|---|
| `matte` | `kd` (0.75) |
| `roughmatte` | `kd` (0.75), `sigma` (0.75) |
| `mirror` | `kr` (1) |
| `glass` | `kr` (1), `kt` (1), `exteriorior`, `interiorior` (unset if absent; legacy `ioroutside`/`iorinside`), `cauchyb` (legacy `cauchyc`), `filmthickness`, `filmior` |
| `archglass` | `kr`, `kt`, `exteriorior`, `interiorior`, `filmthickness`, `filmior` |
| `roughglass` | `kr`, `kt`, `exteriorior`, `interiorior`, `uroughness` (0.1), `vroughness` (0.1), `filmthickness`, `filmior` |
| `glossy2` | `kd` (0.5), `ks` (0.5), `uroughness`/`vroughness` (0.1), `ka` (0), `d` (0), `index` (0 0 0), `multibounce` (0), `doublesided` (0) |
| `metal2` | `uroughness`/`vroughness` (0.1) and one of: `preset` (or `name`): `aluminium` (default), `silver`, `gold`, `copper`, `amorphous carbon`; or `fresnel` = a fresnel texture name; else `n` (0.5), `k` (0.5) |
| `glossycoating` | `base` (material name), `ks` (0.5), `uroughness`/`vroughness` (0.1), `ka` (0), `d` (0), `index` (0), `multibounce` (0) |
| `glossytranslucent` | `kd`, `kt`, `ks`, `ks_bf` (0.5), `uroughness`, `vroughness`, `uroughness_bf`, `vroughness_bf` (0.1), `ka`, `ka_bf`, `d`, `d_bf`, `index`, `index_bf` (0), `multibounce`, `multibounce_bf` (0) |
| `mattetranslucent` | `kr` (0.5), `kt` (0.5) |
| `roughmattetranslucent` | `kr`, `kt` (0.5), `sigma` (0) |
| `carpaint` | `preset` (`ford f8`, `polaris silber`, `opel titan`, `bmw339`, `2k acrylack`, `white`, `blue`, `blue matte`; unknown names fall back to manual) or `kd`, `ks1..3`, `r1..3`, `m1..3`; `ka` (0), `d` (0) |
| `cloth` | `preset` (`denim` default; `silk_charmeuse`, `silk_shantung`, `cotton_twill`, `wool_gabardine`, `polyester_lining_cloth`), `weft_kd`, `weft_ks`, `warp_kd`, `warp_ks` (0.5), `repeat_u`, `repeat_v` (100) |
| `velvet` | `kd` (0.5), `p1` (-2), `p2` (20), `p3` (2), `thickness` (0.1) |
| `disney` | `basecolor` (0.5), `subsurface`, `roughness`, `metallic`, `specular`, `speculartint`, `clearcoat`, `clearcoatgloss`, `anisotropic`, `sheen`, `sheentint` (all 0), `filmamount`, `filmthickness`, `filmior` |
| `mix` | `material1`, `material2` (names), `amount` (0.5) |
| `twosided` | `frontmaterial`, `backmaterial` (names) |
| `null` | only transparency |

There are no `glossy` or `metal` (v1) types; only `glossy2` and `metal2`.

Common to all materials:

| Property | Default |
|---|---|
| `transparency` (or `transparency.front` / `transparency.back`) | none |
| `transparency.shadow` | 0 0 0; `transparency.shadowoverride` (0) |
| `bumptex` | none; else `normaltex` (+ `normaltex.scale` 1) |
| `bumpsamplingdistance` | 0.001 |
| `emission` | none (0 or black removes it) |
| `emission.gain` | 1 1 1 |
| `emission.power` / `emission.efficiency` (alias `efficency`) | 0 / 0 (watts / lm/W; 0 = use gain only) |
| `emission.normalizebycolor` / `emission.gain.normalizebycolor` | 1 / 0 |
| `emission.theta` | 90 (degrees, clamped 0..90) |
| `emission.id` | 0 (light group) |
| `emission.importance` | 1 |
| `emission.temperature` / `.temperature.normalize` | -1 (off) / 0 |
| `emission.directlightsampling.type` | `AUTO` (`ENABLED`, `DISABLED`) |
| `emission.mapfile` / `emission.iesfile` / `emission.iesblob` | image and/or IES emission map; `emission.flipz`, `emission.map.width/height`, ImageMap props on `emission.*` |
| `visibility.indirect.diffuse/glossy/specular.enable` | 1 |
| `shadowcatcher.enable` / `shadowcatcher.onlyinfinitelights` | 0 / 0 |
| `photongi.enable` | 1 |
| `holdout.enable` | 0 |
| `volume.interior` / `volume.exterior` | volume names |
| `id` | harlequin default |

### 3.5 Textures (`scene.textures.<name>.*`)

Source: `src/slg/scene/parsetextures.cpp`, `src/slg/imagemap/imagemap.cpp`, `src/slg/core/colorspace.cpp`. Default type `imagemap`.

Main types:

| `type` | Params (default) |
|---|---|
| `imagemap` | `file` (image.png), `gain` (1), `mapping.*` (2D), ImageMap props (below), `randomizedtiling.enable` (0, needs `wrap = repeat`) |
| `constfloat1` | `value` (1), optional colorspace |
| `constfloat3` | `value` (1 1 1), optional colorspace |
| `scale` / `add` / `subtract` / `divide` / `dotproduct` / `lessthan` / `greaterthan` | `texture1`, `texture2` |
| `mix` | `amount` (0.5), `texture1` (0), `texture2` (1) |
| `checkerboard2d` / `checkerboard3d` | `texture1` (1), `texture2` (0), `mapping.*` |
| `fbm` / `wrinkled` | `octaves` (8), `roughness` (0.5), 3D mapping |
| `marble` | `octaves`, `roughness`, `scale` (1), `variation` (0.2) |
| `blender_blend`, `blender_clouds`, `blender_distortednoise`, `blender_magic`, `blender_marble`, `blender_musgrave`, `blender_noise`, `blender_stucci`, `blender_wood`, `blender_voronoi` | Blender procedural params (`noisesize`, `noisedepth`, `bright`, `contrast`, ...), 3D mapping |
| `brick` | `bricktex`, `mortartex`, `brickmodtex`, `brickbond` (running), sizes |
| `dots`, `windy`, `uv`, `band`, `cloud`, `blackbody` (`temperature` 6500, `normalize`), `irregulardata`, `lampspectrum`, `hsv`, `remap`, `clamp`, `abs`, `power`, `colordepth`, `normalmap` (`texture`, `scale`), `bilerp`, `hitpointcolor`/`alpha`/`grey`/`vertexaov`/`triangleaov`, `objectid`, `objectidcolor`, `objectidnormalized`, `shadingnormal`, `position`, `splitfloat3`, `makefloat3`, `rounding`, `modulo`, `brightcontrast`, `triplanar`, `random`, `wireframe`, `distort`, `bombing`, `densitygrid` | see source |
| `fresnelcolor` | `kr` (0.5) |
| `fresnelconst` | `n`, `k` (1 1 1) |
| `fresnelpreset` | `name` (aluminium; silver, gold, copper, amorphous carbon) |
| `fresnelluxpop` / `fresnelsopra` | `file` (.nk) |
| `fresnelabbe`, `fresnelcauchy`, `fresnelapproxn`, `fresnelapproxk` | see source |

2D mapping `mapping.type`: `uvmapping2d` (default: `uvindex`, `rotation`, `uvscale` (1 1), `uvdelta` (0 0), `centerrotation`) or `uvrandommapping2d`. 3D mapping: `uvmapping3d` (default), `globalmapping3d`, `localmapping3d`, `localrandommapping3d`, each with `mapping.transformation`.

ImageMap props (any image: textures, infinite light, emission maps, BACKGROUND_IMG):

| Prop | Default | Values |
|---|---|---|
| `.gamma` (alias `.colorspace.gamma`) | **2.2** | |
| `.colorspace` | `luxcore` | `nop`, `luxcore` (uses gamma), `opencolorio` (`.colorspace.config`, `.colorspace.name`) |
| `.storage` | `auto` | `auto`, `byte`, `half`, `float` |
| `.wrap` | `repeat` | `repeat`, `black`, `white`, `clamp` |
| `.filter` | `linear` | `nearest`, `linear` |
| `.channel` | `default` | `default`, `red`, `green`, `blue`, `alpha`, `mean`, `colored_mean`, `rgb` |

Constants in texture slots: `0.5`, `0.8 0.1 0.1`, or with a color space: `nop v` / `nop r g b`, `luxcore <gamma> v` / `luxcore <gamma> r g b`, `opencolorio <config> <space> v|r g b`.

### 3.6 Lights (`scene.lights.<name>.*`)

Source: `src/slg/scene/parselights.cpp`. Default `type` is **`sky2`**. Legacy blocks `scene.skylight.*` (sky2), `scene.infinitelight.*` (infinite), `scene.sunlight.*` (sun) still parse.

Common: `gain` (1 1 1), `id` (0, light group), `importance` (1), `transformation` (16, light-to-world), `volume` (name); for non-intersectable lights `temperature` (-1) and `temperature.normalize` (0). For point-like lights: `power` (W, 0), `efficiency` (lm/W, 0; alias `efficency`), `normalizebycolor` (1).

| `type` | Params (default) |
|---|---|
| `infinite` | `file` (image.png; lat-long), ImageMap props (**gamma 2.2 by default: set `gamma = 1` for .exr/.hdr**), `sampleupperhemisphereonly` (0), `visibility.indirect.{diffuse,glossy,specular}.enable` (1), `visibilitymapcache.enable` (0) + `visibilitymapcache.*` |
| `constantinfinite` | `color` (1 1 1), visibility + visibilitymapcache as above |
| `sky2` | `dir` (0 0 1, direction to the sun), `turbidity` (2.2), `groundalbedo` (0 0 0), `ground.enable` (0), `ground.autoscale` (1), `ground.color` (0.75), `distribution.width`/`.height` (512/256), visibility, visibilitymapcache |
| `sky3` (Prague model) | `dataset` (SkyModelDataset.dat; falls back to `scene.pragueskymodel.dataset`), `visibility` (59.4), `altitude` (0), `groundalbedo` (0), `ground.*`, `dir`, `envmap.width`/`.height` (2048/1024) |
| `sun` | `dir` (0 0 1), `turbidity` (2.2), `relsize` (1, min 1), visibility |
| `sun3` | Prague params + `relsize`, `dir` |
| `point` | `position` (0 0 0), `color` (1) |
| `mappoint` | `position`, `color`, `mapfile` and/or `iesfile` (required), `flipz`, `map.width/height` |
| `sphere` | `position`, `radius` (1), `color` |
| `mapsphere` | as sphere + `mapfile`/`iesfile` |
| `spot` | `position` (0 0 0), `target` (0 0 1), `coneangle` (30°), `conedeltaangle` (5°), `color` |
| `projection` | `position`, `target`, `fov` (45°), `mapfile` (optional) |
| `laser` | `position`, `target`, `radius` (0.01), `color` |
| `distant` | `direction` (0 0 1, direction the light travels), `theta` (10°), `color` |
| `sharpdistant` | `direction`, `color` |

Area lights are not a light type: set `emission` on the object's material (§3.4).

visibilitymapcache sub-props (`src/slg/lights/visibility/envlightvisibilitycache.cpp`): `.map.quality` (0.5), `.map.tilewidth`/`.tileheight` (0 = auto), `.map.tilesamplecount`, `.map.sampleupperhemisphereonly` (0), `.visibility.maxsamplecount` (1M), `.visibility.maxdepth` (4), `.visibility.targethitrate` (0.99), `.visibility.radius` (0), `.visibility.normalangle` (25), `.persistent.file` (""), `.persistent.safesave` (1).

### 3.7 Volumes (`scene.volumes.<name>.*`)

Source: `src/slg/scene/parsevolumes.cpp`. Volumes are stored with materials (names share one namespace).

| Property | Default |
|---|---|
| `type` | **default string is `homogenous` (misspelled), which is not a valid type: always set `type`** (`clear`, `homogeneous`, `heterogeneous`) |
| `ior` | 1 (texture) |
| `absorption` | 0 0 0 |
| `scattering`, `asymmetry` | 0 0 0 (homogeneous, heterogeneous) |
| `multiscattering` | 0 |
| `steps.size` / `steps.maxcount` | 1 / 32 (heterogeneous) |
| `emission`, `emission.id` | none / 0 |
| `priority` | 0 |
| `photongi.enable` | 0 |
| `id` | harlequin |

`scene.world.volume.default = <volume>` sets the world volume. Attach with material `volume.interior`/`volume.exterior`, `scene.camera.volume`, `scene.lights.X.volume`.

---

## 4. Conventions

- **Z is up**: camera up defaults to (0 0 1); sun/sky `dir` default (0 0 1) is the zenith; infinite light uses a lat-long map around Z (`InfiniteLight::GetEnvUV`).
- Matrices: 16 values, column-major, translation in values 13-15 (§0). Shape `.transformation` bakes into the mesh; object `.transformation` instances it; light `.transformation` is light-to-world.
- Angles in degrees (fov, coneangle, theta, emission.theta); subdiv `sharpnessthreshold` in radians.
- Colors are linear RGB. Image textures are **linearized with gamma 2.2 by default, for every file format including .exr/.hdr**; set `gamma = 1` (or `colorspace = nop`) for linear data, normal maps and HDR environments. Constant colors are linear unless written with a colorspace prefix.
- Output images: the default pipeline (auto-linear + gamma 2.2) produces display-ready PNGs; `RGB`/`RGBA` raw outputs need .exr/.hdr.
- Units: no unit is enforced by the parser; `scene.epsilon.min/max` are absolute distances, so very large or very small scenes may need them changed.

---

## 5. `luxcoreconsole`

Source: `samples/luxcoreconsole/luxcoreconsole.cpp`, `src/luxcore/luxcoreinit.cpp`.

### 5.1 Usage

`luxcoreconsole [options] <file>` where `<file>` extension (case-insensitive) is:

| Ext | Meaning |
|---|---|
| `.cfg` | LuxCore SDL render config (loads `scene.file`) |
| `.lxs` | old LuxRender SDL, translated by `luxcore::ParseLXS` |
| `.bcf` | binary RenderConfig (from FILESAVER `BIN`) |
| `.rsm` | resume file (config + scene + render state + film) |

Any other extension: `RUNTIME ERROR: Unknown file extension: ...`, exit 1. Two config files: "Used multiple configuration files".

| Option | Effect |
|---|---|
| `-o <file>` | config file (no extension check here; checked later) |
| `-f <scene>` | sets `scene.file` |
| `-w <n>` / `-e <n>` | sets `film.width` / `film.height` |
| `-D <name> <value>` | sets one property; **the value is a single string** (`Property(name).Add(value)`), so multi-value props (colors, matrices, `film.subregion`, `batch.haltspp A B`) cannot be passed this way. It only reaches render-config props: a `scene.*` value defined in the `.scn` (camera, lights, materials) is not changed by `-D` (checked: `-D scene.camera.lookat.orig ...` has no effect) |
| `-d <dir>` | `chdir` to `<dir>` (happens while parsing args) |
| `-c` | remove unused meshes, image maps, materials, textures |
| `-s` | print per-device stats each second |
| `-k` | clear and refill the OpenCL kernel caches for PATHOCL, TILEPATHOCL, RTPATHOCL, then exit 0 (no config file needed) |
| `-h` | print usage, exit 0 |

Unknown option: prints "Invalid option", exit 1. Command-line props are applied on top of the file (`.cfg`: `props->Set(cmdLineProp)`; `.bcf`/`.rsm`: `config->Parse`).

### 5.2 Run loop, output and exit codes

- Forces `screen.refresh.interval = 2500` (film update every 2.5 s) unless FILESAVER.
- Every 1 s prints `[Elapsed time: T/HALTsec][Samples S/HALTSPP][Convergence C%][Avg. samples/sec XM on YK tris]` (halttime is printed as an int).
- Loop ends when the engine `HasDone()` (a halt condition, §1.6). It then calls `Stop()` (which runs the final periodic saves) and `Film::SaveOutputs()` (all `film.outputs.*`), unless FILESAVER. Prints `Done.`.
- All logging goes to **stderr** (`DefaultDebugHandler`), with `[LuxCore]`, `[SDL]`, `[LuxRays]` prefixes and time since init.
- Exit 0 on success, 1 on any exception (`RUNTIME ERROR: ...` or `ERROR: ...`).

### 5.3 File name resolution

Before loading: resolver paths cleared, then `.` and the config file's directory added. `ResolveFile(name)`: absolute paths and existing relative paths are used as is; otherwise tries `<dir>/<name>` for each path, then `<dir>/<basename>`; otherwise returns the name unchanged. Used for `scene.file`, mesh files (`.ply`), image maps, IES files, `.nk` files, OCIO configs, CRF/LUT files, strands, OpenVDB, sky datasets. The **scene file's own directory is not added**, so paths inside a `.scn` resolve against the cwd and the `.cfg` directory (shipped scenes use repo-root-relative paths like `scenes/luxball/room.ply`).

---

## 6. OpenCL/CUDA headless notes

Sources: `src/luxrays/core/init.cpp`, `src/luxrays/core/context.cpp`, `src/luxrays/utils/config.cpp`, `src/luxrays/utils/ocl.cpp`, `src/luxrays/utils/cuda.cpp`, `src/slg/engines/oclrenderengine.cpp`, `docs/SPIRV_PRECOMPILATION.md`.

- OpenCL is loaded at run time (`clewInit`); if the library is missing: stderr `OpenCL disabled: OpenCL library not found`. CUDA via `cuewInit` + `cuInit`; failure prints `CUDA disabled: ...` or a `Cuda error: ...` line. OptiX enabled only if `optixInit` succeeds.
- No platform: log `No OpenCL platform available`. A `context.opencl.platform.index` out of range throws "Unable to find an appropriate OpenCL platform".
- **PATHOCL/TILEPATHOCL/RTPATHOCL do not fall back to CPU**: with no selected OpenCL/CUDA device they throw `No hardware device selected or available` (exit 1). By default only GPUs are selected (`opencl.cpu.use = 0`), so a CPU-only OpenCL runtime (e.g. PoCL) needs `opencl.cpu.use = 1`. Use PATHCPU on machines without a GPU.
- The film image pipeline falls back to CPU when no hardware device exists (`filmimagepipelinehw.cpp`).
- Kernel cache directory (`luxrays::GetCacheDir`): Linux `$XDG_CACHE_HOME/luxcorerender.org`, or **`$HOME/.config/luxcorerender.org`** if `XDG_CACHE_HOME` is unset (not `~/.cache`), or the temp dir if `HOME` is unset; macOS `~/luxcorerender.org`; other OS `<temp>/luxcorerender.org`. Subdirs: `ocl_kernel_cache/LUXRAYS_<version>/<platform>/<device>/...` and `cuda_kernel_cache/LUXRAYS_<version>/...`. The only environment variables read are `XDG_CACHE_HOME` and `HOME`.
- First OpenCL run compiles kernels (slow); `luxcoreconsole -k` pre-fills the cache. Builds made with `make spirv` embed SPIR-V kernels used directly by drivers with `cl_khr_il_program`.

---

## 7. `samples/pyluxcoretool`

`samples/pyluxcoretool/pyluxcoretool.py` is a small CLI dispatcher (argparse) with sub-commands `console`, `merge`, `maketx`, `netconsole`, `netconsoleui`, `netnode`, `netnodeui`, `menu` (default), `help`, plus PyInstaller `.spec` files for packaging. It imports `pyluxcoretools.pyluxcoreconsole.cmd` etc., but the package in `python/pyluxcoretools/` now has `console/`, `merge/`, `maketx/`, `netconsole/`, `netnode/`, `netmenu/`, so the sample looks stale. The maintained entry points are the wheel scripts in `pyproject.toml`: `pyluxcore-console` (`.cfg/.lxs/.bcf/.rsm`, flags `-f -w -e -D -d -c` plus `-t` camera shutter), `pyluxcore-merge` (merge films), `pyluxcore-maketx`, `pyluxcore-netmenu`, `pyluxcore-netconsole`, `pyluxcore-netnode` (network render farm), and GUI `pyluxcore-netconsole-ui`, `pyluxcore-netnode-ui`.
