"""The pond on the "How it works" page, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/pond.py
    (add  -- --preview  to also render a preview picture into frontend/blender/previews/, and  -- --fast  for a quick bake)

It makes:
    frontend/blender/pond.blend      - open this in Blender to look at or edit the pond
    frontend/public/models/pond.glb  - the file the website loads (features/howItWorks/pondScene.js)

A jungle pond in the same chunky block style as the Landing island: stepped grassy banks all around,
a tall rocky cliff at the back with a notch where a waterfall pours in, rocks in the water, trees, palms,
reeds and purple flowering bushes. Soft shadows (ambient occlusion) are baked into the colors.

Separate objects the website moves:
    "Pad_1" ... "Pad_4"       - the four lily pads the frog leaps across, one per stage (they bob)
    "Flower_1" ... "Flower_4" - a pink lotus on each pad, which opens when the frog lands there
    "Sway_..."                - plants with "sway" and "speed" custom properties, like the island's
What stays in code (pondScene.js): the water, the waterfall, ripples, the frog's leaps, dragonflies.

It borrows the island's shapes, colors and plants (island.py). Positions are in the website's
coordinates (+y up, +z toward the viewer). The water surface is at y = 0.
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island as kit  # noqa: E402  (the island's shapes, Piece, colors and plants)

BLEND_PATH = os.path.join(HERE, "pond.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "pond.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

# ---------- The layout (pondScene.js uses the same numbers) ----------
GROW = 1.3                    # the pond was made bigger by this much; everything placed around it moves out too
POND_RX, POND_RZ = 8.0 * GROW, 5.8 * GROW   # the pond is an oval this wide (x) and deep (z)
STEP = 0.6                    # height of one ground step
FALL_X = (-1.5, 0.5)          # the waterfall's notch in the back cliff
PADS = [(x * GROW, z * GROW, size * 1.15) for x, z, size in [(2.7, -2.4, 1.05), (-3.4, -0.4, 1.0), (-0.7, 2.3, 1.1), (3.6, 2.4, 1.0)]]   # (x, z, size), stage 1 to 4
SMALL_PADS = [(x * GROW, z * GROW, size * 1.1) for x, z, size in [(-6.2, 2.9, 0.6), (6.3, -0.8, 0.55), (0.9, -0.2, 0.45), (-2.2, -3.7, 0.55), (5.4, 0.6, 0.4), (-5.4, -2.4, 0.5)]]
WATER_ROCKS = [(x * GROW, z * GROW, size * 1.1) for x, z, size in [(-5.6, 0.9, 0.55), (5.6, -3.2, 0.6), (1.4, -4.4, 0.45), (-4.6, 3.9, 0.4), (6.6, 3.4, 0.5), (-1.9, 0.9, 0.3)]]

rng = kit.rng
random = rng.random
pick = kit.pick
transform = kit.transform
COLORS = dict(kit.COLORS)
COLORS.update({
    "sand": ["#d8c48e", "#cfb882"],
    "pad": ["#5fc24a", "#53b442", "#6ccc52"],
    "padDark": "#3d8f37",
    "lotus": "#ff8fb4",
    "lotusDeep": "#f06d9a",
    "lotusMiddle": "#ffd75e",
    "purple": ["#b77ee8", "#a46bdc", "#c993f0"],
    "reed": ["#6fae3a", "#5d9c33"],
    "cattail": "#7a4f2c",
})


def oval(x, z):
    return math.hypot(x / POND_RX, z / POND_RZ)


def steps_at(x, z):
    """How many ground steps tall the bank is at this cell (0 = water)."""
    d = oval(x, z)
    if d < 1:
        return 0
    wobble = math.sin(x * 1.3) * 0.35 + math.cos(z * 1.7 + x * 0.4) * 0.3
    steps = 1 + int(max(0, (d - 1) * 4.2 + wobble))
    if z < -4.2 * GROW:              # the tall rocky cliff at the back
        steps = max(steps, 6 + int(max(0, -z - 6 * GROW) * 0.6))
        if FALL_X[0] <= x <= FALL_X[1]:
            steps -= 1               # the notch the waterfall pours through
    elif z > 3 * GROW:               # keep the front bank low, so it doesn't hide the pond
        steps = min(steps, 1 + int(max(0, z - 6 * GROW) * 0.8))
    return min(steps, 9)


def top_at(x, z):
    """The ground height at a point (the top of its cell)."""
    steps = steps_at(round(x), round(z))
    return -0.3 + steps * STEP if steps else -0.3


def place(x, z):
    return transform((x, top_at(x, z), z))


# The island's plant builders look up the ground with ground_place(); point them at the pond's ground instead
kit.ground_place = place
POND = kit.Piece("Pond")
kit.STATIC = POND
kit.SWAYING = []


def static(shape, color, *args, **kwargs):
    POND.add(shape, color, transform(*args, **kwargs))


# ---------- Ground: stepped columns of grass, dirt and rock around the water ----------

def build_ground():
    for x in range(-22, 23):
        for z in range(-17, 14):
            steps = steps_at(x, z)
            if not steps:
                continue
            top = -0.3 + steps * STEP
            bottom = -1.2
            cliff = z < -4.2 * GROW
            near_water = steps == 1 and oval(x, z) < 1.1
            # the column body: rock for the cliff, dirt elsewhere
            body = pick(COLORS["rock"] if cliff else COLORS["dirt"])
            static(kit.box_shape(1, top - bottom - 0.2, 1), body, (x, (top - 0.2 + bottom) / 2, z))
            # a stripe of rock where the cliff's layers show
            if cliff and steps > 2:
                for layer in range(1, steps - 1, 2):
                    y = -0.3 + layer * STEP
                    static(kit.box_shape(1.02, 0.16, 1.02), pick(COLORS["deepRock"]), (x, y, z))
            # the top: sand by the water, grass elsewhere
            cap = pick(COLORS["sand"]) if near_water else pick(COLORS["grass"])
            static(kit.beveled_box(1, 0.2, 1, 0.05), cap, (x, top - 0.1, z))


# ---------- Things in the water ----------

def lily_pad(size, color, notch=0.55, sides=14):
    """A flat round pad with a wedge cut out, as (verts, faces). Its top is at y = 0.06."""
    verts = [(0, 0.06, 0), (0, 0.0, 0)]
    start = notch / 2
    angles = [start + (math.tau - notch) * i / sides for i in range(sides + 1)]
    for a in angles:
        r = size * (1 + (random() - 0.5) * 0.04)
        verts += [(math.sin(a) * r, 0.06, math.cos(a) * r), (math.sin(a) * r, 0.0, math.cos(a) * r)]
    faces = []
    for i in range(sides):
        t0, b0, t1, b1 = 2 + i * 2, 3 + i * 2, 4 + i * 2, 5 + i * 2
        faces.append((0, t0, t1))          # top
        faces.append((1, b1, b0))          # bottom
        faces.append((t0, b0, b1, t1))     # rim
    last_t, last_b = 2 + sides * 2, 3 + sides * 2
    faces.append((0, 1, 3, 2))            # the two cut edges of the notch
    faces.append((0, last_t, last_b, 1))
    return verts, faces


def pad_veins(piece, size, notch=0.55):
    """Thin darker lines fanning out from the middle of the pad."""
    for i in range(7):
        a = notch / 2 + (math.tau - notch) * (i + 0.5) / 7
        length = size * 0.8
        piece.add(kit.box_shape(0.03, 0.01, length), COLORS["padDark"],
                  transform((math.sin(a) * length / 2, 0.065, math.cos(a) * length / 2), (0, a, 0)))


def build_pads():
    pads = []
    for index, (x, z, size) in enumerate(PADS, start=1):
        turn = random() * math.tau
        pad = kit.Piece(f"Pad_{index}", transform((x, 0, z), (0, turn, 0)), {"stage": index})
        pad.add(lily_pad(size, pick(COLORS["pad"])), COLORS["pad"][index % 3])
        pad_veins(pad, size)
        pads.append(pad)
        # The lotus: a closed bud now; the website opens it (scales the petals out) when the frog arrives
        flower = kit.Piece(f"Flower_{index}", transform((x + math.sin(turn + 2.2) * size * 0.45, 0.06, z + math.cos(turn + 2.2) * size * 0.45)))
        for ring, (count, tilt, length, color) in enumerate([(7, 0.45, 0.5, COLORS["lotus"]), (5, 0.2, 0.42, COLORS["lotusDeep"])]):
            for i in range(count):
                flower.add(kit.leaf_shape(length, 0.28, -0.05, 4), color,
                           transform((0, 0.02 + ring * 0.02, 0), (-(math.pi / 2 - tilt), i / count * math.tau + ring * 0.5, 0), "YXZ"))
        flower.add(kit.icosphere_shape(0.1, 1), COLORS["lotusMiddle"], transform((0, 0.1, 0)))
        pads.append(flower)
    for x, z, size in SMALL_PADS:
        static(lily_pad(size, None, notch=0.5, sides=10), pick(COLORS["pad"]), (x, 0, z), (0, random() * math.tau, 0))
    return pads


def build_water_rocks():
    for x, z, size in WATER_ROCKS:
        static(kit.lumpy_ball(size, 0.22, 0), pick(COLORS["rock"]), (x, size * 0.15, z), scale=(1.2, 0.7, 1))
        if random() < 0.6:
            static(kit.lumpy_ball(size * 0.5, 0.2, 0), pick(COLORS["rock"]), (x + size * 0.8, size * 0.05, z + size * 0.4), scale=(1, 0.7, 1))


# ---------- Plants on the banks ----------

def reeds(x, z, count=6):
    plant = kit.swaying(f"Sway_reeds_{len(kit.SWAYING)}", place(x, z), 0.05, 1.2 + random() * 0.6)
    for i in range(count):
        a = random() * math.tau
        r = random() * 0.35
        height = 0.9 + random() * 0.7
        lean = (random() - 0.5) * 0.3
        plant.add(kit.box_shape(0.05, height, 0.05), pick(COLORS["reed"]),
                  transform((math.sin(a) * r, height / 2, math.cos(a) * r), (lean, 0, lean)))
        if i % 2 == 0:
            plant.add(kit.box_shape(0.1, 0.26, 0.1), COLORS["cattail"],
                      transform((math.sin(a) * r + lean * height * 0.5, height * 0.86, math.cos(a) * r - lean * height * 0.5), (lean, 0, lean)))


def flowering_bush(x, z, size=1):
    plant = kit.swaying(f"Sway_bush_{len(kit.SWAYING)}", place(x, z), 0.02, 0.9 + random() * 0.5)
    for bx, by, bz, radius in [(0, 0.38, 0, 0.55), (0.42, 0.25, 0.1, 0.4), (-0.38, 0.28, 0.15, 0.42), (0.05, 0.66, -0.1, 0.38)]:
        plant.add(kit.lumpy_ball(radius * size), pick(COLORS["leaves"]), transform((bx * size, by * size, bz * size)))
    for _ in range(9):
        a = random() * math.tau
        lift = random() * 0.6 + 0.2
        plant.add(kit.box_shape(0.13, 0.13, 0.13), pick(COLORS["purple"]),
                  transform((math.cos(a) * 0.55 * size, lift * size, math.sin(a) * 0.5 * size), (random(), random(), 0)))


def rock(x, z, size=0.4):
    static(kit.lumpy_ball(size, 0.2, 0), pick(COLORS["rock"]), (x, top_at(x, z) + size * 0.32, z), scale=(1, 0.72, 1))


def build_plants():
    # The back cliff: a few trees and palms along the top
    for x, z, size in [(-6.5, -7.5, 1.3), (-3.5, -8.5, 1.1), (3.2, -8, 1.25), (6.8, -7, 1.15), (-9.5, -5.5, 1.2), (9.6, -4.8, 1.1)]:
        x, z = x * GROW, z * GROW
        kit.tree(x, z, size, "#f0912e" if x > 6 else None)
    for x, z, size in [(1.6, -7.1, 1.1), (-2.8, -6.6, 1.0), (8.3, -6.2, 1.0), (-8.0, -6.7, 1.0)]:
        x, z = x * GROW, z * GROW
        kit.palm(x, z, size)
    # The sides
    for x, z, size in [(-10.5, -1, 1.2), (-10, 3, 1.0), (10.6, 0.5, 1.15), (10.2, 4.2, 1.0)]:
        x, z = x * GROW, z * GROW
        kit.tree(x, z, size)
    kit.palm(-9.3 * GROW, 1.2 * GROW, 1.1)
    kit.palm(9.2 * GROW, -2.2 * GROW, 1.05)
    for x, z in [(-8.6, -3.2), (8.4, 2.6), (-7.6, 4.6), (7.0, 5.4), (-4.0, -6.0), (4.6, -6.3)]:
        x, z = x * GROW, z * GROW
        kit.leafy_plant(x, z, 1.0 + random() * 0.3, bright=random() < 0.4)
    # Purple flowering bushes, like the reference
    for x, z, size in [(8.6, -1.0, 1.1), (9.0, 1.8, 0.95), (7.8, -4.6, 1.0), (-8.8, 2.0, 0.9), (-7.4, -5.0, 0.85), (5.6, 6.2, 0.8)]:
        x, z = x * GROW, z * GROW
        flowering_bush(x, z, size)
    # Reeds and cattails along the water's edge
    for x, z in [(-7.6, 1.6), (-6.8, -2.8), (7.4, 1.0), (6.6, -3.4), (-3.6, 5.6), (2.6, 5.9), (-6.0, 4.4), (5.6, 4.6)]:
        x, z = x * GROW, z * GROW
        reeds(x, z)
    # Rocks and flowers on the banks
    for x, z, size in [(-8.0, 0.2, 0.45), (7.6, 3.6, 0.4), (-5.0, 5.6, 0.35), (4.2, 6.0, 0.4), (-2.0, -5.6, 0.5), (3.6, -5.4, 0.45)]:
        x, z = x * GROW, z * GROW
        rock(x, z, size)
    for x, z, color in [(-6.4, 5.2, "#ffd34d"), (6.2, 5.6, "#ff9ec7"), (-9.4, -2.4, "#ffffff"), (9.8, -2.8, "#ffd34d"), (0.4, 6.4, "#ff9ec7")]:
        x, z = x * GROW, z * GROW
        kit.flowers(x, z, color)


# ---------- Material, baking and export ----------

def bake_ambient_occlusion(objects, samples):
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
        light = [o.color[0] for o in occlusion.data]
        for c, ao in zip(color.data, light):
            shade = 0.45 + 0.55 * ao
            c.color = (c.color[0] * shade, c.color[1] * shade, c.color[2] * shade, 1)
        mesh.color_attributes.remove(occlusion)
        mesh.color_attributes.active_color = mesh.color_attributes["Col"]
        if obj.name == "Pond":
            remove_hidden_faces(obj, light)


def remove_hidden_faces(obj, light):
    """Drop faces nobody can see: squeezed between blocks, deep under the water, or pointing down."""
    mesh = obj.data
    hidden = []
    for poly in mesh.polygons:
        corners = range(poly.loop_start, poly.loop_start + poly.loop_total)
        average = sum(light[i] for i in corners) / poly.loop_total
        top = max((obj.matrix_world @ mesh.vertices[v].co).z for v in poly.vertices)
        normal = (obj.matrix_world.to_3x3() @ poly.normal).normalized()
        if average < 0.04 or top < -0.6 or normal.z < -0.6:
            hidden.append(poly.index)
    edit = bmesh.new()
    edit.from_mesh(mesh)
    edit.faces.ensure_lookup_table()
    bmesh.ops.delete(edit, geom=[edit.faces[i] for i in hidden], context="FACES")
    bmesh.ops.delete(edit, geom=[v for v in edit.verts if not v.link_faces], context="VERTS")
    edit.to_mesh(mesh)
    edit.free()


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    collection = bpy.context.scene.collection
    build_ground()
    build_water_rocks()
    movers = build_pads()
    build_plants()
    material = kit.vertex_color_material()
    objects = [POND.finish(material, collection)]
    objects += [piece.finish(material, collection) for piece in movers]
    objects += [piece.finish(material, collection) for piece in kit.SWAYING]
    return objects


def preview():
    """A picture from the website's camera, with a flat stand-in for the water."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.5, 0.75, 0.9, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
    water = bpy.context.active_object
    water_mat = bpy.data.materials.new("water")
    water_mat.diffuse_color = (0.1, 0.55, 0.6, 1)
    water_mat.use_nodes = True
    water_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.05, 0.45, 0.5, 1)
    water.data.materials.append(water_mat)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.2
    sun.rotation_euler = (math.radians(35), math.radians(15), math.radians(20))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.sensor_fit = "VERTICAL"
    cam.data.angle_y = math.radians(42)   # three.js measures the field of view up and down
    scene.collection.objects.link(cam)
    scene.camera = cam
    position = kit.TO_BLENDER @ Vector((0, 15, 14))   # the same as pondScene.js
    target = kit.TO_BLENDER @ Vector((0, 0, -0.6))
    cam.location = position
    cam.rotation_euler = (target - position).to_track_quat("-Z", "Y").to_euler()
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(PREVIEW_DIR, "pond.png")
    bpy.ops.render.render(write_still=True)
    for obj in (sun, cam, water):
        bpy.data.objects.remove(obj)


def export():
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(GLB_PATH),
        export_format="GLB",
        export_apply=True,
        export_extras=True,           # "stage" on the pads, "sway" / "speed" on the plants
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
    bake_ambient_occlusion(objects, samples=8 if "--fast" in sys.argv else 40)
    if "--preview" in sys.argv:
        preview()
    export()
    size = os.path.getsize(GLB_PATH)
    print("POND_DONE", os.path.abspath(GLB_PATH), f"{size / 1024:.0f} KB", f"{len(objects)} objects")
