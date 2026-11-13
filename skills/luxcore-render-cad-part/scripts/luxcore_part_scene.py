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
import json
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


def _noise(name, feature_mm, amplitude_mm, octaves=6):
    """A 3D fbm height texture in world space (no UVs needed), scaled to amplitude_mm."""
    s = 1.0 / feature_mm
    return [(f"{name}_fbm", [("type", "fbm"), ("octaves", str(octaves)), ("roughness", "0.6"),
                             ("mapping.type", "globalmapping3d"),
                             ("mapping.transformation", f"{s:g} 0 0 0 0 {s:g} 0 0 0 0 {s:g} 0 0 0 0 1")]),
            (name, [("type", "scale"), ("texture1", f"{name}_fbm"), ("texture2", f"{amplitude_mm:g}")])]


def _rough_var(name, feature_mm, lo, hi):
    """Roughness varying between lo and hi with a world-space fbm (no UVs needed)."""
    s = 1.0 / feature_mm
    return [(f"{name}_fbm", [("type", "fbm"), ("octaves", "4"), ("roughness", "0.5"),
                             ("mapping.type", "globalmapping3d"),
                             ("mapping.transformation", f"{s:g} 0 0 0 0 {s:g} 0 0 0 0 {s:g} 0 0 0 0 1")]),
            (f"{name}_abs", [("type", "abs"), ("texture", f"{name}_fbm")]),
            (name, [("type", "mix"), ("amount", f"{name}_abs"), ("texture1", f"{lo:g}"), ("texture2", f"{hi:g}")])]


# Finishes: materials that need textures or helper materials. Units are mm (CAD scenes).
# name -> {"textures": [(id, props)], "helpers": [(id, props)], "material": props}
FINISHES = {
    "aluminium-blasted": {
        "textures": _noise("tx_blast", 0.06, 0.002),
        "material": [("type", "metal2"), ("preset", "aluminium"), ("uroughness", "0.32"),
                     ("vroughness", "0.32"), ("bumptex", "tx_blast")]},
    "steel-satin": {  # world-space roughness variation; true machining marks need UVs
        "textures": _rough_var("tx_satr", 6.0, 0.10, 0.17),
        "material": [("type", "metal2"), ("n", "2.87 2.95 2.65"), ("k", "3.12 2.93 2.81"),
                     ("uroughness", "tx_machr"), ("vroughness", "tx_machr")]},
    "steel-blackoxide": {
        "textures": _rough_var("tx_oxr", 4.0, 0.25, 0.45),
        "material": [("type", "metal2"), ("n", "1.9 1.9 1.9"), ("k", "0.6 0.6 0.62"),
                     ("uroughness", "tx_oxr"), ("vroughness", "tx_oxr")]},
    "powder-black": {
        "textures": _noise("tx_peel", 0.6, 0.012),
        "material": [("type", "glossy2"), ("kd", "0.025 0.025 0.027"), ("ks", "0.05 0.05 0.05"),
                     ("uroughness", "0.3"), ("vroughness", "0.3"), ("bumptex", "tx_peel")]},
    "plastic-textured-black": {
        "textures": _noise("tx_vdi", 0.08, 0.003),
        "material": [("type", "glossy2"), ("kd", "0.02 0.02 0.02"), ("ks", "0.04 0.04 0.04"),
                     ("uroughness", "0.28"), ("vroughness", "0.28"), ("bumptex", "tx_vdi")]},
    "anodized-black-coated": {
        "helpers": [("hm_anod_base", [("type", "matte"), ("kd", "0.012 0.012 0.014")])],
        "material": [("type", "glossycoating"), ("base", "mat_hm_anod_base"), ("ks", "0.05 0.05 0.05"),
                     ("uroughness", "0.12"), ("vroughness", "0.12")]},
    "soldermask-green": {
        "material": [("type", "glossy2"), ("kd", "0.015 0.14 0.045"), ("ks", "0.06 0.06 0.06"),
                     ("uroughness", "0.08"), ("vroughness", "0.08")]},
    "glass-frosted": {  # converges slowly: >= 512 spp or --denoise
        "material": [("type", "roughglass"), ("kr", "1 1 1"), ("kt", "0.95 0.95 0.95"),
                     ("interiorior", "1.5"), ("uroughness", "0.3"), ("vroughness", "0.3")]},
    "display-black": {
        "material": [("type", "glossy2"), ("kd", "0 0 0"), ("ks", "0.04 0.04 0.04"),
                     ("uroughness", "0.01"), ("vroughness", "0.01")]},
}

# Registries other tools (solidcraft_to_luxcore.py) fill before calling main(). The scene gets
# only what the used materials reference (followed through textures and helpers).
TEXTURES = {}        # texture id -> props, emitted in insertion order before all materials
HELPERS = {}         # helper material id (without mat_) -> props, emitted before part materials
COPY_FILES = {}      # file name in --out -> source path (images used by textures)
PART_OPTIONS = {}    # part path/key -> {"bevel": mm, "camerainvisible": 0|1}


def register_finish(name, finish):
    """Make a FINISHES entry usable as a material name."""
    for tid, props in finish.get("textures", []):
        TEXTURES.setdefault(tid, props)
    for hid, props in finish.get("helpers", []):
        HELPERS.setdefault(hid, props)
    MATERIALS[name] = finish["material"]


for _n, _f in FINISHES.items():
    register_finish(_n, _f)


# ---------------------------------------------------------------------------------------------
# Finish families: a surface type that takes any colour (plastics, paints, coatings).
# Spec forms (anywhere a material name is accepted):
#   "plastic-satin"                    the family's default colour
#   "plastic-satin/RAL3020"            "/RAL nnnn", "/#rrggbb" or "/rrggbb" (sRGB)
#   {"finish": "plastic-fdm", "color": "#c03020", "layer": 0.2}   (render.json)
# In solidcraft_to_luxcore.py a dict without "color" takes the colour of the SolidCraft look.
# ---------------------------------------------------------------------------------------------

# RAL Classic, approximate sRGB for screen use (the official values are CIELab under D65; a
# printed or painted sample is the reference, not these numbers).
RAL = {
    "1003": "#F9A800", "1013": "#E3D9C6", "1015": "#E6D2B5", "1021": "#EEC900", "1023": "#F0CA00",
    "2004": "#E75B12", "3000": "#A72920", "3020": "#BB1E10", "5002": "#00387B", "5010": "#004F7C",
    "5012": "#0089B6", "5015": "#007CB0", "5017": "#005B8C", "6005": "#0F4336", "6011": "#5C7E4B",
    "6018": "#48A43F", "6029": "#006F3D", "7001": "#8F999F", "7004": "#9EA0A1", "7016": "#383E42",
    "7021": "#2F3234", "7024": "#45494E", "7032": "#B9B9A8", "7035": "#CBD0CC", "7040": "#9DA3A6",
    "7042": "#8F9695", "7047": "#D0D0D0", "9002": "#D7D5CB", "9003": "#ECECE7", "9004": "#2B2B2C",
    "9005": "#0A0A0D", "9006": "#A1A1A0", "9007": "#878581", "9010": "#F1ECE1", "9011": "#27292B",
    "9016": "#F1F0EA", "9017": "#2A292A",
}


def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def parse_color(c):
    """'#rrggbb' / 'rrggbb' (sRGB), 'RAL 7035' / 'RAL7035', or [r, g, b] linear -> linear tuple."""
    if isinstance(c, (list, tuple)):
        return tuple(float(x) for x in c[:3])
    t = str(c).strip()
    m = t.upper().replace(" ", "").replace("_", "")
    if m.startswith("RAL"):
        if m[3:] not in RAL:
            raise ValueError(f"RAL {m[3:]} is not in the table; give its colour as #rrggbb")
        t = RAL[m[3:]]
    t = t.lstrip("#")
    if len(t) != 6 or any(ch not in "0123456789abcdefABCDEF" for ch in t):
        raise ValueError(f"not a colour: {c!r} (use #rrggbb, RAL nnnn or [r, g, b])")
    return tuple(srgb_to_linear(int(t[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def _rgb(c, k=1.0):
    return " ".join(f"{min(1.0, x * k):.5g}" for x in c)


def _glossy(c, rough, ks=0.045):
    return [("type", "glossy2"), ("kd", _rgb(c)), ("ks", f"{ks:g} {ks:g} {ks:g}"),
            ("uroughness", f"{rough:g}"), ("vroughness", f"{rough:g}")]


def _layer_lines(uid, layer, depth, axis):
    """Bump for FDM layer lines: a triangle wave of the world coordinate along `axis`."""
    ch = {"x": 0, "y": 1, "z": 2}[axis]
    off = round(10000.0 / layer) * layer  # fmod is negative below 0: shift, keeping the phase
    return [(f"{uid}_pos", [("type", "position")]),
            (f"{uid}_h", [("type", "splitfloat3"), ("texture", f"{uid}_pos"), ("channel", str(ch))]),
            (f"{uid}_hs", [("type", "add"), ("texture1", f"{uid}_h"), ("texture2", f"{off:g}")]),
            (f"{uid}_m", [("type", "modulo"), ("texture", f"{uid}_hs"), ("modulo", f"{layer:g}")]),
            (f"{uid}_f", [("type", "scale"), ("texture1", f"{uid}_m"), ("texture2", f"{1.0 / layer:g}")]),
            (f"{uid}_c", [("type", "subtract"), ("texture1", f"{uid}_f"), ("texture2", "0.5")]),
            (f"{uid}_a", [("type", "abs"), ("texture", f"{uid}_c")]),
            (uid, [("type", "scale"), ("texture1", f"{uid}_a"), ("texture2", f"{2 * depth:g}")])]


def _fam_plastic(rough, bump=None):
    def build(uid, c, p):
        tex = []
        mat = _glossy(c, float(p.get("roughness", rough)))
        if bump:
            feat, amp = float(p.get("texture", bump[0])), float(p.get("depth", bump[1]))
            tex = _noise(f"{uid}_b", feat, amp)
            mat.append(("bumptex", f"{uid}_b"))
        return {"textures": tex, "material": mat}
    return build


def _fam_fdm(uid, c, p):
    layer, depth = float(p.get("layer", 0.2)), float(p.get("depth", 0.03))
    tex = _layer_lines(f"{uid}_ll", layer, depth, str(p.get("axis", "z")).lower())
    return {"textures": tex, "material": _glossy(c, float(p.get("roughness", 0.25))) + [("bumptex", f"{uid}_ll")]}


def _fam_translucent(uid, c, p):
    r = float(p.get("roughness", 0.15))
    return {"material": [("type", "glossytranslucent"), ("kd", _rgb(c)), ("kt", _rgb(c, 0.8)),
                         ("ks", "0.04 0.04 0.04"), ("uroughness", f"{r:g}"), ("vroughness", f"{r:g}")]}


def _fam_clear(uid, c, p):
    ior, r = float(p.get("ior", 1.49)), float(p.get("roughness", 0.0))
    if r > 0:
        return {"material": [("type", "roughglass"), ("kr", "1 1 1"), ("kt", _rgb(c)),
                             ("interiorior", f"{ior:g}"), ("uroughness", f"{r:g}"), ("vroughness", f"{r:g}")]}
    return {"material": [("type", "glass"), ("kr", "1 1 1"), ("kt", _rgb(c)), ("interiorior", f"{ior:g}")]}


def _fam_paint_gloss(uid, c, p):
    r = float(p.get("roughness", 0.015))
    return {"helpers": [(f"{uid}_base", [("type", "matte"), ("kd", _rgb(c))])],
            "material": [("type", "glossycoating"), ("base", f"mat_{uid}_base"), ("ks", "0.05 0.05 0.05"),
                         ("uroughness", f"{r:g}"), ("vroughness", f"{r:g}")]}


def _fam_paint_metallic(uid, c, p):
    r = float(p.get("roughness", 0.015))
    return {"helpers": [(f"{uid}_base", [("type", "disney"), ("basecolor", _rgb(c)), ("metallic", "0.75"),
                                          ("roughness", f"{float(p.get('flake', 0.35)):g}")])],
            "material": [("type", "glossycoating"), ("base", f"mat_{uid}_base"), ("ks", "0.05 0.05 0.05"),
                         ("uroughness", f"{r:g}"), ("vroughness", f"{r:g}")]}


def _fam_powder(rough, feat, amp, octaves=6):
    def build(uid, c, p):
        f, a = float(p.get("texture", feat)), float(p.get("depth", amp))
        return {"textures": _noise(f"{uid}_b", f, a, octaves),
                "material": _glossy(c, float(p.get("roughness", rough)), 0.05) + [("bumptex", f"{uid}_b")]}
    return build


# name -> (builder(uid, linear colour, params), default colour, one-line description)
FAMILIES = {
    "plastic-gloss": (_fam_plastic(0.02), "RAL9005", "polished-mould plastic (SPI A), mirror-like highlights"),
    "plastic-satin": (_fam_plastic(0.12), "RAL9005", "satin plastic (SPI B/C)"),
    "plastic-matte": (_fam_plastic(0.4), "RAL9005", "matte plastic, no texture"),
    "plastic-textured": (_fam_plastic(0.3, (0.08, 0.006)), "RAL9005",
                         "moulded texture (VDI 3400 / MT-like); texture = grain size mm, depth mm"),
    "plastic-fdm": (_fam_fdm, "RAL9005", "3D-printed (FDM) with layer lines; layer mm, axis x|y|z, depth mm"),
    "plastic-translucent": (_fam_translucent, "#f0f0f0", "translucent plastic (PP natural, diffusers, light pipes)"),
    "plastic-clear": (_fam_clear, "#ffffff", "clear plastic (PMMA ior 1.49, PC 1.58); colour = tint; roughness > 0 frosts it"),
    "paint-gloss": (_fam_paint_gloss, "RAL3020", "gloss paint / enamel: colour under a clear coat"),
    "paint-satin": (lambda uid, c, p: {"material": _glossy(c, float(p.get("roughness", 0.15)), 0.04)},
                    "RAL7035", "satin paint"),
    "paint-matte": (lambda uid, c, p: {"material": _glossy(c, float(p.get("roughness", 0.6)), 0.03)},
                    "RAL7035", "matte paint"),
    "paint-metallic": (_fam_paint_metallic, "RAL9006", "metallic paint (car paint): metallic base, clear coat"),
    "powder-coat": (_fam_powder(0.3, 0.6, 0.012), "RAL9005", "smooth powder coat with orange peel"),
    "powder-structure": (_fam_powder(0.45, 0.35, 0.06, 4), "RAL7016",
                         "structured / wrinkle powder coat (machine enclosures)"),
}

_resolved = {}


def resolve_material(spec, default_color=None):
    """Material name for a spec: a MATERIALS name, a family name with optional '/colour', or a
    dict {"finish": family, "color": ..., params}. Registers families on first use."""
    if isinstance(spec, str) and spec in MATERIALS:
        return spec
    if isinstance(spec, str):
        fam, _, col = spec.partition("/")
        params = {}
        if col:
            params["color"] = col if col.upper().startswith("RAL") or col.startswith("#") else "#" + col
    else:
        params = dict(spec)
        fam = params.pop("finish")
    if fam not in FAMILIES:
        raise ValueError(f"unknown material or finish `{fam}`; known: "
                         + ", ".join(sorted(MATERIALS)) + "; families: " + ", ".join(sorted(FAMILIES)))
    builder, dflt, _ = FAMILIES[fam]
    color = params.pop("color", None)
    if color is None:
        color = default_color if default_color is not None else dflt
    lin = parse_color(color)
    key = json.dumps([fam, [round(x, 5) for x in lin], sorted(params.items())])
    if key not in _resolved:
        uid = f"f{len(_resolved)}_{fam.replace('-', '_')}"
        register_finish(uid, builder(uid, lin, params))
        _resolved[key] = uid
    return _resolved[key]


def is_material_spec(name):
    try:
        resolve_material(name)
        return True
    except (ValueError, KeyError):
        return False


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


def write_ply(path, tris, crease_deg=30.0, normals=None, uvs=None):
    """Binary PLY with three unshared vertices per triangle, per-corner normals (given, or
    crease-angle normals) and optional per-corner texture coordinates (LuxCore reads `s t`)."""
    if normals is None:
        normals = corner_normals(tris, crease_deg)
    with open(path, "wb") as f:
        f.write((
            "ply\nformat binary_little_endian 1.0\ncomment written by luxcore_part_scene.py\n"
            f"element vertex {3 * len(tris)}\nproperty float x\nproperty float y\nproperty float z\n"
            "property float nx\nproperty float ny\nproperty float nz\n"
            + ("property float s\nproperty float t\n" if uvs is not None else "")
            + f"element face {len(tris)}\nproperty list uchar int vertex_indices\nend_header\n"
        ).encode("ascii"))
        if uvs is None:
            for t, ns in zip(tris, normals):
                for v, n in zip(t, ns):
                    f.write(struct.pack("<6f", *v, *n))
        else:
            for t, ns, us in zip(tris, normals, uvs):
                for v, n, uv in zip(t, ns, us):
                    f.write(struct.pack("<8f", *v, *n, *uv))
        for i in range(len(tris)):
            f.write(struct.pack("<B3i", 3, 3 * i, 3 * i + 1, 3 * i + 2))


def y_up_to_z_up(tris):
    return [tuple((v[0], -v[2], v[1]) for v in t) for t in tris]


def fmt(*vals):
    return " ".join(f"{v:.6g}" for v in vals)


def main(argv=None, preloaded=None):
    """preloaded: {path: (tris, corner_normals)} supplied by another tool (no file read)."""
    preloaded = preloaded or {}
    epilog = ("materials: " + ", ".join(sorted(m for m in MATERIALS if not m.startswith(("f", "sc_"))
                                                or m in FINISHES or m in ("gold", "glass")))
              + "\n\nfinish families (any colour: NAME/RAL7035, NAME/#c03020, NAME/c03020):\n"
              + "\n".join(f"  {n:20s} {d}" for n, (_, _, d) in sorted(FAMILIES.items())))
    ap = argparse.ArgumentParser(description=__doc__, epilog=epilog,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parts", nargs="+", help="FILE.stl|FILE.ply, optionally FILE:material")
    ap.add_argument("--out", required=True, help="output folder (created)")
    ap.add_argument("--material", default="aluminium",
                    help="material for parts without :material (default aluminium): a name below, "
                         "or a finish family with an optional colour, e.g. plastic-satin/RAL3020")
    ap.add_argument("--view", default="iso", choices=sorted(VIEWS))
    ap.add_argument("--fov", type=float, default=30.0, help="perspective FOV in degrees")
    ap.add_argument("--zoom", type=float, default=1.0, help=">1 moves the camera closer")
    ap.add_argument("--crease", type=float, default=30.0,
                    help="smooth-shading crease angle in degrees (0 = flat facets)")
    ap.add_argument("--exposure", type=float, default=0.0,
                    help="TONEMAP_LINEAR scale; 0 = auto (TONEMAP_AUTOLINEAR)")
    ap.add_argument("--bevel", type=float, default=0.0,
                    help="round every convex edge at render time with this radius (scene units, "
                         "mm for CAD); keep it below the smallest real feature. 0 = off")
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
        if ":" in spec and is_material_spec(spec.rsplit(":", 1)[1]):
            path, mat = spec.rsplit(":", 1)
        try:
            mat = resolve_material(mat)
        except ValueError as e:
            sys.exit(str(e))
        ext = os.path.splitext(path)[1].lower()
        normals = uvs = None
        if path in preloaded:
            tris, normals, *rest = preloaded[path]
            uvs = rest[0] if rest else None
        else:
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
        write_ply(os.path.join(a.out, ply), tris, a.crease, normals, uvs)
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
    # Textures first (LuxCore needs a texture defined before anything that names it), then
    # helper materials (bases of coatings, the two sides of a decal mix), then part materials.
    # Emit exactly what the used materials reference, followed recursively through helpers and
    # textures (a scale texture names its fbm, a mix material names its helpers).
    tex_ids, helper_ids = set(), set()
    todo = [MATERIALS[m] for m in used]
    while todo:
        for _, v in todo.pop():
            for tok in str(v).split():
                if tok in TEXTURES and tok not in tex_ids:
                    tex_ids.add(tok)
                    todo.append(TEXTURES[tok])
                elif tok.startswith("mat_") and tok[4:] in HELPERS and tok[4:] not in helper_ids:
                    helper_ids.add(tok[4:])
                    todo.append(HELPERS[tok[4:]])
    for tid in [t for t in TEXTURES if t in tex_ids]:
        for k, v in TEXTURES[tid]:
            s.append(f"scene.textures.{tid}.{k} = {v}")
    for h in [h for h in HELPERS if h in helper_ids]:
        for k, v in HELPERS[h]:
            s.append(f"scene.materials.mat_{h}.{k} = {v}")
    for dst, src_path in COPY_FILES.items():
        shutil.copyfile(src_path, os.path.join(a.out, dst))
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
        opts = PART_OPTIONS.get(src, {})
        bevel = opts.get("bevel", a.bevel)
        s.append(f"# part {n}: {src} ({ntri} triangles)")
        s.append(f"scene.shapes.part_{n}.type = mesh")
        s.append(f"scene.shapes.part_{n}.ply = {ply}")
        shape = f"part_{n}"
        if bevel and bevel > 0:
            s.append(f"scene.shapes.part_{n}_bevel.type = bevel")
            s.append(f"scene.shapes.part_{n}_bevel.source = part_{n}")
            s.append(f"scene.shapes.part_{n}_bevel.bevel.radius = {fmt(bevel)}")
            shape = f"part_{n}_bevel"
        s.append(f"scene.objects.part_{n}.shape = {shape}")
        if opts.get("camerainvisible"):
            s.append(f"scene.objects.part_{n}.camerainvisible = 1")
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
