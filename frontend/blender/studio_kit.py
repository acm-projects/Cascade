"""The pieces of AI Studio's island, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/studio_kit.py
    (add  -- --preview  to render frontend/blender/previews/studio-kit.png, and  -- --fast  for a quick bake)

It makes:
    frontend/blender/studio_kit.blend      - open this in Blender to look at or edit the pieces
    frontend/public/models/studio_kit.glb  - the file the website loads (features/studio/world/studioWorldScene.js)

AI Studio's island changes shape with your clips, so it can't be one fixed model like the Landing island.
Instead this is a kit of pieces the website places where they're needed: trees, palms, ferns, a berry bush,
rocks, mushrooms, the three-step waterfall cliff (your video), rocky rims for the ponds, the clip platform,
and a dock with a boat. Same chunky low-poly style and colors as the Landing island (island.py), with soft
shadows baked into the colors.

Each piece is an empty named "Kit_<Name>" at the origin, standing on the ground (y = 0 on the website).
Parts that should sway are separate children with "sway" and "speed" custom properties (like island.py).
The cliff's numbers match CLIFF in studioWorldScene.js: its steps' front edges and heights, 3.8 deep, with a
1.9 wide channel down the middle where the website draws the water.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import island as kit  # noqa: E402  (the island's shapes, Piece, colors)

BLEND_PATH = os.path.join(HERE, "studio_kit.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "studio_kit.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

CLIFF = [(-2.2, 4.6), (-0.9, 3.2), (0.4, 1.8)]   # (front edge x, height) of each step, back to front
CLIFF_BACK = -4.6
CLIFF_DEPTH = 3.8
CHANNEL = 1.9

random = kit.random
pick = kit.pick
transform = kit.transform
C = dict(kit.COLORS)
C.update({
    "fruit": "#f0912e", "berry": ["#ff9ec7", "#c993f0", "#ffd34d"], "moss": ["#3f8f3a", "#4c9e3f"],
    "cap": "#ef5b4a", "spot": "#fff4e0", "reed": ["#6fae3a", "#5d9c33"], "cattail": "#7a4f2c",
    "plank": ["#a06f3c", "#8f6234"], "post": "#70492a", "hull": "#b5763a",
    "stone": ["#9a938c", "#8c857f", "#a59e96"],   # lighter rocks: the baked shadows darken them a lot
})

ITEMS = []   # (root empty, [mesh objects])


def item(name):
    """Start a kit piece: an empty at the origin; its parts are parented to it."""
    root = bpy.data.objects.new(f"Kit_{name}", None)
    root.empty_display_size = 0.3
    bpy.context.scene.collection.objects.link(root)
    parts = []
    ITEMS.append((root, parts))
    return root, parts


def finish(piece, root, parts, material):
    obj = piece.finish(material, bpy.context.scene.collection)
    obj.parent = root
    parts.append(obj)
    return obj


# ---------- Plants ----------

def tree(material, name, size=1.0, fruit=False, tall=False):
    root, parts = item(name)
    height = (1.6 if tall else 1.1) * size
    base = kit.Piece(f"{name}_Trunk")
    base.add(kit.cylinder_shape(0.1 * size, 0.17 * size, height, 6), C["trunk"], transform((0, height / 2, 0)))
    for i in range(3):   # roots spreading at the bottom
        angle = i / 3 * math.tau + 0.4
        base.add(kit.box_shape(0.08 * size, 0.08 * size, 0.3 * size), C["trunk"],
                 transform((math.sin(angle) * 0.14 * size, 0.04, math.cos(angle) * 0.14 * size), (0.3, angle, 0), "YXZ"))
    finish(base, root, parts, material)
    crown = kit.Piece(f"{name}_Crown", transform((0, height, 0)), {"sway": 0.025, "speed": 0.8 + random() * 0.4})
    blobs = [(0, 0.5, 0, 0.42), (0, 0.95, 0, 0.32), (0.2, 0.2, 0.1, 0.34)] if tall else \
        [(0, 0.35, 0, 0.62), (0.36, 0.12, 0.1, 0.42), (-0.32, 0.16, 0.16, 0.45), (0.04, 0.15, -0.36, 0.42), (0.05, 0.78, 0, 0.36)]
    for bx, by, bz, r in blobs:
        color = pick(C["brightLeaves"]) if by > 0.7 else pick(C["leaves"])
        crown.add(kit.lumpy_ball(r * size * (1.15 if tall else 1)), color, transform((bx * size, by * size, bz * size)))
    if fruit:
        for i in range(8):
            bx, by, bz, r = blobs[i % len(blobs)]
            angle = random() * math.tau
            lift = 0.1 + random() * 0.5
            out = math.sqrt(1 - lift * lift) * r * size * 0.98
            crown.add(kit.icosphere_shape(0.075 * size, 1), C["fruit"],
                      transform((bx * size + math.cos(angle) * out, by * size + lift * r * size, bz * size + math.sin(angle) * out)))
    finish(crown, root, parts, material)


def palm(material, name, size=1.0, bend=0.06, leaves=8):
    root, parts = item(name)
    trunk = kit.Piece(f"{name}_Trunk")
    lean = height = 0
    for i in range(6):
        lean = i * bend * size
        trunk.add(kit.cylinder_shape(0.09 * size * (1 - i * 0.07), 0.12 * size * (1 - i * 0.07), 0.46 * size, 6),
                  C["trunk"] if i % 2 else "#6a4428", transform((lean, height + 0.23 * size, 0), (0, 0, -bend * 1.5)))
        height += 0.43 * size
    finish(trunk, root, parts, material)
    crown = kit.Piece(f"{name}_Crown", transform((lean + 0.06, height, 0)), {"sway": 0.05, "speed": 1.05 + random() * 0.5})
    colors = C["leaves"] + C["brightLeaves"]
    for i in range(leaves):
        crown.add(kit.leaf_shape(1.35 * size, 0.46 * size, 0.72 * size), pick(colors),
                  transform((0, 0, 0), (-0.3 - random() * 0.15, i / leaves * math.tau + random() * 0.2, 0), "YXZ"))
    for cx, cz in [(0.11, 0.05), (-0.07, 0.1), (0.02, -0.12)]:
        crown.add(kit.icosphere_shape(0.1 * size, 1), "#6b4423", transform((cx * size, -0.1 * size, cz * size)))
    finish(crown, root, parts, material)


def fern(material, name, size=1.0, bright=False):
    root, parts = item(name)
    plant = kit.Piece(f"{name}_Leaves", None, {"sway": 0.05, "speed": 1.3 + random() * 0.8})
    count = 8
    for i in range(count):
        color = C["brightLeaves"][i % 2] if bright else C["leaves"][i % 4]
        plant.add(kit.leaf_shape((0.74 + random() * 0.32) * size, 0.42 * size, 0.42 * size), color,
                  transform((0, 0, 0), (-0.72 - random() * 0.2, i / count * math.tau + random() * 0.4, 0), "YXZ"))
    finish(plant, root, parts, material)


def bush(material):
    root, parts = item("Bush")
    shape = kit.Piece("Bush_Leaves")
    for bx, by, bz, r in [(0, 0.3, 0, 0.42), (0.32, 0.2, 0.08, 0.3), (-0.3, 0.22, 0.12, 0.32), (0.05, 0.5, -0.08, 0.28)]:
        shape.add(kit.lumpy_ball(r), pick(C["leaves"]), transform((bx, by, bz), scale=(1, 0.85, 1)))
    for _ in range(10):
        angle = random() * math.tau
        shape.add(kit.icosphere_shape(0.06, 0), pick(C["berry"]),
                  transform((math.cos(angle) * 0.42, 0.25 + random() * 0.35, math.sin(angle) * 0.38)))
    finish(shape, root, parts, material)


def rocks(material):
    for name, pieces in [
        ("RockA", [(0, 0, 0, 0.42, 0.7)]),
        ("RockB", [(0, 0, 0, 0.36, 0.75), (0.38, 0, 0.15, 0.22, 0.7)]),
        ("RockC", [(0, 0, 0, 0.5, 0.45), (-0.3, 0, -0.25, 0.2, 0.8), (0.32, 0, -0.2, 0.16, 0.8)]),
    ]:
        root, parts = item(name)
        shape = kit.Piece(f"{name}_Stone")
        for x, y, z, r, squash in pieces:
            shape.add(kit.lumpy_ball(r, 0.22, 0), pick(C["stone"]), transform((x, y + r * squash * 0.55, z), scale=(1, squash, 1)))
            shape.add(kit.lumpy_ball(r * 0.7, 0.2, 0), pick(C["moss"]), transform((x - r * 0.1, y + r * squash * 1.0, z), scale=(1, 0.3, 1)))
        finish(shape, root, parts, material)


def mushrooms(material):
    root, parts = item("Mushrooms")
    shape = kit.Piece("Mushrooms_Caps")
    for x, z, size in [(0, 0, 1.1), (0.22, 0.12, 0.8), (-0.16, 0.18, 0.65)]:
        shape.add(kit.cylinder_shape(0.05 * size, 0.07 * size, 0.22 * size, 6), C["cream"], transform((x, 0.11 * size, z)))
        verts, faces = [], []
        rings, sides = 3, 8
        for r in range(rings + 1):
            phi = r / rings * math.pi / 2
            for s in range(sides):
                a = s / sides * math.tau
                verts.append((math.cos(phi) * math.sin(a) * 0.17 * size, math.sin(phi) * 0.14 * size, math.cos(phi) * math.cos(a) * 0.17 * size))
        for r in range(rings):
            for s in range(sides):
                n = (s + 1) % sides
                faces.append((r * sides + s, r * sides + n, (r + 1) * sides + n, (r + 1) * sides + s))
        faces.append(tuple(range(sides))[::-1])
        shape.add((verts, faces), C["cap"], transform((x, 0.2 * size, z)))
        for k in range(3):   # white spots on the cap
            a = k / 3 * math.tau + x
            shape.add(kit.icosphere_shape(0.025 * size, 0), C["spot"],
                      transform((x + math.sin(a) * 0.09 * size, 0.3 * size, z + math.cos(a) * 0.09 * size)))
    finish(shape, root, parts, material)


# ---------- The waterfall cliff (your video) ----------

def cliff(material):
    root, parts = item("Cliff")
    rock = kit.Piece("Cliff_Rock")
    side = (CLIFF_DEPTH - CHANNEL) / 2
    for i, (front, height) in enumerate(CLIFF):
        back = CLIFF_BACK if i == 0 else CLIFF[i - 1][0]
        width = front - back
        middle = back + width / 2
        # the body: dark rock up to a band of dirt, a lighter rock layer in the middle
        rock.add(kit.box_shape(width, height - 0.7, CLIFF_DEPTH), pick(C["deepRock"]), transform((middle, (height - 0.7) / 2, 0)))
        for layer in range(1, int(height / 1.1)):
            rock.add(kit.box_shape(width + 0.03, 0.18, CLIFF_DEPTH + 0.03), pick(C["rock"]), transform((middle, layer * 1.1 - 0.4, 0)))
        dirt_color = pick(C["dirt"])
        # Soil belongs under the grassy banks, not across the open water channel.
        for bank in (-1, 1):
            rock.add(kit.box_shape(width, 0.48, side), dirt_color,
                     transform((middle, height - 0.46, bank * (CHANNEL / 2 + side / 2))))
        # grass on top either side of the water channel, with tufts
        for s in (-1, 1):
            z = s * (CHANNEL / 2 + side / 2)
            rock.add(kit.beveled_box(width, 0.24, side, 0.04), pick(C["grass"]), transform((middle, height - 0.1, z)))
            for _ in range(6):
                rock.add(kit.cone_shape(0.06, 0.22, 4), pick(["#4fae3b", "#5fc24a", "#3f9a36"]),
                         transform((back + random() * width, height + 0.12, z + (random() - 0.5) * side * 0.8)))
            # moss and little ferns hanging down the front face
            for _ in range(3):
                drop = 0.4 + random() * 1.0
                rock.add(kit.box_shape(0.06, drop, 0.3 + random() * 0.3), pick(C["moss"]),
                         transform((front + 0.03, height - 0.25 - drop / 2, s * (CHANNEL / 2 + 0.25 + random() * (side - 0.5)))))
        # boulders where the water lands
        below = CLIFF[i + 1][1] if i + 1 < len(CLIFF) else 0
        for s in (-1, 1):
            r = 0.28 + random() * 0.15
            rock.add(kit.lumpy_ball(r, 0.22, 0), pick(C["stone"]),
                     transform((front + 0.35, below + r * 0.4, s * (CHANNEL / 2 + 0.15)), scale=(1, 0.7, 1)))
    finish(rock, root, parts, material)


def rim(material, name, radius, stones):
    """A ring of rocks around a pond, with a few reeds."""
    root, parts = item(name)
    ring = kit.Piece(f"{name}_Stones")
    for i in range(stones):
        a = i / stones * math.tau
        r = 0.16 + random() * 0.1
        ring.add(kit.lumpy_ball(r, 0.22, 0), pick(C["stone"]),
                 transform((math.cos(a) * radius, r * 0.35, math.sin(a) * radius), scale=(1.2, 0.6, 1)))
    for k in range(3):
        a = k / 3 * math.tau + 0.6
        for j in range(4):
            h = 0.5 + random() * 0.4
            x = math.cos(a) * (radius + 0.25) + (random() - 0.5) * 0.25
            z = math.sin(a) * (radius + 0.25) + (random() - 0.5) * 0.25
            ring.add(kit.box_shape(0.04, h, 0.04), pick(C["reed"]), transform((x, h / 2, z)))
            if j % 2 == 0:
                ring.add(kit.box_shape(0.08, 0.18, 0.08), C["cattail"], transform((x, h * 0.88, z)))
    finish(ring, root, parts, material)


# ---------- The clip platform, the dock and the boat ----------

def platform(material):
    root, parts = item("Platform")
    shape = kit.Piece("Platform_Base")
    shape.add(kit.cylinder_shape(0.75, 0.88, 0.3, 8), pick(C["stone"]), transform((0, 0.15, 0)))
    for k in range(5):   # planks across the top
        shape.add(kit.box_shape(1.3 - abs(k - 2) * 0.25, 0.07, 0.24), C["plank"][k % 2], transform((0, 0.34, -0.5 + k * 0.25)))
    shape.add(kit.cylinder_shape(0.035, 0.04, 1.3, 6), C["post"], transform((0.5, 1.0, -0.3)))
    shape.add(kit.icosphere_shape(0.06, 1), "#ffd34d", transform((0.5, 1.68, -0.3)))   # a little brass knob on top
    finish(shape, root, parts, material)


def dock(material):
    root, parts = item("Dock")
    shape = kit.Piece("Dock_Planks")
    for i in range(7):
        shape.add(kit.box_shape(0.8, 0.06, 0.24), C["plank"][i % 2], transform((0, 0.95, -0.6 - i * 0.26)))
    for x, z in [(-0.36, -1.0), (0.36, -1.0), (-0.36, -2.3), (0.36, -2.3)]:
        shape.add(kit.cylinder_shape(0.05, 0.05, 1.0, 6), C["post"], transform((x, 0.5, z)))
    finish(shape, root, parts, material)
    root, parts = item("Boat")
    boat = kit.Piece("Boat_Hull")
    boat.add(kit.beveled_box(0.5, 0.18, 1.0, 0.06), C["hull"], transform((0, 0.09, 0)))
    boat.add(kit.box_shape(0.46, 0.05, 0.14), C["post"], transform((0, 0.2, 0)))
    boat.add(kit.box_shape(0.04, 0.03, 0.9), C["post"], transform((0.22, 0.22, 0.1), (0, 0.3, 0)))
    finish(boat, root, parts, material)


# ---------- Build, bake, export ----------

def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    material = kit.vertex_color_material()
    tree(material, "TreeRound")
    tree(material, "TreeFruit", fruit=True)
    tree(material, "TreeTall", tall=True)
    palm(material, "PalmA")
    palm(material, "PalmB", size=1.1, bend=0.09, leaves=9)
    fern(material, "Fern")
    fern(material, "FernBright", bright=True)
    bush(material)
    rocks(material)
    mushrooms(material)
    cliff(material)
    rim(material, "PondRim", 1.07, 14)
    rim(material, "PoolRim", 1.57, 18)
    platform(material)
    dock(material)


def bake(samples):
    """Soft shadows baked into the colors. The pieces are spread out on a ground plane while baking,
    so each one gets contact shadows on its own, then they're put back at the origin."""
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.world = scene.world or bpy.data.worlds.new("World")
    scene.world.light_settings.distance = 0.8
    for i, (root, _) in enumerate(ITEMS):
        root.location = ((i % 6) * 9, (i // 6) * 9, 0)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(25, 10, 0))
    ground = bpy.context.active_object
    bpy.context.view_layer.update()
    for _, parts in ITEMS:
        for obj in parts:
            mesh = obj.data
            color = mesh.color_attributes["Col"]
            occlusion = mesh.color_attributes.new("AO", "FLOAT_COLOR", "CORNER")
            mesh.color_attributes.active_color = occlusion
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.bake(type="AO", target="VERTEX_COLORS", margin=0)
            for c, o in zip(color.data, occlusion.data):
                shade = 0.5 + 0.5 * o.color[0]
                c.color = (c.color[0] * shade, c.color[1] * shade, c.color[2] * shade, 1)
            mesh.color_attributes.remove(occlusion)
            mesh.color_attributes.active_color = mesh.color_attributes["Col"]
    bpy.data.objects.remove(ground)
    return ITEMS


def preview():
    """All the pieces lined up, from the website's camera angle."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y = 1400, 800
    scene.view_settings.view_transform = "Standard"
    world = scene.world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.75, 0.88, 1)
    bpy.ops.mesh.primitive_plane_add(size=200, location=(25, 10, 0))
    ground = bpy.context.active_object
    ground_material = bpy.data.materials.new("ground")
    ground_material.use_nodes = True
    ground_material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = kit.srgb("#62cd36")
    ground.data.materials.append(ground_material)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3
    sun.rotation_euler = (math.radians(40), math.radians(15), math.radians(30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = 34
    scene.collection.objects.link(cam)
    scene.camera = cam
    target = Vector((22.5, 9.0, 1.2))
    cam.location = target + Vector((30, -30, 34))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    scene.render.filepath = os.path.join(PREVIEW_DIR, "studio-kit.png")
    bpy.ops.render.render(write_still=True)
    for obj in (ground, sun, cam):
        bpy.data.objects.remove(obj)


def export():
    for root, _ in ITEMS:
        root.location = (0, 0, 0)
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(GLB_PATH),
        export_format="GLB",
        export_apply=True,
        export_extras=True,           # "sway" / "speed" on the parts that sway
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
    build()
    bake(8 if "--fast" in sys.argv else 48)
    if "--preview" in sys.argv:
        preview()
    export()
    print("STUDIO_KIT_DONE", os.path.abspath(GLB_PATH), f"{os.path.getsize(GLB_PATH) / 1024:.0f} KB", f"{len(ITEMS)} pieces")
