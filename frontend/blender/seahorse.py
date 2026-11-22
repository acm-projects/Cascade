"""Cassie, Cascade's seahorse, built in Blender. She floats on the Projects page and is the face of the AI Studio chat.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/seahorse.py
    (add  -- --preview  to also render preview pictures into frontend/blender/previews/)

It makes:
    frontend/blender/seahorse.blend      - open this in Blender to look at or edit Cassie
    frontend/public/models/seahorse.glb  - the file the website loads (features/landing3d/seahorseScene.js)

The look: chunky low-poly blocks with softly bevelled edges and flat shading, like the frog and the capybara.
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


def srgb_to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def make_material(name, hex_color, roughness=0.8):
    color = [srgb_to_linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
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


def tail_points():
    """The curled tail: a spiral that goes down from the body, curls forward under the belly and up."""
    cx, cz = 0.08, 0.17
    points = []
    steps = 12
    for i in range(steps + 1):
        t = i / steps
        angle = math.pi * (1.0 + 1.75 * t)          # starts on the back side and winds forward and up
        radius = 0.15 * (1 - t) + 0.035 * t
        points.append((cx + radius * math.cos(angle), cz + radius * math.sin(angle), 0.17 * (1 - t) + 0.06 * t))
    return points


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    mats = {key: make_material(key, value) for key, value in COLORS.items()}
    mats["eye"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35
    mats["fin"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.5

    root = pivot("Seahorse", (0, 0, 0))
    body = pivot("Body", (0.08, 0, 0.8), root)
    parts = {"root": root, "body": body}

    # --- Body: a chain of chunky blocks along the S-curve, with lighter belly plates in front ---
    for i in range(len(BODY) - 1):
        (x0, z0, w0, d0), (x1, z1, w1, d1) = BODY[i], BODY[i + 1]
        width, depth = (w0 + w1) / 2, (d0 + d1) / 2
        segment(f"BodySeg_{i}", (x0, z0), (x1, z1), width, depth, mats["body"], body, overlap=1.15, bevel=0.07)
        # belly plate: pushed forward to the front edge of this segment
        dx, dz = x1 - x0, z1 - z0
        size = math.hypot(dx, dz)
        nx, nz = -dz / size, dx / size     # points to +X (the belly side) while the line runs downward
        push = width / 2 - 0.035
        plate = mats["belly"] if i % 2 == 0 else mats["belly_dark"]
        segment(f"Belly_{i}", (x0 + nx * push, z0 + nz * push), (x1 + nx * push, z1 + nz * push),
                0.13, depth * 0.84, plate, body, overlap=1.0, bevel=0.03)
        # little ridge bumps down the back
        if 0 < i < len(BODY) - 2 and i % 2 == 1:
            back = width / 2 + 0.03
            bx, bz = (x0 + x1) / 2 - nx * back, (z0 + z1) / 2 - nz * back
            spike(f"Ridge_{i}", 0.035, 0.09, (bx, 0, bz), mats["crown"], body,
                  tilt=math.atan2(-nx, -nz))

    # --- Tail: a spiral of shrinking blocks, on its own pivot so it can curl ---
    tail = pivot("Tail", (-0.05, 0, 0.3), body)
    parts["tail"] = tail
    points = tail_points()
    start = (BODY[-1][0], BODY[-1][1])
    previous = start
    for i, (x, z, thickness) in enumerate(points):
        material = mats["body_dark"] if i % 3 == 2 else mats["body"]
        segment(f"TailSeg_{i}", previous, (x, z), thickness, thickness * 1.05, material, tail, overlap=1.45, bevel=0.025)
        previous = (x, z)
    dome("TailTip", 0.04, (previous[0], 0, previous[1]), mats["body_dark"], tail)

    # --- Back fin: a fan of thin see-through-looking plates on the -X side of the body (flutters) ---
    fin = pivot("BackFin", (-0.13, 0, 0.74), body)
    parts["fin"] = fin
    for i, angle in enumerate([-40, -20, 0, 20, 40]):
        rad = math.radians(angle)
        length = 0.3 - abs(angle) * 0.002
        cx = -0.13 - math.cos(rad) * length / 2
        cz = 0.74 + math.sin(rad) * length / 2
        block(f"FinRay_{i}", (length, 0.04, 0.1), (cx, 0, cz), mats["fin"] if i % 2 == 0 else mats["fin_dark"],
              fin, bevel=0.012, rotation=(0, -rad, 0))

    # --- Head: a block on top of the neck, a long snout pointing +X, a crown, big eyes ---
    head = pivot("Head", (0.02, 0, 1.3), body)
    parts["head"] = head
    block("Skull", (0.36, 0.3, 0.3), (0.03, 0, 1.42), mats["body"], head, bevel=0.08, rotation=(0, math.radians(-12), 0))
    block("Jaw", (0.26, 0.24, 0.16), (0.12, 0, 1.31), mats["belly"], head, bevel=0.05, rotation=(0, math.radians(-8), 0))
    block("Snout", (0.32, 0.13, 0.12), (0.34, 0, 1.36), mats["body"], head, bevel=0.035, rotation=(0, math.radians(4), 0))
    block("SnoutTip", (0.08, 0.17, 0.16), (0.51, 0, 1.35), mats["snout_tip"], head, bevel=0.035)
    # crown: a little coronet of spikes on top of the head
    for i, (x, tilt, height) in enumerate([(-0.1, -30, 0.14), (-0.01, -10, 0.2), (0.08, 12, 0.13)]):
        spike(f"Crown_{i}", 0.05, height, (x, 0, 1.56 + height / 2 - 0.02), mats["crown"], head,
              tilt=math.radians(tilt))
    # eyes on both sides (the camera sees the -Y one)
    eyes = []
    for side, label in ((-1, "L"), (1, "R")):
        eye = pivot(f"Eye_{label}", (0.08, side * 0.15, 1.44), head)
        dome(f"EyeBall_{label}", 0.1, (0.08, side * 0.14, 1.44), mats["body"], eye)
        dome(f"EyeWhite_{label}", 0.085, (0.09, side * 0.18, 1.45), mats["eye"], eye, squash=(1, 0.8, 1))
        dome(f"Pupil_{label}", 0.045, (0.11, side * 0.245, 1.45), mats["pupil"], eye, squash=(1, 0.7, 1.15))
        dome(f"Shine_{label}", 0.017, (0.125, side * 0.265, 1.475), mats["shine"], eye)
        dome(f"Cheek_{label}", 0.045, (0.2, side * 0.12, 1.33), mats["cheek"], head, squash=(1.2, 0.5, 0.7))
        eyes.append(eye)
    parts["eyes"] = eyes
    # little side fins just behind the head (paddle)
    side_fins = []
    for side, label in ((-1, "L"), (1, "R")):
        side_fin = pivot(f"SideFin_{label}", (-0.02, side * 0.14, 1.2), body)
        for j, tilt in enumerate((-25, 10)):
            block(f"SideFinPlate_{label}_{j}", (0.09, 0.02, 0.05), (-0.06, side * 0.15, 1.2 + j * 0.04), mats["fin"],
                  side_fin, bevel=0.008, rotation=(0, math.radians(tilt), 0))
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
