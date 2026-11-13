# luxcoreconsole, Linux x86_64 build of 2026-11-13

Prebuilt LuxCoreRender command-line renderer (`luxcoreconsole`). This orphan branch holds
only the build output and its docs, no source history. It replaces
`luxcore-cli-2026-11-11` (same source plus one fix, below).

| File | What |
|---|---|
| `luxcore-cli-linux-x86_64.tar.xz` | `bin/luxcoreconsole`, `lib/` (Open Image Denoise 2.5.0, oneTBB 2023.0.0), `COPYING.txt`, `BUILDINFO.txt` |
| `SHA256SUMS` | SHA-256 of the tarball |
| `skills/` | agent skills for this build (snapshot of `.claude/skills` on `claude/bold-gauss-8rzxny`), including `solidcraft-to-luxcore`, the exporter scripts and `luxcore-render-cad-part/examples/device` |

## Build
- Source: `brdmaker/LuxCore` commit `8e83502` on `claude/bold-gauss-8rzxny` (= `main` at
  `64a7632` + the bevel fix), LuxCore 2.11.2, Release.
- Ubuntu 24.04, gcc 14.2, CMake 3.31, Conan 2.32, LuxCoreDeps v2.2.4 (prebuilt).
- `make deps && make luxcoreconsole`; shared libraries bundled next to the binary
  (`RPATH=$ORIGIN/../lib`); binary stripped.

## What changed since 2026-11-11
- **Fixed: bevel shape crash.** A `bevel` shape whose source mesh has no convex edge (a flat
  panel, a concave fold, a piece split off a solid) segfaulted while parsing the scene.
  Regression test `BevelShapeWithoutConvexEdges` (`pyunittests/.../shapes/testsingle.py`):
  fails without the fix, passes with it.

## Use
```bash
git fetch origin luxcore-cli-2026-11-13
git show origin/luxcore-cli-2026-11-13:luxcore-cli-linux-x86_64.tar.xz > luxcore-cli-linux-x86_64.tar.xz
git show origin/luxcore-cli-2026-11-13:SHA256SUMS > SHA256SUMS && sha256sum -c SHA256SUMS
tar -xJf luxcore-cli-linux-x86_64.tar.xz
luxcore-cli-linux-x86_64/bin/luxcoreconsole -h
```
Needs glibc >= 2.38, libstdc++ with `GLIBCXX_3.4.31` and `libgomp1` (Ubuntu 24.04,
Debian 13 or newer). See `skills/luxcore-cli-start/SKILL.md`.

## Tested
- Bevel regression test (above); the crash scenes from the device example.
- `skills/luxcore-render-cad-part/examples/device`: SolidCraft script → exporter → render
  (finishes, bevel, display image, LEDs, decal), 800x560, 64 spp, 30 s on 4 threads.
- The brdmot PSU enclosure with its inserted KiCad board (280 bodies, 760k triangles).
- No GPU in the build machine: OpenCL/CUDA engines not exercised.

## Known issues
- Loading binary serialized files still fails (unchanged from 2026-11-11): a resume file
  (`.rsm`) or a FILESAVER `BIN` `.bcf` gives `ERROR: class version St10unique_ptr...`.
  FILESAVER `TXT` is fine.
- `pyluxcore` (not shipped here) can segfault at Python interpreter exit after a successful
  render.

## Licences
LuxCoreRender: Apache-2.0 (`COPYING.txt` in the tarball). Open Image Denoise and oneTBB:
Apache-2.0.
