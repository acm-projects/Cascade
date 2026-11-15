"""The sea behind the Projects page, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/underwater.py
    add  -- --preview   to also render a preview picture into frontend/blender/previews/underwater.png
    add  -- --fast      for a quicker, rougher shadow bake while trying things out

It makes:
    frontend/blender/underwater.blend      - open this in Blender to look at or edit the scene
    frontend/public/models/underwater.glb  - the file the website loads (features/landing3d/underwaterScene.js)

What's in here: everything solid and still -
    "Floor"  the bumpy sand, with ripples, darker and lighter patches, shells and pebbles
    "Rocks"  the cave walls and rock pillars (stacked boulders with moss and barnacles)
    "Decor"  coral (branching, brain, tube coral and sea fans), loose rocks, starfish and the treasure chest
    "Gold"   the pile of coins and gems in the chest (its own object, so the website can make it glow)
Soft shadows (ambient occlusion) are baked into the colors, which the browser can't do cheaply.

What stays in code (underwaterScene.js), because it moves or glows: the water, the beam of light, the light
ripples on the sand, seaweed, the sunken clip cards, the chest's glow, fish, jellyfish and bubbles.

Positions are in the website's coordinates (+y up, +z toward the viewer), the same numbers as underwaterScene.js.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island as kit  # noqa: E402  (shared helpers: shapes, Piece, colors, transform, export settings)
from island import Piece, beveled_box, box_shape, cone_shape, cylinder_shape, icosphere_shape, lumpy_ball, transform  # noqa: E402

BLEND_PATH = os.path.join(HERE, "underwater.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "underwater.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

random = kit.random
pick = kit.pick

ROCK = ["#5a7192", "#6880a2", "#52668a", "#61789b", "#566b8e"]   # a touch lighter than the code version: the baked shadows darken them
SAND = ["#e9cf93", "#e3c788", "#efd8a2", "#dcc07e"]
MOSS = ["#3f8a5a", "#4f9e62", "#357a50"]

FLOOR = Piece("Floor")
ROCKS = Piece("Rocks")
DECOR = Piece("Decor")
GOLD = Piece("Gold")


def floor_y(x, z):
    """The sand's height: the same formula as underwaterScene.js floorY, so code-placed things still sit on it."""
    return -0.6 + math.sin(x * 0.35) * 0.6 + math.cos(z * 0.4 + x * 0.2) * 0.5 + math.sin(x * 0.9 + z * 0.7) * 0.25


def put(piece, shape, color, x, z, lift=0, rotation=(0, 0, 0), scale=1, order="XYZ"):
    piece.add(shape, color, transform((x, floor_y(x, z) + lift, z), rotation, order, scale))


# ---------- The sand ----------

def build_floor():
    # A bumpy sheet of sand from in front of you to far away (x -55..55, z +20..-60), like the code version,
    # with small ripples on top and patches of lighter and darker sand
    cols, rows = 110, 80
    verts, faces, colors = [], [], []
    for r in range(rows + 1):
        z = 20 - r * (80 / rows)
        for c in range(cols + 1):
            x = -55 + c * (110 / cols)
            ripple = math.sin(x * 2.6 + z * 0.9) * 0.04 + math.sin(z * 3.1 - x * 0.4) * 0.025
            verts.append((x, floor_y(x, z) + ripple, z))
    for r in range(rows):
        for c in range(cols):
            a = r * (cols + 1) + c
            faces.append((a, a + 1, a + cols + 2, a + cols + 1))
    # one connected sheet per sand shade (so neighbouring squares share their corners)
    groups = {}
    for poly in faces:
        x, _, z = verts[poly[0]]
        patch = math.sin(x * 0.45 + 1.3) * math.cos(z * 0.38 - 0.7) + (random() - 0.5) * 0.5
        color = SAND[2] if patch > 0.55 else SAND[3] if patch < -0.6 else pick(SAND[:2])
        groups.setdefault(color, []).append(poly)
    for color, polys in groups.items():
        FLOOR.add((verts, polys), color)
    # Shells and pebbles scattered on the sand (more of them near you)
    for _ in range(140):
        x = (random() - 0.5) * 34
        z = 8 - random() * 26
        if random() < 0.55:
            size = 0.06 + random() * 0.1
            put(FLOOR, lumpy_ball(size, 0.2, 0), pick(["#b8a68a", "#9c8c74", "#cfc2a8", "#8a8a8a"]), x, z, size * 0.25, (0, random() * 6, 0), (1, 0.6, 1))
        else:
            shell(x, z)


def shell(x, z):
    """A little ribbed clam shell, lying on the sand."""
    size = 0.1 + random() * 0.08
    color = pick(["#ffd9c7", "#fff1dc", "#ffc2b0", "#f7e2ff"])
    turn = random() * 6
    for i in range(5):
        a = (i - 2) * 0.32
        rib = cone_shape(size * 0.22, size, 4)
        put(FLOOR, rib, color, x + math.sin(turn + a) * size * 0.4, z + math.cos(turn + a) * size * 0.4, size * 0.08,
            (math.pi / 2, turn + a, 0), (1, 1, 0.35), "YXZ")


# ---------- Rock: pillars made of stacked boulders ----------

def pillar(x, z, height, radius):
    y = floor_y(x, z) - radius * 0.3
    top = floor_y(x, z) + height
    while y < top:
        size = radius * (0.8 + random() * 0.4)
        cx = x + (random() - 0.5) * radius * 0.5
        cz = z + (random() - 0.5) * radius * 0.4
        stretch = (1 + random() * 0.2, 1.25 + random() * 0.3, 1 + random() * 0.2)
        detail = 2 if z > -12 else 1   # far-away rock is hazy anyway: fewer faces
        ROCKS.add(lumpy_ball(size, 0.24, detail), pick(ROCK), transform((cx, y, cz), (0, random() * 6, 0), scale=stretch))
        if random() < 0.45:   # a side lump now and then
            side = size * (0.45 + random() * 0.2)
            sx = cx + (random() < 0.5 and -1 or 1) * size * 0.8
            ROCKS.add(lumpy_ball(side, 0.22, 1), pick(ROCK), transform((sx, y + size * 0.3, cz + size * 0.3)))
        if random() < 0.5:    # moss on a ledge facing up / toward you
            moss = size * (0.35 + random() * 0.2)
            ROCKS.add(lumpy_ball(moss, 0.3, 1), pick(MOSS), transform((cx + (random() - 0.5) * size, y + size * 1.05, cz + size * 0.55), scale=(1.2, 0.35, 1)))
        for _ in range(int(random() * 4)):   # barnacles
            a = random() * math.tau
            bx, bz = cx + math.sin(a) * size * 0.95, cz + abs(math.cos(a)) * size * 0.95
            ROCKS.add(cylinder_shape(0.03, 0.07, 0.08, 6), "#e8e1cf", transform((bx, y + (random() - 0.3) * size, bz), (math.pi / 2, a, 0), "YXZ"))
        y += size * 1.35


def build_rocks():
    # Cave walls framing the sides, close to you
    for x, z, r in [(-14, 5, 3.2), (-11.5, 1, 2.6), (-13, -3, 3), (14.5, 5, 3.2), (12, 0.5, 2.6), (13.5, -4, 3)]:
        pillar(x, z, 26, r)
    # Pillars in the middle distance
    pillar(-6.5, -7, 9, 1.8)
    pillar(7.5, -9, 12, 2)
    pillar(-10, -15, 17, 2.6)
    pillar(10.5, -19, 19, 2.6)
    # The tall one in the beam of light
    pillar(0.6, -16, 30, 2.2)
    # Far away, fading into the blue
    for x, z, h, r in [(-5, -32, 22, 3), (7, -36, 26, 3.6), (-18, -30, 26, 4), (19, -34, 24, 4), (-28, -40, 30, 5), (30, -42, 30, 5)]:
        pillar(x, z, h, r)


# ---------- Coral and other things on the sand ----------

def branch(x, y, z, length, radius, tilt, turn, color, depth):
    """One coral branch that splits into smaller ones, with round tips."""
    local = transform((x, y, z), (tilt, turn, 0), "YXZ")
    end = local @ Vector((0, length, 0))
    DECOR.add(cylinder_shape(radius * 0.75, radius, length, 6), color, local @ transform((0, length / 2, 0)))
    if depth == 0:
        DECOR.add(icosphere_shape(radius * 1.05, 1), color, transform(tuple(end)))
        return
    for k in range(2 if random() < 0.6 else 3):
        branch(end.x, end.y, end.z, length * (0.6 + random() * 0.2), radius * 0.72,
               tilt + (random() - 0.5) * 0.9, turn + (k - 0.5) * 1.6 + random(), color, depth - 1)


def branching_coral(x, z, color, size=1):
    base = floor_y(x, z)
    for i in range(5 + int(random() * 3)):
        branch(x, base, z, (0.45 + random() * 0.25) * size, 0.09 * size, (random() - 0.5) * 0.7,
               i / 5 * math.tau + random(), color, 2)


def brain_coral(x, z, color, size):
    """A round coral with maze-like grooves."""
    verts, faces = icosphere_shape(size, 3)
    grooved = []
    for vx, vy, vz in verts:
        n = Vector((vx, vy, vz)).normalized()
        groove = math.sin(n.x * 9 + math.sin(n.z * 7) * 2) * math.cos(n.z * 8 + n.y * 5)
        grooved.append(tuple(c * (1 + 0.07 * groove) for c in (vx, vy, vz)))
    put(DECOR, (grooved, faces), color, x, z, size * 0.2, scale=(1, 0.7, 1))


def tube_coral(x, z, color):
    """A cluster of tubes, each with a dark opening on top."""
    inside = "#5a2a4a"
    for _ in range(5 + int(random() * 3)):
        tx = x + (random() - 0.5) * 0.6
        tz = z + (random() - 0.5) * 0.6
        h = 0.35 + random() * 0.6
        r = 0.07 + random() * 0.05
        lean = ((random() - 0.5) * 0.4, 0, (random() - 0.5) * 0.4)
        base = floor_y(tx, tz)
        DECOR.add(cylinder_shape(r * 1.1, r * 0.85, h, 8), color, transform((tx, base + h / 2, tz), lean))
        DECOR.add(cylinder_shape(r * 0.75, r * 0.75, 0.02, 8), inside, transform((tx, base, tz), lean) @ transform((0, h + 0.005, 0)))


def sea_fan(x, z, color, size=1):
    """A flat fan of thin branches, standing up and facing you."""
    base = floor_y(x, z)
    turn = (random() - 0.5) * 0.8
    for i in range(11):
        a = (i / 10 - 0.5) * 2.2
        length = (1.0 + random() * 0.4) * size
        DECOR.add(cylinder_shape(0.015, 0.03, length, 4), color,
                  transform((x, base, z), (0, turn, a), "YXZ") @ transform((0, length / 2, 0)))
    for ring in (0.45, 0.75):   # cross-threads holding the fan together
        for i in range(10):
            a1, a2 = (i / 10 - 0.5) * 2.2, ((i + 1) / 10 - 0.5) * 2.2
            p1 = (math.sin(-a1) * ring * size, math.cos(a1) * ring * size)
            p2 = (math.sin(-a2) * ring * size, math.cos(a2) * ring * size)
            mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
            seg = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            angle = math.atan2(p2[1] - p1[1], p2[0] - p1[0])
            DECOR.add(box_shape(seg, 0.02, 0.02), color, transform((x, base, z), (0, turn, 0)) @ transform((mx, my, 0), (0, 0, angle)))


def loose_rock(x, z, size):
    put(DECOR, lumpy_ball(size, 0.22, 1), pick(ROCK), x, z, size * 0.2, (0, random() * 6, 0), (1, 0.7, 1))


def starfish(x, z, color):
    turn = random() * math.tau
    base = floor_y(x, z) + 0.04
    DECOR.add(icosphere_shape(0.1, 1), color, transform((x, base, z), scale=(1, 0.4, 1)))
    for i in range(5):
        a = turn + i / 5 * math.tau
        arm = transform((x, base, z), (0, a, 0)) @ transform((0, 0, 0.15), (math.pi / 2, 0, 0)) @ transform(scale=(1, 1, 0.45))
        DECOR.add(cone_shape(0.07, 0.3, 6), color, arm)
        for k in range(3):   # little bumps along the top of each arm
            DECOR.add(icosphere_shape(0.018, 0), "#ffffff" if color == "#ff5d73" else "#ffe3b0",
                      transform((x, base, z), (0, a, 0)) @ transform((0, 0.035, 0.07 + k * 0.07)))


def treasure_chest(x, z, turn):
    wood, dark, metal, rivet = "#8a5328", "#5e3518", "#d9a42e", "#f1c75a"
    chest = transform((x, floor_y(x, z), z), (0, turn, 0))
    at = lambda *args, **kw: chest @ transform(*args, **kw)   # noqa: E731
    # the box: three planks on each long side, dark corner posts, a base
    for i in range(3):
        DECOR.add(beveled_box(1.24, 0.22, 0.82, 0.03), wood if i % 2 == 0 else "#97602f", at((0, 0.12 + i * 0.22, 0)))
    for cx in (-0.63, 0.63):
        for cz in (-0.42, 0.42):
            DECOR.add(box_shape(0.08, 0.72, 0.08), dark, at((cx, 0.36, cz)))
    # metal straps with rivets, and a lock on the front
    for sx in (-0.42, 0.42):
        DECOR.add(box_shape(0.1, 0.72, 0.86), metal, at((sx, 0.36, 0)))
        for ry in (0.15, 0.36, 0.57):
            DECOR.add(icosphere_shape(0.025, 0), rivet, at((sx, ry, 0.44)))
    DECOR.add(beveled_box(0.18, 0.2, 0.06, 0.02), metal, at((0, 0.55, 0.44)))
    DECOR.add(box_shape(0.04, 0.07, 0.02), dark, at((0, 0.53, 0.475)))
    # the lid, hinged at the back and open
    hinge = at((0, 0.7, -0.42), (-0.8, 0, 0))
    DECOR.add(beveled_box(1.3, 0.12, 0.86, 0.04), wood, hinge @ transform((0, 0.06, 0.43)))
    DECOR.add(cylinder_shape(0.43, 0.43, 1.3, 10), wood, hinge @ transform((0, 0.06, 0.43), (0, 0, math.pi / 2), scale=(1, 1, 0.45)))
    for sx in (-0.42, 0.42):
        DECOR.add(box_shape(0.1, 0.16, 0.9), metal, hinge @ transform((sx, 0.08, 0.43)))
    # the gold: a mound, coins scattered on it and spilling out, and a few gems
    GOLD.add(lumpy_ball(0.5, 0.18, 1), "#ffd34d", at((0, 0.7, 0), scale=(1.15, 0.38, 0.75)))
    for _ in range(26):
        cx, cz = (random() - 0.5) * 1.0, (random() - 0.5) * 0.6
        GOLD.add(cylinder_shape(0.07, 0.07, 0.015, 10), pick(["#ffd34d", "#ffc72e", "#ffe27a"]),
                 at((cx, 0.82 - (abs(cx) + abs(cz)) * 0.12, cz), ((random() - 0.5) * 0.8, 0, (random() - 0.5) * 0.8)))
    for _ in range(9):   # coins that spilled onto the sand in front
        a = random() * 2 - 1
        GOLD.add(cylinder_shape(0.07, 0.07, 0.015, 10), "#ffd34d", at((a * 0.7, 0.01, 0.6 + random() * 0.5), (random() * 0.3, 0, random() * 0.3)))
    for color in ("#ff3d6e", "#3dd6ff", "#5dff8a", "#b45dff"):
        GOLD.add(icosphere_shape(0.07, 0), color, at(((random() - 0.5) * 0.7, 0.88, (random() - 0.5) * 0.4), (random(), random(), 0)))


def build_decor():
    branching_coral(-5.6, 5, "#ff7f8a", 1.3)
    branching_coral(4, 5.5, "#ff9a3c", 1.4)
    branching_coral(1.4, 2, "#c77dff", 1.1)
    branching_coral(-7.5, -1.5, "#ff7f8a", 1.2)
    branching_coral(6.8, -2.5, "#ffb43c", 1.3)
    branching_coral(-2.5, -5, "#c77dff", 1)
    brain_coral(-0.6, 6.4, "#ff9fb0", 0.55)
    brain_coral(7.4, 6, "#c77dff", 0.5)
    brain_coral(2.8, -1.5, "#ffb86b", 0.45)
    tube_coral(-9.2, 6.2, "#ff6fae")
    tube_coral(9.4, 3.2, "#ffa64d")
    tube_coral(-3.8, -3.2, "#9b7bff")
    sea_fan(-10.2, 0.5, "#c94fd6", 1.3)
    sea_fan(10.6, -1.5, "#ff5d73", 1.2)
    sea_fan(3.6, -7.5, "#b45dff", 1.4)
    loose_rock(-4.6, 7.2, 0.7)
    loose_rock(2.4, 7.6, 0.55)
    loose_rock(5.6, 0.5, 0.6)
    loose_rock(-8.6, 2, 0.6)
    loose_rock(8.2, 7.4, 0.45)
    starfish(-1.6, 5.4, "#ff8a3d")
    starfish(3.2, 4.2, "#ff5d73")
    starfish(-6.4, 7.4, "#ffcf3d")
    treasure_chest(-3.4, 3, 0.45)


# ---------- Building, baking, exporting ----------

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.context.scene.collection
    build_floor()
    build_rocks()
    build_decor()
    material = kit.vertex_color_material()
    material.name = "UnderwaterVertexColor"
    objects = [piece.finish(material, collection) for piece in (FLOOR, ROCKS, DECOR, GOLD)]
    face_up(objects[0])
    return objects


def face_up(obj):
    """The sand is an open sheet, so Blender can't tell which side is its top: make every face point up."""
    edit = bmesh.new()
    edit.from_mesh(obj.data)
    edit.verts.ensure_lookup_table()
    bmesh.ops.remove_doubles(edit, verts=edit.verts, dist=0.0001)   # join the shade groups into one sheet
    for face in edit.faces:
        face.normal_update()
        if face.normal.z < 0:
            face.normal_flip()
    edit.to_mesh(obj.data)
    edit.free()


def bake_ambient_occlusion(objects, samples):
    """Soft contact shadows, multiplied into each object's colors (like island.py, but keeping every face:
    the camera here looks from the side and from below the rocks' overhangs)."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.light_settings.distance = 1.2
    for obj in objects:
        mesh = obj.data
        color = mesh.color_attributes["Col"]
        occlusion = mesh.color_attributes.new("AO", "FLOAT_COLOR", "CORNER")
        mesh.color_attributes.active_color = occlusion
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.bake(type="AO", target="VERTEX_COLORS", margin=0)
        for c, o in zip(color.data, occlusion.data):
            shade = 0.68 + 0.32 * o.color[0]   # gentle: crevices a little darker, nothing gloomy
            c.color = (c.color[0] * shade, c.color[1] * shade, c.color[2] * shade, 1)
        mesh.color_attributes.remove(occlusion)
        mesh.color_attributes.active_color = mesh.color_attributes["Col"]


def preview():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    world = scene.world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = kit.srgb("#1f63ad")
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (math.radians(20), math.radians(10), 0)
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle = math.radians(50)   # the website's camera: 50 degrees top to bottom
    scene.collection.objects.link(cam)
    scene.camera = cam
    position = kit.TO_BLENDER @ Vector((0, 3, 14))     # the website's camera
    target = kit.TO_BLENDER @ Vector((0, 5, -6))
    cam.location = position
    cam.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(PREVIEW_DIR, "underwater.png")
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
        export_vertex_color="ACTIVE",
        export_all_vertex_colors=False,
        export_animations=False,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
        export_draco_mesh_compression_enable=True,
        export_draco_mesh_compression_level=7,
        export_draco_position_quantization=14,
        export_draco_normal_quantization=8,
        export_draco_color_quantization=8,
    )


if __name__ == "__main__":
    objects = build()
    bake_ambient_occlusion(objects, samples=32 if "--fast" not in sys.argv else 6)
    if "--preview" in sys.argv:
        preview()
    export()
    size = os.path.getsize(GLB_PATH)
    verts = sum(len(o.data.vertices) for o in objects)
    print("UNDERWATER_DONE", os.path.abspath(GLB_PATH), f"{size / 1024:.0f} KB", f"{verts} vertices")
