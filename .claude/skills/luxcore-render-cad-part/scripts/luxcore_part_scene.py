#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Turn one or more STL/PLY parts into a ready-to-render LuxCore studio scene.

Writes into OUT_DIR: part_<n>.ply (binary PLY, flat-shaded), scene.scn, render.cfg.
Render with:  luxcoreconsole -d OUT_DIR render.cfg      (writes OUT_DIR/render.png)

Stdlib only. STL may be ASCII or binary; units are kept as they are (CAD STL is
usually mm). Z is up in LuxCore; use --up y for Y-up exports.

Examples
  luxcore_part_scene.py part.stl --out /tmp/r --material aluminium
  luxcore_part_scene.py body.stl:plastic-black screw.stl:steel --out /tmp/r --view front
"""

import argparse
import math
import os
import shutil
import struct
import sys

# name -> list of (property suffix, value) for scene.materials.<id>.*
MATERIALS = {
    "aluminium": [("type", "metal2"), ("preset", "aluminium"),
                  ("uroughness", "0.08"), ("vroughness", "0.08")],
    "aluminium-brushed": [("type", "metal2"), ("preset", "aluminium"),
                          ("uroughness", "0.25"), ("vroughness", "0.04")],
    "steel": [("type", "metal2"), ("n", "2.87 2.95 2.65"), ("k", "3.12 2.93 2.81"),
              ("uroughness", "0.12"), ("vroughness", "0.12")],
    "steel-polished": [("type", "metal2"), ("n", "2.87 2.95 2.65"), ("k", "3.12 2.93 2.81"),
                       ("uroughness", "0.02"), ("vroughness", "0.02")],
    "brass": [("type", "metal2"), ("n", "0.444 0.527 1.094"), ("k", "3.695 2.765 1.829"),
              ("uroughness", "0.08"), ("vroughness", "0.08")],
    "copper": [("type", "metal2"), ("preset", "copper"),
               ("uroughness", "0.08"), ("vroughness", "0.08")],
    "gold": [("type", "metal2"), ("preset", "gold"),
             ("uroughness", "0.05"), ("vroughness", "0.05")],
    "anodized-black": [("type", "glossy2"), ("kd", "0.015 0.015 0.017"), ("ks", "0.04 0.04 0.04"),
                       ("uroughness", "0.18"), ("vroughness", "0.18")],
    "plastic-black": [("type", "glossy2"), ("kd", "0.02 0.02 0.02"), ("ks", "0.04 0.04 0.04"),
                      ("uroughness", "0.08"), ("vroughness", "0.08")],
    "plastic-white": [("type", "glossy2"), ("kd", "0.75 0.75 0.73"), ("ks", "0.04 0.04 0.04"),
                      ("uroughness", "0.08"), ("vroughness", "0.08")],
    "plastic-grey": [("type", "glossy2"), ("kd", "0.25 0.25 0.25"), ("ks", "0.04 0.04 0.04"),
                     ("uroughness", "0.08"), ("vroughness", "0.08")],
    "plastic-red": [("type", "glossy2"), ("kd", "0.6 0.04 0.03"), ("ks", "0.04 0.04 0.04"),
                    ("uroughness", "0.08"), ("vroughness", "0.08")],
    "plastic-blue": [("type", "glossy2"), ("kd", "0.03 0.12 0.55"), ("ks", "0.04 0.04 0.04"),
                     ("uroughness", "0.08"), ("vroughness", "0.08")],
    "rubber": [("type", "roughmatte"), ("kd", "0.025 0.025 0.025"), ("sigma", "0.6")],
    "glass": [("type", "glass"), ("kr", "1 1 1"), ("kt", "1 1 1"), ("interiorior", "1.5")],
    "clay": [("type", "matte"), ("kd", "0.6 0.6 0.6")],
}

VIEWS = {  # direction from target to camera (Z up)
    "iso": (1.0, -1.0, 0.8),
    "iso-back": (-1.0, 1.0, 0.8),
    "front": (0.0, -1.0, 0.25),
    "back": (0.0, 1.0, 0.25),
    "right": (1.0, 0.0, 0.25),
    "left": (-1.0, 0.0, 0.25),
    "top": (0.0, -0.001, 1.0),
    "low": (1.0, -1.0, 0.15),
}


def read_stl(path):
    """Return a flat list of triangles [(v0, v1, v2), ...] from ASCII or binary STL."""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) >= 84:
        (count,) = struct.unpack_from("<I", data, 80)
        if 84 + count * 50 == len(data):
            tris = []
            for i in range(count):
                vals = struct.unpack_from("<12f", data, 84 + i * 50)
                tris.append((vals[3:6], vals[6:9], vals[9:12]))
            return tris
    text = data.decode("ascii", errors="replace")
    verts = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "vertex":
            verts.append(tuple(float(x) for x in parts[1:4]))
    if not verts or len(verts) % 3:
        raise ValueError(f"{path}: not a readable STL")
    return [tuple(verts[i:i + 3]) for i in range(0, len(verts), 3)]


def read_ply_triangles(path):
    """Minimal PLY reader (ascii / binary_little_endian, float xyz, int/uint index lists)."""
    with open(path, "rb") as f:
        header = []
        while True:
            line = f.readline().decode("ascii").strip()
            header.append(line)
            if line == "end_header":
                break
        body = f.read()
    fmt = next(h.split()[1] for h in header if h.startswith("format"))
    elements, cur = [], None
    for h in header:
        p = h.split()
        if p and p[0] == "element":
            cur = [p[1], int(p[2]), []]
            elements.append(cur)
        elif p and p[0] == "property" and cur is not None:
            cur[2].append(p[1:])
    sizes = {"char": "b", "uchar": "B", "int8": "b", "uint8": "B", "short": "h", "ushort": "H",
             "int16": "h", "uint16": "H", "int": "i", "uint": "I", "int32": "i", "uint32": "I",
             "float": "f", "float32": "f", "double": "d", "float64": "d"}
    verts, tris = [], []
    if fmt == "ascii":
        tokens = body.decode("ascii").split()
        pos = 0
        for name, count, props in elements:
            for _ in range(count):
                row = {}
                for prop in props:
                    if prop[0] == "list":
                        n = int(tokens[pos]); pos += 1
                        row[prop[3]] = [float(t) for t in tokens[pos:pos + n]]; pos += n
                    else:
                        row[prop[1]] = float(tokens[pos]); pos += 1
                if name == "vertex":
                    verts.append((row["x"], row["y"], row["z"]))
                elif name == "face":
                    idx = [int(i) for i in row.get("vertex_indices", row.get("vertex_index", []))]
                    for k in range(1, len(idx) - 1):
                        tris.append((idx[0], idx[k], idx[k + 1]))
    elif fmt == "binary_little_endian":
        pos = 0
        for name, count, props in elements:
            for _ in range(count):
                row = {}
                for prop in props:
                    if prop[0] == "list":
                        (n,) = struct.unpack_from("<" + sizes[prop[1]], body, pos)
                        pos += struct.calcsize(sizes[prop[1]])
                        c = sizes[prop[2]]
                        row[prop[3]] = struct.unpack_from(f"<{n}{c}", body, pos)
                        pos += n * struct.calcsize(c)
                    else:
                        c = sizes[prop[0]]
                        (row[prop[1]],) = struct.unpack_from("<" + c, body, pos)
                        pos += struct.calcsize(c)
                if name == "vertex":
                    verts.append((row["x"], row["y"], row["z"]))
                elif name == "face":
                    idx = list(row.get("vertex_indices", row.get("vertex_index", [])))
                    for k in range(1, len(idx) - 1):
                        tris.append((idx[0], idx[k], idx[k + 1]))
    else:
        raise ValueError(f"{path}: unsupported PLY format {fmt}")
    return [(verts[a], verts[b], verts[c]) for a, b, c in tris]


def face_normal(t):
    a, b, c = t
    u = [b[i] - a[i] for i in range(3)]
    v = [c[i] - a[i] for i in range(3)]
    n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
    ln = math.sqrt(sum(x * x for x in n))
    return [x / ln for x in n] if ln > 0 else [0.0, 0.0, 0.0], ln


def corner_normals(tris, crease_deg):
    """Per-corner normals: average the area-weighted normals of the faces that share the
    corner's position and lie within crease_deg of this face. Curved CAD faces (cylinders,
    fillets) render smooth, real edges stay sharp. crease_deg <= 0 gives flat shading."""
    fn = [face_normal(t) for t in tris]
    if crease_deg <= 0:
        return [[n, n, n] for n, _ in fn]
    cos_t = math.cos(math.radians(crease_deg))
    by_pos = {}
    for ti, t in enumerate(tris):
        for v in t:
            by_pos.setdefault((round(v[0], 5), round(v[1], 5), round(v[2], 5)), []).append(ti)
    out = []
    for ti, t in enumerate(tris):
        n0 = fn[ti][0]
        corners = []
        for v in t:
            acc = [0.0, 0.0, 0.0]
            for tj in by_pos[(round(v[0], 5), round(v[1], 5), round(v[2], 5))]:
                nj, area = fn[tj]
                if sum(n0[i] * nj[i] for i in range(3)) >= cos_t:
                    for i in range(3):
                        acc[i] += nj[i] * area
            la = math.sqrt(sum(x * x for x in acc))
            corners.append([x / la for x in acc] if la > 0 else n0)
        out.append(corners)
    return out


def write_ply(path, tris, crease_deg=30.0):
    """Binary PLY with three unshared vertices per triangle and crease-angle normals."""
    normals = corner_normals(tris, crease_deg)
    with open(path, "wb") as f:
        f.write((
            "ply\nformat binary_little_endian 1.0\ncomment written by luxcore_part_scene.py\n"
            f"element vertex {3 * len(tris)}\nproperty float x\nproperty float y\nproperty float z\n"
            "property float nx\nproperty float ny\nproperty float nz\n"
            f"element face {len(tris)}\nproperty list uchar int vertex_indices\nend_header\n"
        ).encode("ascii"))
        for t, ns in zip(tris, normals):
            for v, n in zip(t, ns):
                f.write(struct.pack("<6f", *v, *n))
        for i in range(len(tris)):
            f.write(struct.pack("<B3i", 3, 3 * i, 3 * i + 1, 3 * i + 2))


def y_up_to_z_up(tris):
    return [tuple((v[0], -v[2], v[1]) for v in t) for t in tris]


def fmt(*vals):
    return " ".join(f"{v:.6g}" for v in vals)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="+", help="FILE.stl|FILE.ply, optionally FILE:material")
    ap.add_argument("--out", required=True, help="output folder (created)")
    ap.add_argument("--material", default="aluminium", choices=sorted(MATERIALS),
                    help="material for parts without :material (default aluminium)")
    ap.add_argument("--view", default="iso", choices=sorted(VIEWS))
    ap.add_argument("--fov", type=float, default=30.0, help="perspective FOV in degrees")
    ap.add_argument("--zoom", type=float, default=1.0, help=">1 moves the camera closer")
    ap.add_argument("--crease", type=float, default=30.0,
                    help="smooth-shading crease angle in degrees (0 = flat facets)")
    ap.add_argument("--exposure", type=float, default=0.0,
                    help="TONEMAP_LINEAR scale; 0 = auto (TONEMAP_AUTOLINEAR)")
    ap.add_argument("--up", default="z", choices=["z", "y"], help="up axis of the input files")
    ap.add_argument("--width", type=int, default=1200)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--spp", type=int, default=256, help="batch.haltspp (0 = off)")
    ap.add_argument("--time", type=int, default=600, help="batch.halttime seconds (0 = off)")
    ap.add_argument("--noise", type=float, default=0.0,
                    help="batch.haltnoisethreshold, e.g. 0.02 (0 = off)")
    ap.add_argument("--floor", default=None, choices=["white", "grey", "shadowcatcher", "none"],
                    help="default: white, or shadowcatcher with --env-map")
    ap.add_argument("--env", default="studio", choices=["studio", "sky"],
                    help="studio = softboxes + dim fill, sky = sun and sky")
    ap.add_argument("--env-map", default=None, metavar="FILE",
                    help="equirectangular environment image (.exr/.hdr/.jpg/.png); replaces --env")
    ap.add_argument("--env-rotate", type=float, default=0.0,
                    help="rotate the environment map about Z, degrees")
    ap.add_argument("--env-gain", type=float, default=1.0, help="environment map brightness")
    ap.add_argument("--denoise", action="store_true", help="add INTEL_OIDN to the pipeline")
    ap.add_argument("--transparent", action="store_true",
                    help="also write render_alpha.png (RGBA); use with --floor shadowcatcher|none")
    ap.add_argument("--output", default="render.png", help="image name, relative to --out")
    a = ap.parse_args(argv)
    if a.env_map:
        a.env = "map"
    if a.floor is None:
        a.floor = "shadowcatcher" if a.env == "map" else "white"

    os.makedirs(a.out, exist_ok=True)
    parts = []
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    for n, spec in enumerate(a.parts):
        path, mat = spec, a.material
        if ":" in spec and spec.rsplit(":", 1)[1] in MATERIALS:
            path, mat = spec.rsplit(":", 1)
        ext = os.path.splitext(path)[1].lower()
        tris = read_stl(path) if ext == ".stl" else read_ply_triangles(path)
        if a.up == "y":
            tris = y_up_to_z_up(tris)
        if not tris:
            sys.exit(f"{path}: no triangles")
        for t in tris:
            for v in t:
                for i in range(3):
                    lo[i] = min(lo[i], v[i]); hi[i] = max(hi[i], v[i])
        ply = f"part_{n}.ply"
        write_ply(os.path.join(a.out, ply), tris, a.crease)
        parts.append((ply, mat, len(tris), path))

    center = [(lo[i] + hi[i]) / 2 for i in range(3)]
    size = [hi[i] - lo[i] for i in range(3)]
    radius = max(1e-9, 0.5 * math.sqrt(sum(s * s for s in size)))
    d = VIEWS[a.view]
    dl = math.sqrt(sum(c * c for c in d))
    d = [c / dl for c in d]
    aspect = a.width / a.height
    # LuxCore's FOV spans the LONGER image side (ProjectiveCamera::Update).
    t = math.tan(math.radians(a.fov) / 2)
    tan_x, tan_y = (t, t / aspect) if aspect >= 1 else (t * aspect, t)
    up_v = [0.0, 1.0, 0.0] if a.view == "top" else [0.0, 0.0, 1.0]
    up = fmt(*up_v)

    def cross(p, q):
        return [p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2], p[0] * q[1] - p[1] * q[0]]

    fwd = [-c for c in d]
    right = cross(fwd, up_v)
    rl = math.sqrt(sum(c * c for c in right))
    right = [c / rl for c in right]
    cam_up = cross(right, fwd)
    # Smallest distance at which every bounding-box corner is inside the frame.
    dist = 0.0
    margin = 1.05
    for cx in (lo[0], hi[0]):
        for cy in (lo[1], hi[1]):
            for cz in (lo[2], hi[2]):
                o = [cx - center[0], cy - center[1], cz - center[2]]
                x = abs(sum(o[i] * right[i] for i in range(3))) * margin
                y = abs(sum(o[i] * cam_up[i] for i in range(3))) * margin
                z = sum(o[i] * d[i] for i in range(3))  # towards the camera
                dist = max(dist, x / tan_x + z, y / tan_y + z)
    dist = max(dist, 1.5 * radius) / a.zoom
    eye = [center[i] + d[i] * dist for i in range(3)]

    floor_z = lo[2] - 1e-4 * radius
    F = 40 * radius
    used = sorted({m for _, m, _, _ in parts})

    s = ["# Generated by luxcore_part_scene.py. Z up, units as in the source files.",
         f"# bbox min {fmt(*lo)} max {fmt(*hi)} size {fmt(*size)}",
         "scene.camera.type = perspective",
         f"scene.camera.lookat.orig = {fmt(*eye)}",
         f"scene.camera.lookat.target = {fmt(*center)}",
         f"scene.camera.up = {up}",
         f"scene.camera.fieldofview = {fmt(a.fov)}",
         f"scene.camera.cliphither = {fmt(dist * 1e-3)}",
         ""]
    for m in used:
        for k, v in MATERIALS[m]:
            s.append(f"scene.materials.mat_{m.replace('-', '_')}.{k} = {v}")
    if a.floor != "none":
        kd = {"white": "0.65 0.65 0.65", "grey": "0.35 0.35 0.35", "shadowcatcher": "0.8 0.8 0.8"}[a.floor]
        s.append(f"scene.materials.mat_floor.type = matte")
        s.append(f"scene.materials.mat_floor.kd = {kd}")
        if a.floor == "shadowcatcher":
            s.append("scene.materials.mat_floor.shadowcatcher.enable = 1")
    if a.env == "studio":
        s += ["scene.materials.mat_softbox.type = matte",
              "scene.materials.mat_softbox.kd = 0 0 0",
              "scene.materials.mat_softbox.emission = 1 1 1",
              "scene.materials.mat_softbox.emission.gain = 4 4 4",
              "scene.materials.mat_softbox.emission.id = 0"]
    s.append("")
    for n, (ply, mat, ntri, src) in enumerate(parts):
        s.append(f"# part {n}: {src} ({ntri} triangles)")
        s.append(f"scene.shapes.part_{n}.type = mesh")
        s.append(f"scene.shapes.part_{n}.ply = {ply}")
        s.append(f"scene.objects.part_{n}.shape = part_{n}")
        s.append(f"scene.objects.part_{n}.material = mat_{mat.replace('-', '_')}")
    if a.floor != "none":
        s += ["scene.shapes.floor.type = inlinedmesh",
              f"scene.shapes.floor.vertices = {fmt(center[0]-F, center[1]-F, floor_z, center[0]+F, center[1]-F, floor_z, center[0]+F, center[1]+F, floor_z, center[0]-F, center[1]+F, floor_z)}",
              "scene.shapes.floor.faces = 0 1 2 0 2 3",
              "scene.objects.floor.shape = floor",
              "scene.objects.floor.material = mat_floor"]
    s.append("")
    if a.env == "studio":
        # Two softboxes (key: upper left-front, rim: upper right-back), facing the part.
        def softbox(name, direction, size_scale):
            dd = [c / math.sqrt(sum(x * x for x in direction)) for c in direction]
            c = [center[i] + dd[i] * radius * 4 for i in range(3)]
            # Orthonormal basis with normal pointing at the part.
            nrm = [-x for x in dd]
            tmp = [0, 0, 1] if abs(nrm[2]) < 0.9 else [1, 0, 0]
            u = [nrm[1]*tmp[2]-nrm[2]*tmp[1], nrm[2]*tmp[0]-nrm[0]*tmp[2], nrm[0]*tmp[1]-nrm[1]*tmp[0]]
            ul = math.sqrt(sum(x * x for x in u)); u = [x / ul for x in u]
            w = [nrm[1]*u[2]-nrm[2]*u[1], nrm[2]*u[0]-nrm[0]*u[2], nrm[0]*u[1]-nrm[1]*u[0]]
            h = radius * size_scale
            pts = []
            for su, sw in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                pts += [c[i] + su * h * u[i] + sw * h * w[i] for i in range(3)]
            # Winding so the geometric normal faces the part (emission is one-sided).
            return [f"scene.shapes.{name}.type = inlinedmesh",
                    f"scene.shapes.{name}.vertices = {fmt(*pts)}",
                    f"scene.shapes.{name}.faces = 0 1 2 0 2 3",
                    f"scene.objects.{name}.shape = {name}",
                    f"scene.objects.{name}.material = mat_softbox",
                    f"scene.objects.{name}.camerainvisible = 1"]
        s += softbox("softbox_key", (-1.0, -0.6, 1.3), 1.2)
        s += softbox("softbox_rim", (1.2, 1.0, 1.0), 1.0)
        s += ["scene.lights.fill.type = constantinfinite",
              "scene.lights.fill.color = 1 1 1",
              "scene.lights.fill.gain = 0.3 0.3 0.3",
              "scene.lights.fill.id = 1"]
    elif a.env == "map":
        # Copy the map next to the scene so the folder is self-contained (paths resolve via -d).
        ext = os.path.splitext(a.env_map)[1].lower()
        env_name = "environment" + ext
        shutil.copyfile(a.env_map, os.path.join(a.out, env_name))
        # LuxCore removes gamma 2.2 from every image by default; HDR data is already linear.
        gamma = "1" if ext in (".exr", ".hdr") else "2.2"
        r = math.radians(a.env_rotate)
        cr, sr = math.cos(r), math.sin(r)
        s += ["scene.lights.env.type = infinite",
              f"scene.lights.env.file = {env_name}",
              f"scene.lights.env.gamma = {gamma}",
              f"scene.lights.env.gain = {fmt(a.env_gain, a.env_gain, a.env_gain)}",
              # column-major rotation about Z
              f"scene.lights.env.transformation = {fmt(cr, sr, 0, 0, -sr, cr, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)}",
              "scene.lights.env.id = 1"]
    else:
        s += ["scene.lights.sky.type = sky2",
              "scene.lights.sky.dir = -0.5 -0.7 0.6",
              "scene.lights.sky.turbidity = 2.5",
              "scene.lights.sky.id = 1",
              # sun/sky are ~3e4x brighter than the studio rig (measured): scale so --exposure means the same
              "scene.lights.sky.gain = 3e-05 3e-05 3e-05",
              "scene.lights.sun.type = sun",
              "scene.lights.sun.dir = -0.5 -0.7 0.6",
              "scene.lights.sun.turbidity = 2.5",
              "scene.lights.sun.gain = 3e-05 3e-05 3e-05",
              "scene.lights.sun.id = 0"]
    with open(os.path.join(a.out, "scene.scn"), "w", encoding="utf-8") as f:
        f.write("\n".join(s) + "\n")

    c = ["# Generated by luxcore_part_scene.py. Run: luxcoreconsole -d <this folder> render.cfg",
         "scene.file = scene.scn",
         "renderengine.type = PATHCPU",
         "sampler.type = SOBOL",
         f"film.width = {a.width}",
         f"film.height = {a.height}",
         "path.pathdepth.total = 8",
         "path.pathdepth.diffuse = 4",
         "path.pathdepth.glossy = 6",
         "path.pathdepth.specular = 8",
         "path.clamping.variance.maxvalue = 10",
         f"scene.epsilon.min = {fmt(max(1e-6, radius * 1e-6))}",
         f"scene.epsilon.max = {fmt(max(1e-3, radius * 1e-2))}",
         f"batch.halttime = {a.time}",
         f"batch.haltspp = {a.spp}"]
    if a.noise > 0:
        c.append(f"batch.haltnoisethreshold = {fmt(a.noise)}")
    step = 0
    if a.denoise:
        c.append(f"film.imagepipelines.0.{step}.type = INTEL_OIDN"); step += 1
    if a.exposure > 0:
        c += [f"film.imagepipelines.0.{step}.type = TONEMAP_LINEAR",
              f"film.imagepipelines.0.{step}.scale = {fmt(a.exposure)}"]
    else:
        c.append(f"film.imagepipelines.0.{step}.type = TONEMAP_AUTOLINEAR")
    c += [
          f"film.imagepipelines.0.{step + 1}.type = GAMMA_CORRECTION",
          f"film.imagepipelines.0.{step + 1}.value = 2.2",
          "film.outputs.0.type = RGB_IMAGEPIPELINE",
          "film.outputs.0.index = 0",
          f"film.outputs.0.filename = {a.output}"]
    if a.denoise:
        c += ["film.outputs.1.type = ALBEDO", "film.outputs.1.filename = albedo.exr",
              "film.outputs.2.type = AVG_SHADING_NORMAL", "film.outputs.2.filename = normal.exr"]
    if a.transparent:
        stem = os.path.splitext(a.output)[0]
        c += ["film.outputs.3.type = RGBA_IMAGEPIPELINE", "film.outputs.3.index = 0",
              f"film.outputs.3.filename = {stem}_alpha.png"]
    with open(os.path.join(a.out, "render.cfg"), "w", encoding="utf-8") as f:
        f.write("\n".join(c) + "\n")

    print(f"bbox size {fmt(*size)}  center {fmt(*center)}  radius {radius:.4g}")
    for ply, mat, ntri, src in parts:
        print(f"{src} -> {ply} ({ntri} triangles, {mat})")
    print(f"wrote {a.out}/scene.scn and {a.out}/render.cfg")
    print(f"render: luxcoreconsole -d {a.out} render.cfg")


if __name__ == "__main__":
    main()
