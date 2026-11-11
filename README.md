# luxcoreconsole, Linux x86_64 build of 2026-11-11

Prebuilt LuxCoreRender command-line renderer (`luxcoreconsole`). This orphan branch holds
only build outputs and their docs, no source history.

| File | What |
|---|---|
| `luxcore-cli-linux-x86_64.tar.xz` | `bin/luxcoreconsole`, `lib/` (Open Image Denoise 2.5.0, oneTBB 2023.0.0), `COPYING.txt`, `BUILDINFO.txt` |
| `SHA256SUMS` | SHA-256 of the tarball |
| `skills/` | agent skills for this build (snapshot of `.claude/skills` on `claude/bold-gauss-8rzxny`) |

## Build
- Source: `brdmaker/LuxCore` commit `64a7632598db46d994f046004a5ee5dad805d0cf` (`main`),
  LuxCore 2.11.2, Release.
- Ubuntu 24.04, gcc 14.2, CMake 3.31, Conan 2.32, LuxCoreDeps v2.2.4 (prebuilt).
- `make deps && make luxcoreconsole`, then the shared libraries were bundled next to the binary
  (`RPATH=$ORIGIN/../lib`) and the binary was stripped.

## Use
```bash
git fetch origin luxcore-cli-2026-11-11
git show origin/luxcore-cli-2026-11-11:luxcore-cli-linux-x86_64.tar.xz > luxcore-cli-linux-x86_64.tar.xz
git show origin/luxcore-cli-2026-11-11:SHA256SUMS > SHA256SUMS && sha256sum -c SHA256SUMS
tar -xJf luxcore-cli-linux-x86_64.tar.xz
luxcore-cli-linux-x86_64/bin/luxcoreconsole -h
```
Needs glibc >= 2.38, libstdc++ with `GLIBCXX_3.4.31` and `libgomp1` (Ubuntu 24.04,
Debian 13 or newer). See `skills/luxcore-cli-start/SKILL.md`.

## Tested
- `scenes/cornell/cornell.cfg` with PATHCPU, 320x320, 32 spp: correct image, 8 s on 4 threads.
- STL parts from `brdmaker/3dassets` (lathe chuck, NEMA17 assembly) through
  `skills/luxcore-render-cad-part`: studio and daylight lighting, OIDN denoiser, RGBA output,
  TILEPATHCPU, FILESAVER TXT export and re-render.
- No GPU in the build machine: OpenCL/CUDA engines were only checked to fail cleanly
  (`No hardware device selected or available`).

## Known issues in this build
- Loading binary serialized files fails: a resume file (`.rsm`, from
  `periodicsave.resumerendering.period`) or a FILESAVER `BIN` `.bcf` gives
  `ERROR: class version St10unique_ptrIN3slg12RenderConfig...`. Writing `.rsm` works,
  reading it does not. FILESAVER `TXT` is fine.

## Licences
LuxCoreRender: Apache-2.0 (`COPYING.txt` in the tarball). Open Image Denoise and oneTBB:
Apache-2.0.
