---
name: luxcore-cli-start
description: Use when you need the LuxCore command-line renderer (luxcoreconsole) in a fresh session - fetch and unpack the prebuilt Linux binary from an orphan luxcore-cli-<date> branch, verify it, smoke-test it, or rebuild it from source (including the offline Conan workaround for sandboxed containers).
---

# Getting luxcoreconsole running

`luxcoreconsole` is LuxCoreRender's batch renderer: it reads a render config (`.cfg`), renders
until a halt condition is met, writes the film outputs (PNG/EXR...) and exits. It is not on
`PATH` in a fresh container.

## 1. Get the prebuilt binary (fast path, ~1 min)

Prebuilt Linux x86_64 builds live on orphan branches named `luxcore-cli-<YYYY-MM-DD>` of
`brdmaker/LuxCore` (one per build date; take the newest). Each branch holds
`luxcore-cli-linux-x86_64.tar.xz`, `SHA256SUMS`, `README.md` and a snapshot of these skills.

```bash
REPO=/home/user/LuxCore                       # any clone of brdmaker/LuxCore
git -C $REPO fetch origin 'refs/heads/luxcore-cli-*:refs/remotes/origin/luxcore-cli-*'
BR=$(git -C $REPO branch -r --list 'origin/luxcore-cli-*' | sort | tail -1 | tr -d ' ')
echo "using $BR"
BIN=$HOME/luxcore-bin; mkdir -p $BIN
git -C $REPO show $BR:luxcore-cli-linux-x86_64.tar.xz > $BIN/luxcore-cli-linux-x86_64.tar.xz
git -C $REPO show $BR:SHA256SUMS > $BIN/SHA256SUMS
(cd $BIN && sha256sum -c SHA256SUMS)          # must print: OK
tar -xJf $BIN/luxcore-cli-linux-x86_64.tar.xz -C $BIN
export LUXCORE=$BIN/luxcore-cli-linux-x86_64/bin/luxcoreconsole
export PATH=$(dirname $LUXCORE):$PATH
luxcoreconsole -h                             # prints usage; exit 0
cat $BIN/luxcore-cli-linux-x86_64/BUILDINFO.txt
```

No repo clone? `git clone --depth 1 --branch <branch> --single-branch <url>` the orphan branch
alone (it has no source history, only the package).

The package is self-contained: `bin/luxcoreconsole` finds its bundled `lib/` (Open Image
Denoise, oneTBB) through `RPATH=$ORIGIN/../lib`, so keep `bin/` and `lib/` side by side.
System needs: glibc >= 2.38, libstdc++ from gcc 13+ (`GLIBCXX_3.4.31`), `libgomp1`
(Ubuntu 24.04 / Debian 13 or newer). If `ldd bin/luxcoreconsole | grep "not found"` shows
`libgomp`, run `apt-get install -y libgomp1`.

The line `CUDA disabled: CUDA driver or nvrtc library not found` at start-up is normal on a
machine without an NVIDIA GPU; CPU engines work. Never commit the binary to a source branch.

## 2. Smoke test (10 s)

```bash
cd /home/user/LuxCore                         # the shipped scenes use repo-root-relative paths
luxcoreconsole -D renderengine.type PATHCPU -D batch.haltspp 32 \
  -D film.outputs.0.filename /tmp/cornell.png -w 320 -e 320 scenes/cornell/cornell.cfg
```
Expect progress lines, then `Done.` and exit code 0; open `/tmp/cornell.png` (a Cornell box).
`cornell.cfg` also declares other outputs (`denoised.png`, `cornell_ALBEDO.png`,
`cornell_AVG_SHADING_NORMAL.exr`) that land in the current directory: delete them, don't
commit them.

## 3. Rebuild from source (when no branch exists or the source changed)

About 25 minutes on 4 cores. Needs gcc 14, CMake >= 3.29, Conan 2, Python `wheel` CLI,
patchelf. The precompiled dependency bundle comes from
`github.com/LuxCoreRender/LuxCoreDeps/releases` (version in `build-system/build-settings.json`).

```bash
apt-get install -y g++-14 patchelf
pip install --user --break-system-packages "cmake>=3.29,<4" wheel conan
pip install --user --break-system-packages --force-reinstall wheel   # makes ~/.local/bin/wheel exist
export PATH=$HOME/.local/bin:$PATH CC=gcc-14 CXX=g++-14 DEPS_WITHOUT_SUDO=1
cd /home/user/LuxCore
make deps                 # downloads ~240 MB, restores the Conan cache, writes out/dependencies
make luxcoreconsole       # Release; result: out/install/Release/bin/luxcoreconsole
```

**Sandboxed container (Conan Center blocked, proxy 403 on center2.conan.io):** `make deps`
then fails with `Package 'b2/[>=5.2 <6]' not resolved` (or `cmake/...`, `nasm/...`). Every real
package is already prebuilt in the downloaded cache; Conan only wants the *recipes* of build
tools it will never run. Put this wrapper first on `PATH` as `conan`, then rerun `make deps`:

```python
#!/usr/bin/env python3
# Offline Conan wrapper: disables the remote and stubs build-tool recipes that are never built.
import re, subprocess, sys, os
C = os.path.expanduser("~/.local/bin/conan")
STUB = os.path.expanduser("~/conanwrap/stub")   # folder holding the conanfile.py below
subprocess.run([C, "remote", "disable", "conancenter"], capture_output=True)
args = sys.argv[1:]
if not args or args[0] != "install":
    sys.exit(subprocess.call([C] + args))
for _ in range(40):
    p = subprocess.run([C] + args, capture_output=True, text=True)
    out = p.stdout + p.stderr
    m = re.search(r"Package '([^/']+)/([^']+)' not resolved", out)
    if p.returncode == 0 or not m:
        sys.stdout.write(out); sys.exit(p.returncode)
    name, ver = m.groups()
    if ver.startswith("["):
        lo = re.search(r">=?\s*([0-9][0-9.]*)", ver); ver = lo.group(1) if lo else "1.0.0"
    subprocess.run([C, "export", STUB, "--name", name, "--version", ver], capture_output=True)
sys.stdout.write(out); sys.exit(1)
```
with `~/conanwrap/stub/conanfile.py`:
```python
from conan import ConanFile
class ToolStub(ConanFile):
    package_type = "application"
    settings = "os", "arch"
```
(`mkdir -p ~/conanwrap/stub`, save the wrapper as `~/conanwrap/conan`, `chmod +x`, and
`export PATH=~/conanwrap:$PATH`.) The `SIGNATURE CHECKING ERROR` warning from `gh attestation`
is harmless in the sandbox.

### Package a build for an orphan branch
`make luxcoreconsole` installs only the executable. Bundle the shared libraries next to it:
```bash
P=/tmp/pkg/luxcore-cli-linux-x86_64; mkdir -p $P/bin $P/lib
cp out/install/Release/bin/luxcoreconsole $P/bin/ && strip $P/bin/luxcoreconsole
D=out/dependencies/full_deploy/host
cp -P $D/oidn/*/Release/x86_64/lib/libLuxOpenImageDenoise*.so* $D/onetbb/*/Release/x86_64/lib/libtbb*.so* $P/lib/
for l in $P/lib/*.so.*; do [ -L $l ] || patchelf --set-rpath '$ORIGIN' $l; done
cp COPYING.txt $P/   # plus a BUILDINFO.txt: commit, date, compiler, deps version
ldd $P/bin/luxcoreconsole | grep "not found"     # must print nothing
(cd /tmp/pkg && tar -cJf luxcore-cli-linux-x86_64.tar.xz luxcore-cli-linux-x86_64 && sha256sum luxcore-cli-linux-x86_64.tar.xz > SHA256SUMS)
```
Then commit tarball + `SHA256SUMS` + `README.md` to a new orphan branch
`luxcore-cli-$(date +%F)` (`git switch --orphan ...` in a separate worktree) and push it.
Keep each file under GitHub's 100 MB limit (the xz tarball is ~70 MB).

## Next
- Running renders, flags, halt conditions, outputs, troubleshooting: `luxcore-cli-render`.
- Writing `.cfg` / `.scn` files: `luxcore-scene-format` (with `reference.md`).
- Photoreal pictures of CAD parts (STL from SolidCraft etc.): `luxcore-render-cad-part`.
