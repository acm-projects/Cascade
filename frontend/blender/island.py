"""Cascade's Landing island, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/island.py
    add  -- --preview   to also render preview pictures into frontend/blender/previews/

It makes:
    frontend/blender/island.blend      - open this in Blender to look at or edit the island
    frontend/public/models/island.glb  - the file the website loads (features/landing3d/islandScene.js)

What's in here: everything solid and still - the stepped ground and cliffs, trees, palms, plants, rocks,
mushrooms, flowers, grass tufts, pebbles, cliff stones and moss, stepping stones, the hut, the bridge,
the video screen's wooden frame, the dock and the campfire's stones and logs.
Soft shadows (ambient occlusion) are baked into the colors, which the browser can't do cheaply.

What stays in code (islandScene.js), because it moves or glows: the sea, the flowing river and waterfalls,
foam, clip cards, the screen's picture, crystals, vines, birds, clouds, flames, the boat and the animals.
Tree crowns and plants are separate objects named "Sway_..." with "sway" and "speed" custom properties,
so the website can make them sway.

The layout matches islandScene.js exactly (same sizes, river and positions), so the waterfalls and clip cards
still line up. Positions below are written in the website's coordinates (+y up, +z toward the viewer);
to_blender() turns them into Blender's (+z up).
"""
import math
import os
import random as random_module
import sys

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "island.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "island.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

# ---------- The layout (the same numbers as islandScene.js) ----------
HIGH, MID, LOW = 3.8, 2.4, 1.2
RIVER_MIN_X, RIVER_MAX_X = 0.5, 2.5
RIVER_X = (RIVER_MIN_X + RIVER_MAX_X) / 2
SEA_LEVEL = -0.6
ISLAND_RADIUS = 9
RIVER_BACK, RIVER_FRONT = -8, 8
EDGE = RIVER_FRONT + 0.5
GRID = ISLAND_RADIUS + 2

COLORS = {
    "grass": ["#72d93f", "#62cd36", "#82e046", "#58c433"],   # a little more vibrant than the code version
    "dirt": ["#9a6a3c", "#8d5f35"],
    "rock": ["#6f6a68", "#65615f", "#77716c"],
    "deepRock": ["#4d4f58", "#454751"],
    "leaves": ["#2dbd4f", "#1fa548", "#3fcd5c", "#179743"],
    "brightLeaves": ["#86d92a", "#a0e833"],
    "trunk": "#7a5230",
    "wood": "#a06f3c",
    "woodDark": "#70492a",
    "thatch": "#d9b35c",
    "cream": "#f6ecd2",
}

rng = random_module.Random(20261105)
random = rng.random


def pick(options):
    return options[int(random() * len(options))]


def ground_height(z):
    if z <= -2.5:
        return HIGH
    if z <= 2.5:
        return MID
    return LOW


def is_river(x):
    return RIVER_MIN_X < x < RIVER_MAX_X


def is_land(x, z):
    if is_river(x):
        return RIVER_BACK <= z <= RIVER_FRONT
    wobble = math.sin(x * 1.7 + z * 0.6) * 0.5 + math.cos(z * 1.9 - x * 0.4) * 0.4
    return math.hypot(x, z) <= ISLAND_RADIUS + wobble * 0.55


def is_busy(x, z):
    """Spots kept clear of grass and pebbles: the hut, the bridge, the campfire and the screen."""
    return ((-3.2 < x < -1 and -1.1 < z < 1.4) or (-0.2 < x < 3.2 and -0.3 < z < 0.9)
            or (-4.2 < x < -3 and -1.5 < z < -0.3) or (z < RIVER_BACK + 0.8 and -0.5 < x < 3.5))


# ---------- Coordinates: the website's (y up) to Blender's (z up) ----------
TO_BLENDER = Matrix.Rotation(math.radians(90), 4, "X")   # (x, y, z) -> (x, -z, y)


def srgb(hex_color):
    """'#rrggbb' -> linear RGBA, the way Blender stores colors."""
    out = []
    for i in (1, 3, 5):
        c = int(hex_color[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def transform(position=(0, 0, 0), rotation=(0, 0, 0), order="XYZ", scale=(1, 1, 1)):
    """A matrix in the website's coordinates (rotation order like three.js Euler orders)."""
    rx, ry, rz = rotation
    parts = {"X": Matrix.Rotation(rx, 4, "X"), "Y": Matrix.Rotation(ry, 4, "Y"), "Z": Matrix.Rotation(rz, 4, "Z")}
    rot = parts[order[0]] @ parts[order[1]] @ parts[order[2]]   # three.js: intrinsic, applied in the written order
    if isinstance(scale, (int, float)):
        scale = (scale, scale, scale)
    scale_matrix = Matrix.Diagonal((*scale, 1))
    return Matrix.Translation(Vector(position)) @ rot @ scale_matrix


# ---------- Shapes, in the website's coordinates: (vertices, faces) ----------

def box_shape(w, h, d):
    x, y, z = w / 2, h / 2, d / 2
    verts = [(-x, -y, -z), (x, -y, -z), (x, y, -z), (-x, y, -z), (-x, -y, z), (x, -y, z), (x, y, z), (-x, y, z)]
    faces = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]
    return verts, faces


def cylinder_shape(top, bottom, height, sides):
    verts, faces = [], []
    for i in range(sides):
        a = i / sides * math.tau
        verts.append((math.sin(a) * top, height / 2, math.cos(a) * top))
        verts.append((math.sin(a) * bottom, -height / 2, math.cos(a) * bottom))
    for i in range(sides):
        j = (i + 1) % sides
        faces.append((i * 2, j * 2, j * 2 + 1, i * 2 + 1))
    if top > 0:
        faces.append(tuple(i * 2 for i in range(sides))[::-1])
    faces.append(tuple(i * 2 + 1 for i in range(sides)))
    return verts, faces


def cone_shape(radius, height, sides):
    verts = [(math.sin(i / sides * math.tau) * radius, -height / 2, math.cos(i / sides * math.tau) * radius) for i in range(sides)]
    verts.append((0, height / 2, 0))
    faces = [(i, (i + 1) % sides, sides) for i in range(sides)]
    faces.append(tuple(range(sides))[::-1])
    return verts, faces


def icosphere_shape(radius, detail=1):
    mesh = bmesh.new()
    bmesh.ops.create_icosphere(mesh, subdivisions=detail + 1 if detail else 1, radius=radius)
    verts = [tuple(v.co) for v in mesh.verts]
    faces = [tuple(v.index for v in f.verts) for f in mesh.faces]
    mesh.free()
    return verts, faces


def lumpy_ball(radius, lumps=0.14, detail=1):
    verts, faces = icosphere_shape(radius, detail)
    moved = {}
    out = []
    for v in verts:
        key = tuple(round(c, 3) for c in v)
        if key not in moved:
            moved[key] = 1 + (random() - 0.5) * lumps * 2
        out.append(tuple(c * moved[key] for c in v))
    return out, faces


def leaf_shape(length, width, droop, steps=6):
    verts, faces = [], []
    for step in range(steps + 1):
        along = step / steps
        z = along * length
        y = -droop * along * along
        half = (width / 2) * math.sin(math.pi * min(1, along * 0.92 + 0.04)) * (1 - along * 0.2)
        verts += [(-half, y + half * 0.28, z), (0, y, z), (half, y + half * 0.28, z)]
        if step < steps:
            r = step * 3
            faces += [(r, r + 1, r + 4, r + 3), (r + 1, r + 2, r + 5, r + 4)]
    return verts, faces


# ---------- A mesh that collects many colored pieces ----------

class Piece:
    """Collects shapes (each with its own color) into one Blender mesh object."""

    def __init__(self, name, world=None, props=None):
        self.name = name
        self.world = world or Matrix.Identity(4)   # where this object sits, in the website's coordinates
        self.props = props or {}
        self.bm = bmesh.new()
        self.color_layer = self.bm.loops.layers.color.new("Col")

    def add(self, shape, color, local=None):
        """local: a transform() inside this object (website coordinates)."""
        verts, faces = shape
        matrix = TO_BLENDER @ (local or Matrix.Identity(4))
        made = [self.bm.verts.new(matrix @ Vector(v)) for v in verts]
        linear = srgb(color)
        for face in faces:
            try:
                f = self.bm.faces.new([made[i] for i in face])
            except ValueError:
                continue
            for loop in f.loops:
                loop[self.color_layer] = linear

    def finish(self, material, collection):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        mesh = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(mesh)
        self.bm.free()
        for poly in mesh.polygons:
            poly.use_smooth = False   # flat, low-poly look
        mesh.materials.append(material)
        obj = bpy.data.objects.new(self.name, mesh)
        collection.objects.link(obj)
        obj.matrix_world = TO_BLENDER @ self.world @ TO_BLENDER.inverted()
        for key, value in self.props.items():
            obj[key] = value
        return obj


STATIC = Piece("Island")
SWAYING = []   # Pieces that the website sways


def static(shape, color, *args, **kwargs):
    STATIC.add(shape, color, transform(*args, **kwargs))


def swaying(name, world, amount, speed):
    piece = Piece(name, world, {"sway": amount, "speed": speed})
    SWAYING.append(piece)
    return piece


def beveled_box(w, h, d, bevel=0.05):
    """A box with softly bevelled edges, like three.js RoundedBoxGeometry."""
    mesh = bmesh.new()
    bmesh.ops.create_cube(mesh, size=1)
    for v in mesh.verts:
        v.co = Vector((v.co.x * w, v.co.y * h, v.co.z * d))
    bmesh.ops.bevel(mesh, geom=list(mesh.edges), offset=min(bevel, w / 3, h / 3, d / 3), segments=1, affect="EDGES")
    verts = [tuple(v.co) for v in mesh.verts]
    faces = [tuple(v.index for v in f.verts) for f in mesh.faces]
    mesh.free()
    return verts, faces


# ---------- The ground ----------

def build_ground():
    for x in range(-GRID, GRID + 1):
        for z in range(-GRID, GRID + 1):
            if not is_land(x, z):
                continue
            river = is_river(x)
            top = ground_height(z) - (0.34 if river else 0)
            depth = SEA_LEVEL - 2
            mid = min(0.2, top - 0.9)

            def block(bottom, top_, color, size=1.001):
                height = top_ - bottom
                static(beveled_box(size, height, size, 0.05), color, (x, (top_ + bottom) / 2, z))

            block(depth, mid, pick(COLORS["deepRock"]))
            block(mid, top - (0 if river else 0.42), "#5e5a58" if river else pick(COLORS["rock"] if top - 1 > 1 else COLORS["dirt"]))
            if not river:
                block(top - 0.42, top + (random() - 0.5) * 0.05, pick(COLORS["grass"]), 1.012)


# ---------- The hut, the bridge, the screen's frame and the dock ----------

def build_hut_and_bridge():
    wood, dark = COLORS["wood"], COLORS["woodDark"]
    hut = transform((-2.1, MID, 0))

    def part(shape, color, position=(0, 0, 0), rotation=(0, 0, 0), order="XYZ"):
        STATIC.add(shape, color, hut @ transform(position, rotation, order))

    for x, z in [(-0.7, -0.7), (0.7, -0.7), (-0.7, 0.7), (0.7, 0.7)]:
        part(box_shape(0.14, 0.42, 0.14), dark, (x, 0.21, z))
    part(box_shape(1.8, 0.12, 1.8), dark, (0, 0.46, 0))
    part(beveled_box(1.26, 0.86, 1.26, 0.03), wood, (0, 0.94, 0))
    part(box_shape(0.34, 0.58, 0.02), "#3f2815", (0.1, 0.82, 0.64))
    part(cone_shape(1.32, 0.86, 4), COLORS["thatch"], (0, 1.8, 0), (0, math.pi / 4, 0))
    part(cone_shape(1.5, 0.38, 4), "#c99a45", (0, 1.5, 0), (0, math.pi / 4, 0))
    part(cone_shape(0.16, 0.22, 4), "#a7772f", (0, 2.3, 0), (0, math.pi / 4, 0))
    for x in (-0.25, 0.45):
        part(box_shape(0.06, 0.66, 0.06), dark, (x, 0.27, 1.07), (-0.59, 0, 0))
    for step in range(3):
        along = (step + 1) / 4
        part(box_shape(0.7, 0.04, 0.05), wood, (0.1, 0.52 - along * 0.52, 0.9 + along * 0.35))

    span = RIVER_MAX_X - RIVER_MIN_X + 0.7
    for i in range(9):
        along = i / 8
        px = RIVER_X - span / 2 + along * span
        py = MID + 0.1 + math.sin(along * math.pi) * 0.26
        static(box_shape(span / 9, 0.08, 0.92), wood if i % 2 else dark, (px, py, 0.3), (0, 0, math.cos(along * math.pi) * 0.34))
        if i % 2 == 0:
            for z in (-0.14, 0.74):
                static(box_shape(0.07, 0.34, 0.07), dark, (px, py + 0.18, z))


def build_screen_frame():
    group = transform((RIVER_X, HIGH, RIVER_BACK - 0.05))
    wood, dark = COLORS["wood"], COLORS["woodDark"]
    for x in (-1.72, 1.72):
        STATIC.add(box_shape(0.26, 2.7, 0.26), dark, group @ transform((x, 1.3, 0)))
    STATIC.add(beveled_box(3.5, 2.12, 0.22, 0.06), wood, group @ transform((0, 1.72, 0)))
    STATIC.add(box_shape(3.95, 0.16, 0.72), dark, group @ transform((0, 2.92, 0.04), (0.18, 0, 0)))


def build_dock():
    edge_x = GRID
    while edge_x > 0 and not is_land(edge_x, 4):
        edge_x -= 1
    start = edge_x + 0.5
    wood, dark = COLORS["wood"], COLORS["woodDark"]
    for i in range(8):
        static(box_shape(0.24, 0.06, 0.8), wood if i % 2 else dark, (start + 0.14 + i * 0.26, SEA_LEVEL + 0.3, 4))
    for x, z in [(start + 0.3, 3.65), (start + 0.3, 4.35), (start + 1.9, 3.65), (start + 1.9, 4.35)]:
        static(cylinder_shape(0.05, 0.05, 0.7, 6), dark, (x, SEA_LEVEL + 0.1, z))
    for z in (3.8, 4.2):
        static(box_shape(0.05, LOW - SEA_LEVEL + 0.1, 0.05), dark, (start + 0.03, (LOW + SEA_LEVEL + 0.5) / 2, z))
    y = SEA_LEVEL + 0.55
    while y < LOW:
        static(box_shape(0.05, 0.04, 0.45), wood, (start + 0.03, y, 4))
        y += 0.28


def build_campfire_base():
    fire = transform((-3.6, MID, -0.9))
    for i in range(8):
        angle = i / 8 * math.tau
        STATIC.add(lumpy_ball(0.08, 0.2, 0), pick(COLORS["rock"]), fire @ transform((math.cos(angle) * 0.28, 0.05, math.sin(angle) * 0.28)))
    for i in range(3):
        STATIC.add(cylinder_shape(0.045, 0.05, 0.42, 6), COLORS["woodDark"], fire @ transform((0, 0.08, 0), (math.pi / 2 - 0.25, i / 3 * math.pi, 0)))


# ---------- Plants ----------

def ground_place(x, z):
    return transform((x, ground_height(z), z))


def tree(x, z, size=1, fruit=None):
    group = ground_place(x, z)
    height = 1.5 * size
    STATIC.add(cylinder_shape(0.12 * size, 0.24 * size, height, 6), COLORS["trunk"], group @ transform((0, height / 2, 0)))
    crown = swaying(f"Sway_tree_{len(SWAYING)}", group @ transform((0, height, 0)), 0.022, 0.8 + random() * 0.4)
    blobs = [(0, 0.42, 0, 0.82), (0.48, 0.14, 0.14, 0.56), (-0.42, 0.2, 0.22, 0.6), (0.04, 0.2, -0.46, 0.56), (0.08, 0.92, 0.02, 0.5)]
    for bx, by, bz, radius in blobs:
        color = pick(COLORS["brightLeaves"]) if by > 0.8 else pick(COLORS["leaves"])
        crown.add(lumpy_ball(radius * size), color, transform((bx * size, by * size, bz * size)))
    if fruit:
        for i in range(7):
            bx, by, bz, radius = blobs[i % 4]
            angle = random() * math.tau
            lift = 0.15 + random() * 0.5
            out = math.sqrt(1 - lift * lift) * radius * size * 0.97
            crown.add(icosphere_shape(0.075 * size, 1), fruit,
                      transform((bx * size + math.cos(angle) * out, by * size + lift * radius * size * 0.97, bz * size + math.sin(angle) * out)))


def palm(x, z, size=1):
    group = ground_place(x, z)
    lean = height = 0
    for i in range(5):
        lean = i * 0.055 * size
        STATIC.add(cylinder_shape(0.1 * size * (1 - i * 0.08), 0.13 * size * (1 - i * 0.08), 0.5 * size, 6), COLORS["trunk"],
                   group @ transform((lean, height + 0.25 * size, 0), (0, 0, -0.1)))
        height += 0.47 * size
    crown = swaying(f"Sway_palm_{len(SWAYING)}", group @ transform((lean + 0.06, height, 0)), 0.05, 1.05 + random() * 0.5)
    leaf_colors = COLORS["leaves"] + COLORS["brightLeaves"]
    for i in range(8):
        crown.add(leaf_shape(1.35 * size, 0.46 * size, 0.72 * size), pick(leaf_colors), transform((0, 0, 0), (-0.34, i / 8 * math.tau, 0), "YXZ"))
    for cx, cz in [(0.11, 0.05), (-0.07, 0.1), (0.02, -0.12)]:
        crown.add(icosphere_shape(0.1 * size, 1), "#6b4423", transform((cx * size, -0.1 * size, cz * size)))


def leafy_plant(x, z, size=1, bright=False):
    plant = swaying(f"Sway_plant_{len(SWAYING)}", ground_place(x, z), 0.05, 1.3 + random() * 0.8)
    count = 6 + int(random() * 3)
    for i in range(count):
        color = COLORS["brightLeaves"][i % 2] if bright else COLORS["leaves"][i % 4]
        plant.add(leaf_shape((0.74 + random() * 0.32) * size, 0.42 * size, 0.42 * size), color,
                  transform((0, 0, 0), (-0.72, i / count * math.tau + random() * 0.4, 0), "YXZ"))


def rock(x, z, size=0.4):
    static(lumpy_ball(size, 0.2, 0), pick(COLORS["rock"]), (x, ground_height(z) + size * 0.32, z), scale=(1, 0.72, 1))


def mushroom(x, z, size=1):
    group = ground_place(x, z)
    STATIC.add(cylinder_shape(0.05 * size, 0.07 * size, 0.2 * size, 6), COLORS["cream"], group @ transform((0, 0.1 * size, 0)))
    cap_verts, cap_faces = [], []
    rings, sides = 3, 8
    for r in range(rings + 1):
        phi = r / rings * math.pi / 2
        for s in range(sides):
            a = s / sides * math.tau
            cap_verts.append((math.cos(phi) * math.sin(a) * 0.16 * size, math.sin(phi) * 0.16 * size, math.cos(phi) * math.cos(a) * 0.16 * size))
    for r in range(rings):
        for s in range(sides):
            n = (s + 1) % sides
            cap_faces.append((r * sides + s, r * sides + n, (r + 1) * sides + n, (r + 1) * sides + s))
    cap_faces.append(tuple(range(sides))[::-1])
    STATIC.add((cap_verts, cap_faces), "#ef5b4a", group @ transform((0, 0.18 * size, 0)))


def flowers(x, z, color):
    group = ground_place(x, z)
    for _ in range(5):
        STATIC.add(icosphere_shape(0.075, 0), color, group @ transform(((random() - 0.5) * 0.65, 0.09 + random() * 0.08, (random() - 0.5) * 0.65)))


def build_plants():
    # Back step
    tree(-3.6, -4.5, 1.3, "#f0912e")
    tree(-1.3, -5.2, 1.08)
    tree(-5.1, -2.9, 0.95)
    tree(5.4, -2.8, 0.85)
    palm(3.5, -3.2, 0.92)
    leafy_plant(-1.8, -3.15, 0.95, True)
    leafy_plant(3.3, -5.3, 0.85)
    rock(0, -3.2, 0.34)
    rock(2.95, -2.95, 0.28)
    mushroom(-0.4, -4.2, 1.3)
    flowers(-3, -3.1, "#ff9ec7")
    # The outer ring
    tree(-6.6, -5.4, 1.15)
    palm(-4.2, -7.6, 1.05)
    tree(4.3, -6.5, 1.1, "#f0912e")
    palm(7.2, -4.8, 1)
    leafy_plant(-7.8, -3.4, 1)
    leafy_plant(3.4, -8.2, 0.9, True)
    mushroom(-5.4, -6.8, 1.2)
    flowers(6, -6.2, "#ff9ec7")
    # Middle step
    tree(-5.5, 0.1, 1.22)
    palm(-3.1, 1.75, 1.15)
    palm(5.6, -0.6, 1.1)
    tree(4.1, -1.7, 0.9)
    leafy_plant(3.6, 1.8, 1.08, True)
    leafy_plant(-0.4, -1.7, 0.9)
    leafy_plant(-4.9, 2.1, 0.9)
    rock(-0.1, 1.8, 0.36)
    rock(3, -0.3, 0.26)
    mushroom(5.2, 2, 1.2)
    mushroom(5.5, 1.6, 0.85)
    flowers(-2.2, -1.5, "#ffd34d")
    tree(-8.2, -0.8, 1.1)
    palm(-8, 1.8, 1.05)
    tree(8.3, -1.2, 1)
    leafy_plant(8, 1.6, 1.05, True)
    rock(-6.8, 2.2, 0.34)
    flowers(7.2, 0.2, "#ffd34d")
    # Front step
    palm(-1.9, 5.1, 0.98)
    tree(4.6, 4.1, 0.86, "#e94a3f")
    leafy_plant(-3.4, 3.8, 1.2)
    leafy_plant(3.4, 5.5, 1.18, True)
    leafy_plant(-0.3, 3.3, 0.72, True)
    rock(0.05, 5.8, 0.3)
    rock(3.3, 3.2, 0.32)
    mushroom(-4.7, 3.2, 1.3)
    flowers(5.3, 3.1, "#ff9ec7")
    flowers(-2.4, 3.15, "#ffd34d")
    palm(-6.4, 5.2, 1.1)
    tree(-3.3, 6.9, 1)
    leafy_plant(-1.4, 7.8, 1.05, True)
    tree(5.4, 6.8, 0.95, "#e94a3f")
    leafy_plant(3.4, 7, 0.95)
    mushroom(-5.4, 7, 1.2)
    rock(6.6, 3.2, 0.3)


# ---------- Small details: grass, pebbles, blooms, cliff stones, moss, stepping stones ----------

def build_ground_details():
    tuft = cone_shape(0.035, 0.24, 4)
    pebble = icosphere_shape(0.07, 0)
    bloom = icosphere_shape(0.045, 0)
    unit = box_shape(1, 1, 1)
    for x in range(-GRID, GRID + 1):
        for z in range(-GRID, GRID + 1):
            if not is_land(x, z) or is_river(x):
                continue
            top = ground_height(z)
            tuft_count = 1 + int(random() * 2) if random() < 0.75 else 0
            for _ in range(tuft_count):
                tx, tz = x + (random() - 0.5) * 0.8, z + (random() - 0.5) * 0.8
                if is_busy(tx, tz):
                    continue
                shade = pick(["#4fbd36", "#60d03f", "#41ad33", "#7ddb48"])
                for blade in range(4):
                    angle = blade / 4 * math.tau + random()
                    static(tuft, shade, (tx + math.cos(angle) * 0.04, top + 0.1, tz + math.sin(angle) * 0.04),
                           (math.sin(angle) * 0.35, 0, -math.cos(angle) * 0.35), scale=(1, 0.8 + random() * 0.6, 1))
            if random() < 0.28:
                px, pz = x + (random() - 0.5) * 0.8, z + (random() - 0.5) * 0.8
                if not is_busy(px, pz):
                    static(pebble, pick(["#8d8984", "#a19c95", "#77736e"]), (px, top + 0.03, pz), (0, random() * 3, 0),
                           scale=(0.7 + random() * 0.8, 0.6, 0.7 + random() * 0.6))
            if random() < 0.22:
                fx, fz = x + (random() - 0.5) * 0.8, z + (random() - 0.5) * 0.8
                color = pick(["#ffffff", "#ffd34d", "#ff9ec7", "#c9a7ff"])
                if not is_busy(fx, fz):
                    for _ in range(3):
                        static(bloom, color, (fx + (random() - 0.5) * 0.25, top + 0.05, fz + (random() - 0.5) * 0.25))
            # Cliff walls you can see (facing +x and +z): stones poking out, moss hanging over the top
            for dx, dz in ((1, 0), (0, 1)):
                nx, nz = x + dx, z + dz
                below = (ground_height(nz) - 0.34 if is_river(nx) else ground_height(nz)) if is_land(nx, nz) else SEA_LEVEL
                drop = top - below
                if drop < 0.6:
                    continue

                def across(u):
                    return (x + 0.5 + 0.03, z + u) if dx else (x + u, z + 0.5 + 0.03)

                for _ in range(round(drop * 1.4 + random())):
                    sx, sz = across((random() - 0.5) * 0.8)
                    y = below + 0.15 + random() * max(0.05, drop - 0.75)
                    size = 0.07 + random() * 0.08
                    color = pick(["#7a5230", "#6e4a2b"]) if y > top - 0.9 else pick(["#5d5956", "#86817b", "#4f4c49"])
                    static(unit, color, (sx, y, sz), (0, math.pi / 2 if dx else 0, (random() - 0.5) * 0.6), scale=(size * 2.2, size, size * 0.8))
                if random() < 0.6:
                    for _ in range(1 + int(random() * 2)):
                        mx, mz = across((random() - 0.5) * 0.7)
                        length = 0.12 + random() * 0.32
                        static(unit, pick(["#3fae34", "#4ec03a", "#2f9e38"]), (mx - dx * 0.01, top - 0.4 - length / 2, mz - dz * 0.01),
                               (0, math.pi / 2 if dx else 0, 0), scale=(0.14 + random() * 0.26, length, 0.05))
    # Stepping stones from the hut's ladder to the bridge, and from the bridge on toward the trees
    stone = cylinder_shape(0.17, 0.19, 0.06, 7)

    def trail(start, end, count):
        for i in range(count):
            along = i / (count - 1)
            static(stone, pick(["#e3cf9b", "#d6bf86", "#ecdcae"]),
                   (start[0] + (end[0] - start[0]) * along + (random() - 0.5) * 0.12, MID + 0.02, start[1] + (end[1] - start[1]) * along + (random() - 0.5) * 0.12),
                   (0, random() * 3, 0), scale=(0.85 + random() * 0.3, 1, 0.85 + random() * 0.3))

    trail((-1.95, 1.55), (-0.05, 0.6), 6)
    trail((3.05, 0.6), (4.3, 1.3), 4)


# ---------- Material, baking and export ----------

def vertex_color_material():
    mat = bpy.data.materials.new("IslandVertexColor")
    mat.use_nodes = True
    mat.use_backface_culling = False   # leaves are thin sheets, so show both sides
    nodes = mat.node_tree.nodes
    shader = nodes["Principled BSDF"]
    shader.inputs["Roughness"].default_value = 0.85
    attribute = nodes.new("ShaderNodeVertexColor")
    attribute.layer_name = "Col"
    mat.node_tree.links.new(attribute.outputs["Color"], shader.inputs["Base Color"])
    return mat


def bake_ambient_occlusion(objects, samples):
    """Soft contact shadows, baked into each object's colors (multiplied in)."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.light_settings.distance = 0.8
    for obj in objects:
        mesh = obj.data
        color = mesh.color_attributes["Col"]
        occlusion = mesh.color_attributes.new("AO", "FLOAT_COLOR", "CORNER")
        mesh.color_attributes.active_color = occlusion
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.bake(type="AO", target="VERTEX_COLORS", margin=0)
        # Lighten the bake a little (0.45 floor), so crevices get darker but nothing turns black
        light = [o.color[0] for o in occlusion.data]
        for c, ao in zip(color.data, light):
            shade = 0.45 + 0.55 * ao
            c.color = (c.color[0] * shade, c.color[1] * shade, c.color[2] * shade, 1)
        mesh.color_attributes.remove(occlusion)
        mesh.color_attributes.active_color = mesh.color_attributes["Col"]
        remove_hidden_faces(obj, light)


def remove_hidden_faces(obj, light):
    """Drop faces nobody can see, to keep the file small: faces squeezed between blocks (no light reaches them),
    faces under the sea, and faces pointing down (the camera always looks from above)."""
    mesh = obj.data
    to_world = obj.matrix_world
    hidden = []
    for poly in mesh.polygons:
        corners = range(poly.loop_start, poly.loop_start + poly.loop_total)
        average = sum(light[i] for i in corners) / poly.loop_total
        world_normal = (to_world.to_3x3() @ poly.normal).normalized()
        top = max((to_world @ mesh.vertices[v].co).z for v in poly.vertices)
        if average < 0.04 or top < SEA_LEVEL - 0.05 or world_normal.z < -0.6:
            hidden.append(poly.index)
    mesh_edit = bmesh.new()
    mesh_edit.from_mesh(mesh)
    mesh_edit.faces.ensure_lookup_table()
    bmesh.ops.delete(mesh_edit, geom=[mesh_edit.faces[i] for i in hidden], context="FACES")
    loose = [v for v in mesh_edit.verts if not v.link_faces]
    bmesh.ops.delete(mesh_edit, geom=loose, context="VERTS")
    mesh_edit.to_mesh(mesh)
    mesh_edit.free()


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.context.scene.collection
    build_ground()
    build_hut_and_bridge()
    build_screen_frame()
    build_dock()
    build_campfire_base()
    build_plants()
    build_ground_details()
    material = vertex_color_material()
    objects = [STATIC.finish(material, collection)] + [piece.finish(material, collection) for piece in SWAYING]
    return objects


def preview():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y = 960, 720
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.25, 0.62, 0.85, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(35), math.radians(15), math.radians(20))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 26
    scene.collection.objects.link(cam)
    scene.camera = cam
    # The website's isometric camera sits at (30, 25.5, 30) looking at (0, 1.4, 0)
    position = TO_BLENDER @ Vector((30, 25.5, 30))
    target = TO_BLENDER @ Vector((0, 1.4, 0))
    cam.location = position
    cam.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(PREVIEW_DIR, "island.png")
    bpy.ops.render.render(write_still=True)
    for obj in (sun, cam):
        bpy.data.objects.remove(obj)


def export():
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(GLB_PATH),
        export_format="GLB",
        export_apply=True,
        export_extras=True,           # the sway / speed numbers on the plants
        export_vertex_color="ACTIVE",
        export_all_vertex_colors=False,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
        # Draco packs the mesh many times smaller; the website unpacks it with three.js's DRACOLoader
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=7,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=8,
        export_draco_color_quantization=8,
    )


if __name__ == "__main__":
    objects = build()
    bake_ambient_occlusion(objects, samples=48 if "--fast" not in sys.argv else 8)
    if "--preview" in sys.argv:
        preview()
    export()
    size = os.path.getsize(GLB_PATH)
    verts = sum(len(o.data.vertices) for o in objects)
    print("ISLAND_DONE", os.path.abspath(GLB_PATH), f"{size / 1024:.0f} KB", f"{verts} vertices", f"{len(objects)} objects")
