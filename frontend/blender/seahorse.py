"""Cassie, Cascade's seahorse, built in Blender. She floats on the Projects page and is the face of the AI Studio chat.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/seahorse.py
    (add  -- --preview  to also render preview pictures into frontend/blender/previews/)

It makes:
    frontend/blender/seahorse.blend      - open this in Blender to look at or edit Cassie
    frontend/public/models/seahorse.glb  - the file the website loads (features/landing3d/seahorseScene.js)

The look: low-poly and flat shaded, like the frog and the capybara. Her body and tail are one ringed tube each
(every other ring bulges a little, like a real seahorse's armour plates), with a lighter belly down the front; her
head is a faceted skull with a tube snout, and her fins are scalloped fans with light and dark rays.
She has two rows of little cyan and pink spots down her sides. Her fins and spots glow a little (see GLOW below).
She is built side-on: the snout points +X, so the website's camera (looking from -Y) sees her classic profile.
She is about 1.7 tall, with the bottom of her curled tail near Z = 0.
One animation, "Idle" (a 4 second loop, an NLA track like the frog's clips):
    she bobs up and down and sways, the back fin flutters fast, the little side fins paddle,
    the tail curls a bit tighter and back, the head nods, and she blinks once.
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "seahorse.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "seahorse.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

FPS = 30
IDLE = 4 * FPS   # frames in the idle loop

COLORS = {
    "body": "#ff9444",
    "body_dark": "#ee6f3a",
    "belly": "#ffd89c",
    "belly_dark": "#ffc67e",
    "crown": "#ffbe4a",
    "snout_tip": "#d9592f",
    "fin": "#5fd6e6",
    "fin_dark": "#36b3c6",
    "eye": "#f6f3df",
    "pupil": "#16120c",
    "shine": "#ffffff",
    "cheek": "#ff7d97",
}
# A little glow (Sai asked for "a little"): only her fins and side spots give off a soft light of their own.
# Raise these for more glow; an empty GLOW = {} turns it off.
GLOW = {"fin": 0.35, "fin_dark": 0.25, "spot_cyan": 0.8, "spot_pink": 0.7, "tail_glow": 0.8}
COLORS.update({"spot_cyan": "#8ff8ff", "spot_pink": "#ffb3f0", "tail_glow": "#9ffbff"})


def srgb_to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def make_material(name, hex_color, roughness=0.8, glow=0.0):
    color = [srgb_to_linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    if glow:
        shader.inputs["Emission Color"].default_value = (*color, 1)
        shader.inputs["Emission Strength"].default_value = glow
    mat.diffuse_color = (*color, 1)
    return mat


def keep_world_parent(child, parent):
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def block(name, size, location, material, parent=None, bevel=0.03, rotation=(0, 0, 0)):
    """A box with softly bevelled edges, flat shaded (low-poly look)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = min(bevel, min(size) * 0.45)
        mod.segments = 2
        mod.limit_method = "NONE"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.shade_flat()
    obj.data.materials.append(material)
    if parent:
        keep_world_parent(obj, parent)
    return obj


def dome(name, radius, location, material, parent=None, squash=(1, 1, 1)):
    """A low-poly round lump (eyes, cheeks)."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=radius, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = squash
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_flat()
    obj.data.materials.append(material)
    if parent:
        keep_world_parent(obj, parent)
    return obj


def spike(name, radius, height, location, material, parent=None, tilt=0.0):
    """A four-sided pointy cone (crown spikes, back ridges)."""
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=radius, radius2=0.012, depth=height,
                                    location=location, rotation=(0, tilt, 0))
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.shade_flat()
    obj.data.materials.append(material)
    if parent:
        keep_world_parent(obj, parent)
    return obj


def pivot(name, location, parent=None):
    """An empty to rotate/scale a group of parts around a point (head, tail, fins, eyes)."""
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.1
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        bpy.context.view_layer.update()
        keep_world_parent(obj, parent)
    return obj


def segment(name, p0, p1, width, depth, material, parent, overlap=1.3, bevel=0.04):
    """A block lying along the line p0 -> p1 in the X/Z plane (the seahorse's centre line)."""
    dx, dz = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dz) * overlap
    angle = math.atan2(dx, dz)   # turning about Y by this points the block's Z along the line
    centre = ((p0[0] + p1[0]) / 2, 0, (p0[1] + p1[1]) / 2)
    return block(name, (width, depth, length), centre, material, parent, bevel=bevel, rotation=(0, angle, 0))


# The centre line of the body, from the neck down to where the tail starts, and how thick it is there.
# The belly bulges forward (+X, the same way the snout points); the back is on the -X side.
BODY_KEYS = [
    # (x, z, thickness front-to-back, thickness side-to-side)
    (0.00, 1.30, 0.26, 0.26),
    (0.07, 1.12, 0.36, 0.30),
    (0.15, 0.93, 0.50, 0.35),
    (0.16, 0.74, 0.52, 0.36),
    (0.10, 0.56, 0.42, 0.32),
    (0.02, 0.42, 0.30, 0.25),
    (-0.05, 0.30, 0.21, 0.19),
]


def smooth_line(keys, per_gap=2):
    """Catmull-Rom through the key points, so the body curves smoothly but stays low-poly."""
    out = []
    for i in range(len(keys) - 1):
        p0, p1, p2 = keys[max(i - 1, 0)], keys[i], keys[i + 1]
        p3 = keys[min(i + 2, len(keys) - 1)]
        for step in range(per_gap):
            t = step / per_gap
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * b) + (-a + c) * t + (2 * a - 5 * b + 4 * c - d) * t2 + (-a + 3 * b - 3 * c + d) * t3)
                             for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(keys[-1])
    return out


BODY = smooth_line(BODY_KEYS)


def tail_points(steps=12):
    """The curled tail: a spiral that goes down from the body, curls forward under the belly and up."""
    cx, cz = 0.08, 0.17
    points = []
    for i in range(steps + 1):
        t = i / steps
        angle = math.pi * (1.0 + 1.75 * t)          # starts on the back side and winds forward and up
        radius = 0.15 * (1 - t) + 0.035 * t
        points.append((cx + radius * math.cos(angle), cz + radius * math.sin(angle), 0.17 * (1 - t) + 0.06 * t))
    return points


def finish_mesh(name, verts, faces, face_mats, materials, parent=None, smooth=False):
    """Turn raw points and faces into a flat-shaded object with its materials, normals facing out."""
    import bmesh
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    for mat in materials:
        mesh.materials.append(mat)
    for poly, index in zip(mesh.polygons, face_mats):
        poly.material_index = index
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        bpy.context.view_layer.update()
        keep_world_parent(obj, parent)
    return obj


def ring_normal(points, i):
    """The direction across the line at point i, in the X/Z plane. Points +X (the belly) while the line runs down."""
    a = points[max(i - 1, 0)]
    b = points[min(i + 1, len(points) - 1)]
    dx, dz = b[0] - a[0], b[1] - a[1]
    size = math.hypot(dx, dz) or 1
    return -dz / size, dx / size


def tube(name, points, materials, parent=None, sides=10, ridges=0.0, belly_mats=None):
    """A low-poly tube along a line in the X/Z plane.
    points:  (x, z, thickness front-to-back, thickness side-to-side)
    ridges:  how much every other ring bulges, for a seahorse's ringed body (0 = smooth)
    belly_mats: (light, dark) material indexes for the faces on the belly side, alternating ring by ring;
                other faces use material 0
    """
    verts, faces, face_mats = [], [], []
    for i, (x, z, front, side) in enumerate(points):
        nx, nz = ring_normal(points, i)
        bulge = 1 + (ridges if i % 2 == 0 else -ridges)
        for j in range(sides):
            angle = j / sides * 2 * math.pi
            across = math.cos(angle) * front / 2 * bulge
            verts.append((x + nx * across, math.sin(angle) * side / 2 * bulge, z + nz * across))
    for i in range(len(points) - 1):
        for j in range(sides):
            a, b = i * sides + j, i * sides + (j + 1) % sides
            faces.append((a, b, b + sides, a + sides))
            mid = (j + 0.5) / sides * 2 * math.pi
            if belly_mats and math.cos(mid) > 0.5:
                face_mats.append(belly_mats[i % 2])
            else:
                face_mats.append(0)
    # close both ends
    faces.append(tuple(range(sides)))
    face_mats.append(0)
    last = (len(points) - 1) * sides
    faces.append(tuple(range(last, last + sides)))
    face_mats.append(0)
    return finish_mesh(name, verts, faces, face_mats, materials, parent)


def lump(name, radius, location, material, parent=None, squash=(1, 1, 1), rotation=(0, 0, 0), detail=1):
    """A faceted low-poly ball (skull, jaw): an icosphere, squashed into shape."""
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=detail, radius=radius, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = squash
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_flat()
    obj.data.materials.append(material)
    if parent:
        keep_world_parent(obj, parent)
    return obj


def fan(name, centre, direction, spread, length, rays, materials, parent=None, thickness=0.025):
    """A fin: a fan of rays in the X/Z plane with a scalloped edge, the rays alternating light and dark."""
    cx, cz = centre
    outer = []
    steps = rays * 2
    for k in range(steps + 1):
        angle = direction - spread / 2 + spread * k / steps
        reach = length if k % 2 == 0 else length * 0.8   # ray tips, and the dips between them
        outer.append((cx + math.cos(angle) * reach, cz + math.sin(angle) * reach))
    verts, faces, face_mats = [], [], []
    half = thickness / 2
    for y in (-half, half):
        verts.append((cx, y, cz))
        verts.extend((x, y, z) for x, z in outer)
    count = len(outer) + 1   # verts per side
    for k in range(len(outer) - 1):
        colour = (k // 2) % 2
        faces.append((0, k + 1, k + 2))
        faces.append((count, count + k + 2, count + k + 1))
        face_mats += [colour, colour]
        faces.append((k + 1, count + k + 1, count + k + 2, k + 2))   # the thin outer edge
        face_mats.append(colour)
    # the two straight sides back to the base
    faces.append((0, count, count + 1, 1))
    faces.append((0, len(outer), count + len(outer), count))
    face_mats += [0, 0]
    return finish_mesh(name, verts, faces, face_mats, materials, parent)


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    mats = {key: make_material(key, value, glow=GLOW.get(key, 0.0)) for key, value in COLORS.items()}
    mats["eye"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35
    mats["fin"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.5

    root = pivot("Seahorse", (0, 0, 0))
    body = pivot("Body", (0.08, 0, 0.8), root)
    parts = {"root": root, "body": body}

    # --- Body: one ringed tube down the S-curve, with a lighter belly down the front ---
    spine = smooth_line(BODY_KEYS, per_gap=4)
    tube("Body", spine, [mats["body"], mats["belly"], mats["belly_dark"]], body, sides=10, ridges=0.07,
         belly_mats=(1, 2))
    # little ridge spikes down the back, on every other ring
    for i in range(2, len(spine) - 3, 3):
        x, z, front, _side = spine[i]
        nx, nz = ring_normal(spine, i)
        back = front / 2 * 1.04
        spike(f"Ridge_{i}", 0.03, 0.09, (x - nx * back, 0, z - nz * back), mats["crown"], body,
              tilt=math.atan2(-nx, -nz))

    # --- Glowing spots: two rows down each side, alternating cyan and pink, like a deep-sea creature ---
    for i in range(2, len(spine) - 2, 2):
        x, z, front, side = spine[i]
        nx, nz = ring_normal(spine, i)
        for s in (-1, 1):
            for row, (forward, colour) in enumerate(((0.28, "spot_cyan"), (-0.2, "spot_pink"))):
                if (i // 2 + row) % 2:
                    continue
                size = 0.024 + 0.01 * math.sin(i * 1.7 + row)
                across = forward * front / 2
                dome(f"Spot_{i}_{row}_{'L' if s < 0 else 'R'}", size,
                     (x + nx * across, s * (side / 2 + 0.005), z + nz * across), mats[colour], body, squash=(1, 0.45, 1))

    # --- Tail: a ringed tube that winds into a curl, on its own pivot so it can curl tighter ---
    tail = pivot("Tail", (-0.05, 0, 0.3), body)
    parts["tail"] = tail
    curl = tail_points(steps=26)
    tail_line = [spine[-1]] + [(x, z, thickness, thickness * 1.05) for x, z, thickness in curl]
    tube("Tail", tail_line, [mats["body"], mats["belly"], mats["belly_dark"]], tail, sides=8, ridges=0.08,
         belly_mats=(1, 2))
    end = curl[-1]
    dome("TailTip", 0.045, (end[0], 0, end[1]), mats["tail_glow"], tail)

    # --- Back fin: a scalloped fan on the back (-X side), which flutters ---
    fin = pivot("BackFin", (-0.1, 0, 0.74), body)
    parts["fin"] = fin
    fan("BackFin", (-0.08, 0.74), math.pi, math.radians(110), 0.3, 4, [mats["fin"], mats["fin_dark"]], fin)

    # --- Head: a rounded skull on top of the neck, a long tube snout pointing +X, a crown, big eyes ---
    head = pivot("Head", (0.02, 0, 1.3), body)
    parts["head"] = head
    lump("Skull", 0.2, (0.02, 0, 1.43), mats["body"], head, squash=(1.0, 0.8, 0.85), rotation=(0, math.radians(-12), 0))
    lump("Jaw", 0.14, (0.12, 0, 1.33), mats["belly"], head, squash=(1.0, 0.85, 0.6))
    tube("Snout", [(0.14, 1.38, 0.13, 0.12), (0.3, 1.37, 0.11, 0.1), (0.44, 1.36, 0.1, 0.1), (0.48, 1.36, 0.13, 0.13)],
         [mats["body"]], head, sides=8)
    tube("SnoutTip", [(0.48, 1.36, 0.15, 0.15), (0.55, 1.36, 0.15, 0.15)], [mats["snout_tip"]], head, sides=8)
    # crown: a coronet of spikes on top of the head
    for i, (x, tilt, height) in enumerate([(-0.12, -34, 0.12), (-0.05, -16, 0.18), (0.03, 0, 0.21), (0.1, 16, 0.14)]):
        spike(f"Crown_{i}", 0.045, height, (x, 0, 1.55 + height / 2 - 0.02), mats["crown"], head,
              tilt=math.radians(tilt))
    # eyes on both sides (the camera sees the -Y one)
    eyes = []
    for side, label in ((-1, "L"), (1, "R")):
        eye = pivot(f"Eye_{label}", (0.06, side * 0.15, 1.45), head)
        dome(f"EyeBall_{label}", 0.09, (0.06, side * 0.13, 1.45), mats["body"], eye)
        dome(f"EyeWhite_{label}", 0.08, (0.07, side * 0.17, 1.46), mats["eye"], eye, squash=(1, 0.8, 1))
        dome(f"Pupil_{label}", 0.043, (0.09, side * 0.23, 1.46), mats["pupil"], eye, squash=(1, 0.7, 1.15))
        dome(f"Shine_{label}", 0.016, (0.105, side * 0.25, 1.485), mats["shine"], eye)
        dome(f"Cheek_{label}", 0.042, (0.18, side * 0.11, 1.33), mats["cheek"], head, squash=(1.2, 0.5, 0.7))
        eyes.append(eye)
    parts["eyes"] = eyes
    # little side fins just behind the head (paddle)
    side_fins = []
    for side, label in ((-1, "L"), (1, "R")):
        side_fin = pivot(f"SideFin_{label}", (-0.02, side * 0.14, 1.2), body)
        plate = fan(f"SideFinPlate_{label}", (-0.02, 1.2), math.radians(200), math.radians(70), 0.11, 2,
                    [mats["fin"], mats["fin_dark"]], side_fin, thickness=0.015)
        plate.location.y += side * 0.15
        side_fins.append(side_fin)
    parts["side_fins"] = side_fins
    return parts


# ---------- Animation: the clip is its own action on every moving part, stacked into a named NLA track ----------

def key(obj, path, frame, value):
    setattr(obj, path, value)
    obj.keyframe_insert(path, frame=frame)


def store_clip(objects, clip_name, smooth=True):
    """Move each object's current action into an NLA track called clip_name, then clear it."""
    for obj in objects:
        anim = obj.animation_data
        if not anim or not anim.action:
            continue
        action = anim.action
        action.name = f"{clip_name}_{obj.name}"
        if smooth:
            for curve in action.fcurves if hasattr(action, "fcurves") else []:
                for point in curve.keyframe_points:
                    point.interpolation = "BEZIER"
        track = anim.nla_tracks.new()
        track.name = clip_name
        strip = track.strips.new(clip_name, int(action.frame_range[0]), action)
        strip.name = clip_name
        anim.action = None


def wave(count, low, high, cycles=1, phase=0.0):
    """count+1 evenly spaced (frame, value) keys over the loop, following a sine between low and high."""
    keys = []
    for i in range(count + 1):
        t = i / count
        s = math.sin((t * cycles + phase) * 2 * math.pi)
        keys.append((t * IDLE, low + (high - low) * (s + 1) / 2))
    return keys


def animate_idle(parts):
    root, body, head, tail, fin = parts["root"], parts["body"], parts["head"], parts["tail"], parts["fin"]
    # Bob: up and down once per loop
    for frame, lift in wave(8, 0.0, 0.08):
        key(root, "location", frame, (0, 0, lift))
    # Sway: lean back and forth (about Y, in the side-on view), a little behind the bob
    for frame, lean in wave(8, -0.06, 0.06, phase=0.25):
        key(body, "rotation_euler", frame, (0, lean, 0))
    # Head: a small nod, twice per loop
    for frame, nod in wave(8, -0.05, 0.05, cycles=2):
        key(head, "rotation_euler", frame, (0, nod, 0))
    # Tail: curls a little tighter, then relaxes
    for frame, curl in wave(8, -0.14, 0.08, phase=0.5):
        key(tail, "rotation_euler", frame, (0, curl, 0))
    # Back fin: flutters fast (10 times per loop), the way seahorses swim
    for frame, size in wave(40, 0.65, 1.1, cycles=10):
        key(fin, "scale", frame, (size, 1, 1))
    # Side fins: paddle
    for side_fin in parts["side_fins"]:
        for frame, angle in wave(16, -0.4, 0.4, cycles=4):
            key(side_fin, "rotation_euler", frame, (0, 0, angle))
    # A blink at about 3 seconds
    for eye in parts["eyes"]:
        for frame, height in [(0, 1), (88, 1), (91, 0.12), (94, 1), (IDLE, 1)]:
            key(eye, "scale", frame, (1, 1, height))
    store_clip([root, body, head, tail, fin, *parts["side_fins"], *parts["eyes"]], "Idle")


def reset(parts):
    for obj in [parts["body"], parts["head"], parts["tail"], parts["fin"], *parts["side_fins"], *parts["eyes"]]:
        obj.rotation_euler = (0, 0, 0)
        obj.scale = (1, 1, 1)
    parts["root"].location = (0, 0, 0)


def preview():
    scene = bpy.context.scene
    engines = [item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items]
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in engines)
    if scene.render.engine == "CYCLES":
        scene.cycles.samples = 16
    scene.render.resolution_x, scene.render.resolution_y = 360, 480
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.08, 0.35, 0.6, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.6
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(50), math.radians(-20), math.radians(-30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 50
    scene.collection.objects.link(cam)
    scene.camera = cam
    from mathutils import Vector
    for name, position, target, frame in [("seahorse-side", (0.6, -4.6, 1.2), (0.1, 0, 0.85), 0),
                                          ("seahorse-angle", (2.6, -3.8, 1.6), (0.1, 0, 0.85), 45),
                                          ("seahorse-head", (0.75, -1.9, 1.5), (0.18, 0, 1.4), 0)]:
        target = Vector(target)
        cam.location = position
        cam.rotation_euler = (target - Vector(position)).to_track_quat("-Z", "Y").to_euler()
        scene.frame_set(frame)
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        scene.render.filepath = os.path.join(PREVIEW_DIR, f"{name}.png")
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
        export_animations=True,
        export_animation_mode="NLA_TRACKS",   # one clip per track name: "Idle"
        export_force_sampling=True,
        export_optimize_animation_size=True,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
    )


if __name__ == "__main__":
    parts = build()
    animate_idle(parts)
    reset(parts)
    if "--preview" in sys.argv:
        preview()
    export()
    print("SEAHORSE_DONE", os.path.abspath(GLB_PATH), os.path.getsize(GLB_PATH))
