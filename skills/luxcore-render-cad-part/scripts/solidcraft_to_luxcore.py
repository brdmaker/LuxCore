#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Render a SolidCraft part or assembly in LuxCore with the materials it was modelled with.

Reads everything through solidcraft-cli (no SolidCraft code is linked or copied):
  run 1  the script (or design) + inspect.measure        -> body names, material, mass
         + file.export 3mf-tagged (one object per body)  -> triangles tagged with their B-rep face
  run 2  on the saved design: appearance.list once per body definition (placements of a
         component share it: "Name (Asm:1/Sub:4/Name:1)" is looked up as "Name")
                                                         -> resolved look of each body and face
A body whose look SolidCraft refuses is rendered with the placeholder and a warning.
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

render.json (optional; paths in it are relative to its folder). Everything a PBR look in
SolidCraft cannot say; every section is optional:
  {"bodies":      {"Shaft": "steel-satin",                      <- a finish name (-h of the
                   "Hood": {"type": "glossy2", ...}},              scene writer lists them), or
   "materials":   {"EN AW-6082-T6": "aluminium-blasted"},         raw LuxCore properties
   "appearances": {"Smoked glass": {"type": "glass", ...}},
   "bevel":       0.5  or  {"default": 0.5, "bodies": {"Screen": 0}},
   "emitters":    [{"body": "LED1", "face": [x, y, z], "color": "#20ff40", "gain": 40, "group": 3},
                   {"body": "Lcd", "face": [x, y, z], "image": "screen.png",
                    "frame": {"origin": [x, y, z], "u": [80, 0, 0], "v": [0, 45, 0]},
                    "gain": 3, "group": 2, "base": "display-black"}],
   "decals":      [{"body": "Housing", "face": [x, y, z], "image": "logo.png",
                    "frame": {"origin": [x, y, z], "u": [80, 0, 0], "v": [0, 0, 20]},
                    "offset": 0.02, "ink": "plastic-white"}]}
Material precedence: emitter > body > physical material > appearance name > converted look.
"body" matches a full body name or its definition name (then every placement). "face" is a
point on the face (world mm), as SolidCraft picks faces; without it the whole body emits.
"frame" places an image: origin = its lower-left corner, u = its width, v = its height (mm).
A decal is a copy of the face lifted by "offset" mm, mixing ink (coloured by the image) with
nothing by the image's alpha; use a PNG with transparency. Images with a frame apply to the
one placement nearest the point. "bevel" rounds convex edges at render time (mm).
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


# A body seen in a further placement of its component is reported as
# "Name (Assembly:1/Sub:4/Name:1)". Commands that read the body's definition (appearance.list)
# take the plain "Name"; every placement shares that definition's look and face order.
OCCURRENCE = re.compile(r"^(?P<base>.*\S) \((?P<path>[^()]*:\d+(?:/[^()]*:\d+)*)\)$")


def definition_name(name):
    m = OCCURRENCE.match(name)
    return m.group("base") if m else name


def closest_point_on_triangle(p, a, b, c):
    """Closest point to p on triangle abc (Ericson, Real-Time Collision Detection 5.1.5)."""
    def sub(x, y): return [x[i] - y[i] for i in range(3)]
    def dot(x, y): return sum(x[i] * y[i] for i in range(3))
    def add_s(x, y, t): return [x[i] + y[i] * t for i in range(3)]
    ab, ac, ap_ = sub(b, a), sub(c, a), sub(p, a)
    d1, d2 = dot(ab, ap_), dot(ac, ap_)
    if d1 <= 0 and d2 <= 0:
        return list(a)
    bp = sub(p, b); d3, d4 = dot(ab, bp), dot(ac, bp)
    if d3 >= 0 and d4 <= d3:
        return list(b)
    vc = d1 * d4 - d3 * d2
    if vc <= 0 and d1 >= 0 and d3 <= 0:
        return add_s(a, ab, d1 / (d1 - d3))
    cp = sub(p, c); d5, d6 = dot(ab, cp), dot(ac, cp)
    if d6 >= 0 and d5 <= d6:
        return list(c)
    vb = d5 * d2 - d1 * d6
    if vb <= 0 and d2 >= 0 and d6 <= 0:
        return add_s(a, ac, d2 / (d2 - d6))
    va = d3 * d6 - d5 * d4
    if va <= 0 and (d4 - d3) >= 0 and (d5 - d6) >= 0:
        return add_s(b, sub(c, b), (d4 - d3) / ((d4 - d3) + (d5 - d6)))
    den = 1.0 / (va + vb + vc)
    return add_s(add_s(a, ab, vb * den), ac, vc * den)


def closest_face(tagged, point):
    """(B-rep face index, distance) of the exported triangle nearest to a world point."""
    best = (None, math.inf)
    for tri, face in tagged:
        q = closest_point_on_triangle(point, *tri)
        d = math.dist(q, point)
        if d < best[1]:
            best = (face, d)
    return best


def frame_uv(p, frame):
    """Texture coordinates of world point p in an image frame {origin, u, v} (mm): origin is the
    image's lower-left corner, u spans its width, v its height. LuxCore reads image row 0 at t=0
    (top), so t = 1 - v."""
    o, u, v = frame["origin"], frame["u"], frame["v"]
    d = [p[i] - o[i] for i in range(3)]
    uu = sum(x * x for x in u) or 1.0
    vv = sum(x * x for x in v) or 1.0
    return (sum(d[i] * u[i] for i in range(3)) / uu, 1.0 - sum(d[i] * v[i] for i in range(3)) / vv)


def color_value(c):
    """'#rrggbb' (sRGB) or [r, g, b] (linear) -> LuxCore colour string."""
    if isinstance(c, str):
        return " ".join(f"{x:.5g}" for x in hex_to_linear(c))
    return " ".join(f"{float(x):.5g}" for x in c)


def query_looks(names, design, cwd, tmp):
    """{definition name: appearance.list result}. A name SolidCraft rejects is dropped with a
    warning (its bodies render with the placeholder) instead of failing the whole export."""
    pending = list(dict.fromkeys(names))
    rejected = []
    for _ in range(len(pending) + 1):
        if not pending:
            break
        s = os.path.join(tmp, "looks.json")
        with open(s, "w", encoding="utf-8") as f:
            json.dump({"commands": [{"command": "appearance.list", "params": {"body": n}} for n in pending]}, f)
        out = os.path.join(tmp, "looks_r.json")
        p = subprocess.run([cli(), "run", s, "--in", design, "--results", "--json-out", out],
                           cwd=cwd, capture_output=True, text=True)
        if p.returncode == 0:
            with open(out, encoding="utf-8") as f:
                return dict(zip(pending, json.load(f))), rejected
        m = re.search(r"step (\d+) \(appearance\.list\)", p.stderr)
        if not m:
            sys.exit(f"solidcraft-cli appearance.list failed:\n{p.stderr.strip()}")
        bad = pending.pop(int(m.group(1)) - 1)
        rejected.append(bad)
        print(f"warning: SolidCraft rejects appearance.list for body `{bad}`: "
              f"{p.stderr.strip().splitlines()[-1]}; rendering it with the placeholder look",
              file=sys.stderr)
    return {}, rejected


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
        # Run 1: build, measure, export every body as a tagged 3MF (an object per body, placements in
        # world coordinates), save. Each solidcraft-cli run rebuilds the model, so do as much as
        # possible in this one.
        mf = os.path.join(tmp, "bodies.3mf")
        s1 = os.path.join(tmp, "run1.json")
        with open(s1, "w", encoding="utf-8") as f:
            json.dump({"commands": commands + [
                {"command": "inspect.measure", "params": {}},
                {"command": "file.export", "params": {"path": mf, "format": "3mf-tagged",
                                                      "quality": a.quality}}]}, f)
        args = ["run", s1, "--results", "--json-out", os.path.join(tmp, "r1.json"), "--save", design]
        if in_file:
            args += ["--in", in_file]
        run_cli(args, cwd)
        with open(os.path.join(tmp, "r1.json"), encoding="utf-8") as f:
            measure = json.load(f)[-2]
        bodies = [b for b in measure["bodies"]
                  if not a.bodies or b["name"] in a.bodies or definition_name(b["name"]) in a.bodies]
        if not bodies:
            sys.exit("no bodies to render")
        names = [b["name"] for b in bodies]

        meshes = read_tagged_3mf(mf)
        # Run 2: looks, once per body definition (placements share it).
        by_def, rejected = query_looks([definition_name(n) for n in names], design, cwd, tmp)
        looks = [by_def.get(definition_name(n), {}) for n in names]

        base_dir = os.path.dirname(os.path.abspath(a.overrides)) if a.overrides else os.getcwd()
        preloaded, specs, manifest, mat_ids = {}, [], [], {}

        def material_for(spec):
            """A finish/material name from luxcore_part_scene, or a dict of LuxCore properties."""
            if isinstance(spec, str):
                if spec not in lps.MATERIALS:
                    sys.exit(f"unknown finish `{spec}`; known: {', '.join(sorted(lps.MATERIALS))}")
                return spec
            props = spec if isinstance(spec, list) else list(spec.items())
            pk = json.dumps(props)
            if pk not in mat_ids:
                mat_ids[pk] = f"sc_m{len(mat_ids)}"
                lps.MATERIALS[mat_ids[pk]] = props
            return mat_ids[pk]

        def image_texture(tid, path, alpha=False):
            src_img = path if os.path.isabs(path) else os.path.join(base_dir, path)
            if not os.path.isfile(src_img):
                sys.exit(f"image not found: {src_img}")
            dst = f"img_{tid}{os.path.splitext(src_img)[1].lower()}"
            lps.COPY_FILES[dst] = src_img
            props = [("type", "imagemap"), ("file", dst), ("wrap", "black")]
            props += [("channel", "alpha"), ("gamma", "1")] if alpha else [("gamma", "2.2")]
            lps.TEXTURES[tid] = props
            return tid

        def matches(spec_body, name):
            return spec_body in (name, definition_name(name))

        def body_scale(tagged):
            lo = [min(v[i] for t, _ in tagged for v in t) for i in range(3)]
            hi = [max(v[i] for t, _ in tagged for v in t) for i in range(3)]
            return math.dist(lo, hi)

        # Bevel per body: render.json "bevel": R or {"default": R, "bodies": {name: R}}.
        bevel_cfg = overrides.get("bevel", {})
        if not isinstance(bevel_cfg, dict):
            bevel_cfg = {"default": bevel_cfg}

        # Emitters and decals that name a face by a point: resolve to (body index, face index).
        def resolve_face(item, what):
            cands = [(bi, b["name"]) for bi, b in enumerate(bodies)
                     if matches(item["body"], b["name"]) and meshes.get(b["name"])]
            if not cands:
                sys.exit(f"{what}: no body `{item['body']}`")
            best = (None, None, math.inf)
            for bi, name in cands:
                face, dist = closest_face(meshes[name], item["face"])
                if dist < best[2]:
                    best = (bi, face, dist)
            bi, face, dist = best
            if dist > 0.01 * max(1.0, body_scale(meshes[bodies[bi]["name"]])):
                print(f"warning: {what}: point {item['face']} is {dist:.3g} from body "
                      f"`{bodies[bi]['name']}`; using its nearest face {face}", file=sys.stderr)
            return bi, face, dist

        emitters = []
        for ei, em in enumerate(overrides.get("emitters", [])):
            e = {"spec": em, "index": ei, "face": None, "only_body": None}
            if "face" in em:
                bi, face, _ = resolve_face(em, f"emitter {ei}")
                e["face"] = face
                if "image" in em:  # an image is placed in world coordinates: that instance only
                    e["only_body"] = bi
            if "image" in em and ("frame" not in em or "face" not in em):
                sys.exit(f"emitter {ei}: an image needs `face` (a point on it) and `frame`")
            props = list((lps.MATERIALS[material_for(em["base"])] if "base" in em else
                          lps.MATERIALS["display-black"] if "image" in em else
                          [("type", "matte"), ("kd", "0 0 0")]))
            props = [(k, v) for k, v in props if not k.startswith("emission")]
            if "image" in em:
                props.append(("emission", image_texture(f"tx_emit{ei}", em["image"])))
            else:
                props.append(("emission", color_value(em.get("color", [1, 1, 1]))))
            g = float(em.get("gain", 1.0 if "image" in em else 10.0))
            props += [("emission.gain", f"{g:g} {g:g} {g:g}"), ("emission.id", str(int(em.get("group", 2))))]
            e["material"] = material_for(props)
            emitters.append(e)

        decals = []
        for di, dc in enumerate(overrides.get("decals", [])):
            for k in ("body", "face", "image", "frame"):
                if k not in dc:
                    sys.exit(f"decal {di}: `{k}` is required (body, face point, image, frame)")
            bi, face, _ = resolve_face(dc, f"decal {di}")
            ink = list(lps.MATERIALS[material_for(dc["ink"])]) if "ink" in dc else \
                [("type", "glossy2"), ("ks", "0.04 0.04 0.04"), ("uroughness", "0.3"), ("vroughness", "0.3")]
            ink = [(k, v) for k, v in ink if k != "kd"] + [("kd", image_texture(f"tx_decal{di}", dc["image"]))]
            alpha = image_texture(f"tx_decal{di}_a", dc["image"], alpha=True)
            lps.HELPERS[f"hm_decal{di}_none"] = [("type", "null")]
            lps.HELPERS[f"hm_decal{di}_ink"] = ink
            mix = [("type", "mix"), ("material1", f"mat_hm_decal{di}_none"),
                   ("material2", f"mat_hm_decal{di}_ink"), ("amount", alpha)]
            mname = f"sc_decal{di}"
            lps.MATERIALS[mname] = mix
            decals.append({"spec": dc, "index": di, "body": bi, "face": face, "material": mname})

        for bi, (b, lk) in enumerate(zip(bodies, looks)):
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
            my_emitters = [e for e in emitters if matches(e["spec"]["body"], name)
                           and e["only_body"] in (None, bi)]
            groups = {}
            for (tri, face), nrm in zip(tagged, normals):
                look = face_looks.get(face, body_look)
                em = next((e for e in my_emitters if e["face"] in (None, face)), None)
                key = (json.dumps(look, sort_keys=True), em["index"] if em else None)
                g = groups.setdefault(key, (look, em, [], [], []))
                g[2].append(tri)
                g[3].append(nrm)
                if em and "frame" in em["spec"]:
                    g[4].append([frame_uv(v, em["spec"]["frame"]) for v in tri])
            bevel = bevel_cfg.get("bodies", {}).get(name, bevel_cfg.get("bodies", {}).get(
                definition_name(name), bevel_cfg.get("default")))
            for gi, (look, em, tris, nrms, uvs) in enumerate(groups.values()):
                if em:
                    mat_id, source, props = em["material"], f"emitter {em['index']}", lps.MATERIALS[em["material"]]
                else:
                    spec = (overrides.get("bodies", {}).get(name)
                            or overrides.get("bodies", {}).get(definition_name(name))
                            or overrides.get("materials", {}).get(b.get("material") or "")
                            or overrides.get("appearances", {}).get(look.get("name") or ""))
                    source = "override" if spec else "look"
                    mat_id = material_for(spec if spec else look_to_luxcore(look))
                    props = lps.MATERIALS[mat_id]
                key = f"body{bi}#{gi}"
                preloaded[key] = (tris, nrms, uvs) if uvs else (tris, nrms)
                if bevel is not None:
                    lps.PART_OPTIONS.setdefault(key, {})["bevel"] = float(bevel)
                specs.append(f"{key}:{mat_id}")
                manifest.append({"body": name, "group": gi, "triangles": len(tris), "part_key": key,
                                 "luxcore_material_id": f"mat_{mat_id.replace('-', '_')}",
                                 "physical_material": b.get("material"),
                                 "density_g_cm3": b.get("density_g_cm3"),
                                 "volume_mm3": b.get("volume_mm3"), "mass_g": b.get("mass_g"),
                                 "look": look, "luxcore_material": dict(props), "from": source})
            # Decals on this body: a copy of the face's triangles, lifted along the normal.
            for dc in [d for d in decals if d["body"] == bi]:
                off = float(dc["spec"].get("offset", 0.02))
                tris, nrms, uvs = [], [], []
                for (tri, face), nrm in zip(tagged, normals):
                    if face != dc["face"]:
                        continue
                    lifted = tuple(tuple(v[i] + n[i] * off for i in range(3)) for v, n in zip(tri, nrm))
                    tris.append(lifted)
                    nrms.append(nrm)
                    uvs.append([frame_uv(v, dc["spec"]["frame"]) for v in tri])
                key = f"decal{dc['index']}"
                preloaded[key] = (tris, nrms, uvs)
                lps.PART_OPTIONS[key] = {"bevel": 0.0}
                specs.append(f"{key}:{dc['material']}")
                manifest.append({"body": name, "group": f"decal {dc['index']}", "triangles": len(tris),
                                 "part_key": key, "luxcore_material_id": f"mat_{dc['material']}",
                                 "physical_material": None, "density_g_cm3": None, "volume_mm3": None,
                                 "mass_g": None, "look": {"name": f"decal {dc['spec']['image']}"},
                                 "luxcore_material": dict(lps.MATERIALS[dc["material"]]), "from": "decal"})
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
        default_mat = sorted({m["body"] for m in manifest
                              if m["from"] != "decal" and m["physical_material"] in (None, "Default")})
        if default_mat:
            print("warning: physical material is SolidCraft's placeholder 'Default' (1.29 g/cm3), so "
                  "mass is not real: " + ", ".join(default_mat), file=sys.stderr)
        print(f"wrote {a.out}/materials.json")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
