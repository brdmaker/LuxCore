#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render a SolidCraft part or assembly in LuxCore with the materials it was modelled with.

Reads everything through solidcraft-cli (no SolidCraft code is linked or copied):
  run 1  the script (or design) + inspect.measure        -> body names, material, mass; saved design
  run 2  on that design: appearance.list per body        -> resolved look of each body and face
         + file.export 3mf-tagged (one object per body)  -> triangles tagged with their B-rep face
Then each body is split by look, normals are smoothed inside each B-rep face only (real CAD edges
stay sharp, curved faces stay smooth), SolidCraft's metal/roughness PBR look is converted to a
LuxCore `disney` material, and luxcore_part_scene.py writes the studio scene around it.

Usage
  solidcraft_to_luxcore.py part.json --out /tmp/r/part [--looks looks.json] [--overrides render.json] [scene options]
  luxcoreconsole -d /tmp/r/part render.cfg

Scene options (--view, --env, --env-map, --exposure, --denoise, --spp, ...) are passed to
luxcore_part_scene.py unchanged; run it with -h to list them. Set SOLIDCRAFT_CLI if
solidcraft-cli is not on PATH. For a script that opens files with relative paths (doc.open),
run from the script's folder or pass --cwd.

Overrides (optional JSON, for what a PBR look cannot say, e.g. measured metal n/k or glass):
  {"bodies":    {"Shaft": {"type": "metal2", "n": "2.87 2.95 2.65", "k": "3.12 2.93 2.81",
                           "uroughness": "0.05", "vroughness": "0.05"}},
   "materials": {"EN AW-6082-T6": {"type": "metal2", "preset": "aluminium", ...}},
   "appearances": {"Smoked glass": {"type": "glass", "kt": "0.4 0.4 0.4", "interiorior": "1.5"}}}
A body override wins over a material override, which wins over an appearance-name override,
which wins over the converted look. Values are LuxCore material properties (strings).
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import luxcore_part_scene as lps  # noqa: E402

FT_NS = "https://github.com/bherbruck/solidcraft/formats/3mf-face-tags/2026/10"
CORE_NS = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
DEFAULT_LOOK = {"color": "#a0a0a0", "opacity": 1.0, "pbr": None, "name": "(none)"}


def cli():
    return os.environ.get("SOLIDCRAFT_CLI") or shutil.which("solidcraft-cli") or "solidcraft-cli"


def run_cli(args, cwd):
    p = subprocess.run([cli()] + args, cwd=cwd, capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit(f"solidcraft-cli {' '.join(args)} failed:\n{p.stderr.strip() or p.stdout.strip()}")
    return p


def load_commands(path):
    """The source's commands: a script's own list, or a design's history via `script`."""
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return json.load(f)["commands"], None
    return [], path  # a .sc design or a STEP file: start from it with --in


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_to_linear(h):
    h = h.lstrip("#")
    return [srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4)]


def look_to_luxcore(look):
    """SolidCraft look {color, opacity, pbr{metallic, roughness, dielectric_ior}} -> LuxCore props."""
    rgb = hex_to_linear(look.get("color") or DEFAULT_LOOK["color"])
    col = " ".join(f"{x:.5g}" for x in rgb)
    pbr = look.get("pbr") or {}
    ior = float(pbr.get("dielectric_ior", 1.5))
    if float(look.get("opacity", 1.0)) < 1.0:
        # SolidCraft's alpha looks are not physical glass; this is the nearest LuxCore reading.
        return [("type", "glass"), ("kr", "1 1 1"), ("kt", col), ("interiorior", f"{ior:.4g}")]
    if not pbr:
        # Scalar (non-PBR) look: a plastic-like dielectric with its colour.
        return [("type", "disney"), ("basecolor", col), ("metallic", "0"),
                ("roughness", "0.5"), ("specular", "0.5")]
    spec = min(1.0, ((ior - 1) / (ior + 1)) ** 2 / 0.08)
    return [("type", "disney"), ("basecolor", col),
            ("metallic", f"{float(pbr.get('metallic', 0)):.4g}"),
            ("roughness", f"{float(pbr.get('roughness', 0.5)):.4g}"),
            ("specular", f"{spec:.4g}")]


def read_tagged_3mf(path):
    """{object name: [(tri, face_index), ...]} in world coordinates (build transforms applied)."""
    with zipfile.ZipFile(path) as z:
        model = next(n for n in z.namelist() if n.lower().endswith(".model"))
        root = ET.fromstring(z.read(model))
    ns = {"m": CORE_NS}
    objects = {}
    for obj in root.findall("m:resources/m:object", ns):
        mesh = obj.find("m:mesh", ns)
        if mesh is None:
            continue
        verts = [(float(v.get("x")), float(v.get("y")), float(v.get("z")))
                 for v in mesh.findall("m:vertices/m:vertex", ns)]
        tris = []
        for t in mesh.findall("m:triangles/m:triangle", ns):
            face = int(t.get(f"{{{FT_NS}}}face", "0"))
            tris.append(((verts[int(t.get("v1"))], verts[int(t.get("v2"))], verts[int(t.get("v3"))]), face))
        objects[obj.get("id")] = (obj.get("name") or f"object{obj.get('id')}", tris)
    out = {}
    for item in root.findall("m:build/m:item", ns):
        name, tris = objects[item.get("objectid")]
        tr = item.get("transform")
        if tr:
            m = [float(x) for x in tr.split()]  # 3MF: m00 m01 m02 m10 m11 m12 m20 m21 m22 m30 m31 m32

            def xf(v, m=m):
                return (v[0] * m[0] + v[1] * m[3] + v[2] * m[6] + m[9],
                        v[0] * m[1] + v[1] * m[4] + v[2] * m[7] + m[10],
                        v[0] * m[2] + v[1] * m[5] + v[2] * m[8] + m[11])
            tris = [(tuple(xf(v) for v in t), f) for t, f in tris]
        out.setdefault(name, []).extend(tris)
    return out


def face_normals(tagged):
    """Per-corner normals averaged only over triangles of the same B-rep face."""
    fn = []
    for t, _ in tagged:
        n, area = lps.face_normal(t)
        fn.append((n, area))
    acc = {}
    for (t, face), (n, area) in zip(tagged, fn):
        for v in t:
            k = (face, round(v[0], 6), round(v[1], 6), round(v[2], 6))
            a = acc.setdefault(k, [0.0, 0.0, 0.0])
            for i in range(3):
                a[i] += n[i] * area
    out = []
    for (t, face), (n, _) in zip(tagged, fn):
        corners = []
        for v in t:
            a = acc[(face, round(v[0], 6), round(v[1], 6), round(v[2], 6))]
            la = math.sqrt(sum(x * x for x in a))
            corners.append([x / la for x in a] if la > 0 else n)
        out.append(corners)
    return out


def ident(s):
    return re.sub(r"[^A-Za-z0-9_]", "_", s)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 add_help=True)
    ap.add_argument("source", help="SolidCraft script (.json), design (.sc) or STEP file")
    ap.add_argument("--out", required=True, help="output folder for the LuxCore scene")
    ap.add_argument("--overrides", help="render.json with LuxCore material overrides")
    ap.add_argument("--looks", help="extra SolidCraft script ({commands: [...]}) run after the source, "
                    "e.g. material.create/assign and appearance.assign for a STEP or a generated part")
    ap.add_argument("--bodies", nargs="*", help="only these bodies (default: all)")
    ap.add_argument("--quality", default="fine", choices=["standard", "fine", "finest"],
                    help="tessellation quality of the export (default fine)")
    ap.add_argument("--cwd", help="folder to run the script in (default: the script's folder)")
    a, scene_args = ap.parse_known_args(argv)

    src = os.path.abspath(a.source)
    cwd = os.path.abspath(a.cwd) if a.cwd else os.path.dirname(src)
    overrides = {}
    if a.overrides:
        with open(a.overrides, encoding="utf-8") as f:
            overrides = json.load(f)
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="sc2lux-")
    try:
        commands, in_file = load_commands(src)
        if a.looks:
            with open(a.looks, encoding="utf-8") as f:
                commands = commands + json.load(f)["commands"]
        design = os.path.join(tmp, "design.sc")
        # Run 1: build, measure, save.
        s1 = os.path.join(tmp, "run1.json")
        with open(s1, "w", encoding="utf-8") as f:
            json.dump({"commands": commands + [{"command": "inspect.measure", "params": {}}]}, f)
        args = ["run", s1, "--results", "--json-out", os.path.join(tmp, "r1.json"), "--save", design]
        if in_file:
            args += ["--in", in_file]
        run_cli(args, cwd)
        with open(os.path.join(tmp, "r1.json"), encoding="utf-8") as f:
            measure = json.load(f)[-1]
        bodies = [b for b in measure["bodies"] if not a.bodies or b["name"] in a.bodies]
        if not bodies:
            sys.exit("no bodies to render")
        names = [b["name"] for b in bodies]

        # Run 2: looks per body and one tagged 3MF with an object per body.
        mf = os.path.join(tmp, "bodies.3mf")
        cmds = [{"command": "appearance.list", "params": {"body": n}} for n in names]
        cmds.append({"command": "file.export", "params": {
            "path": mf, "format": "3mf-tagged", "bodies": names, "quality": a.quality}})
        s2 = os.path.join(tmp, "run2.json")
        with open(s2, "w", encoding="utf-8") as f:
            json.dump({"commands": cmds}, f)
        run_cli(["run", s2, "--in", design, "--results", "--json-out", os.path.join(tmp, "r2.json")], cwd)
        with open(os.path.join(tmp, "r2.json"), encoding="utf-8") as f:
            looks = json.load(f)[:len(names)]
        meshes = read_tagged_3mf(mf)

        preloaded, specs, manifest = {}, [], []
        for b, lk in zip(bodies, looks):
            name = b["name"]
            body_look = (lk.get("body") or {}).get("appearance") or None
            if body_look is None:
                rgb = (lk.get("body") or {}).get("color")
                body_look = dict(DEFAULT_LOOK)
                if rgb:  # the colour SolidCraft shows the body in (material default, imported paint)
                    body_look["color"] = "#" + "".join(f"{round(max(0, min(1, c)) * 255):02x}" for c in rgb[:3])
            face_looks = {fl["face"]: fl["appearance"] for fl in (lk.get("body") or {}).get("faces", [])
                          if fl.get("appearance")}
            tagged = meshes.get(name)
            if not tagged:
                print(f"warning: no mesh exported for body {name}", file=sys.stderr)
                continue
            normals = face_normals(tagged)
            groups = {}
            for (tri, face), nrm in zip(tagged, normals):
                look = face_looks.get(face, body_look)
                key = json.dumps(look, sort_keys=True)
                g = groups.setdefault(key, (look, [], []))
                g[1].append(tri)
                g[2].append(nrm)
            for gi, (look, tris, nrms) in enumerate(groups.values()):
                props = (overrides.get("bodies", {}).get(name)
                         or overrides.get("materials", {}).get(b.get("material") or "")
                         or overrides.get("appearances", {}).get(look.get("name") or ""))
                source = "override" if props else "look"
                props = list(props.items()) if props else look_to_luxcore(look)
                mat_id = ident(f"sc_{name}_{gi}")
                lps.MATERIALS[mat_id] = props
                key = f"{name}#{gi}"
                preloaded[key] = (tris, nrms)
                specs.append(f"{key}:{mat_id}")
                manifest.append({"body": name, "group": gi, "triangles": len(tris),
                                 "physical_material": b.get("material"),
                                 "density_g_cm3": b.get("density_g_cm3"),
                                 "volume_mm3": b.get("volume_mm3"), "mass_g": b.get("mass_g"),
                                 "look": look, "luxcore_material": dict(props), "from": source})
        lps.main(specs + ["--out", a.out] + scene_args, preloaded=preloaded)
        with open(os.path.join(a.out, "materials.json"), "w", encoding="utf-8") as f:
            json.dump({"source": os.path.basename(src), "parts": manifest}, f, indent=1)
        for m in manifest:
            lm = m["luxcore_material"]
            print(f"{m['body']}[{m['group']}]: {m['look'].get('name')} {m['look'].get('color')} "
                  f"-> {lm.get('type')} ({m['from']}); material {m['physical_material']}, "
                  f"mass {m['mass_g'] if m['mass_g'] is None else round(m['mass_g'], 2)} g")
        no_look = sorted({m["body"] for m in manifest if m["look"].get("name") == "(none)" and m["from"] == "look"})
        if no_look:
            print("warning: no appearance assigned in SolidCraft, rendered as neutral grey: "
                  + ", ".join(no_look) + " (add appearance.assign/material looks, or --overrides)",
                  file=sys.stderr)
        default_mat = sorted({m["body"] for m in manifest if m["physical_material"] in (None, "Default")})
        if default_mat:
            print("warning: physical material is SolidCraft's placeholder 'Default' (1.29 g/cm3), so "
                  "mass is not real: " + ", ".join(default_mat), file=sys.stderr)
        print(f"wrote {a.out}/materials.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
