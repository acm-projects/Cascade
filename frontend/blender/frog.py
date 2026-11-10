"""The frog that leaps across the lily pads on the "How it works" page, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/frog.py
    (add  -- --preview  to also render preview pictures into frontend/blender/previews/)

It makes:
    frontend/blender/frog.blend      - open this in Blender to look at or edit the frog
    frontend/public/models/frog.glb  - the file the website loads (features/howItWorks/pondScene.js)

The look: chunky low-poly blocks with softly bevelled edges, like the capybara.
It faces -Y in Blender (toward you on the website), sits on the ground at Z = 0 and is about 1 tall.
Two animations (each one is an NLA track, so the website gets one clip per track):
    "Idle" - a 4 second loop: the throat puffs, it breathes and blinks
    "Leap" - 0.8 seconds: crouch, kick the back legs out, reach forward, tuck in and land.
             The website moves the frog through the air in time with it.
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "frog.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "frog.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

FPS = 30
IDLE = 4 * FPS   # frames in the idle loop
LEAP = 24        # frames in one leap (0.8 seconds)

COLORS = {
    "skin": "#5cb546",
    "skin_dark": "#3f8f37",
    "spots": "#2f7a30",
    "belly": "#e8e6a4",
    "eye": "#f6f3df",
    "pupil": "#16120c",
    "shine": "#ffffff",
    "mouth": "#24461f",
    "cheek": "#f08a8a",
    "toes": "#7fcc58",
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


def block(name, size, location, material, parent=None, bevel=0.06, rotation=(0, 0, 0)):
    """A box with softly bevelled edges, flat shaded (low-poly look)."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "NONE"
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.shade_flat()
    obj.data.materials.append(material)
    if parent:
        keep_world_parent(obj, parent)
    return obj


def dome(name, radius, location, material, parent=None, squash=1.0):
    """A low-poly half-round lump (eyes, cheeks)."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=10, ring_count=6, radius=radius, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (1, 1, squash)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_flat()
    obj.data.materials.append(material)
    if parent:
        keep_world_parent(obj, parent)
    return obj


def pivot(name, location, parent=None):
    """An empty to rotate/scale a group of parts around a point (legs, eyes, throat)."""
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.12
    obj.location = location
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        bpy.context.view_layer.update()
        keep_world_parent(obj, parent)
    return obj


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    mats = {key: make_material(key, value) for key, value in COLORS.items()}
    mats["eye"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35

    root = pivot("Frog", (0, 0, 0))
    parts = {"root": root}

    # --- Body: a wide, squat loaf that leans back a little (frogs sit tilted up at the front) ---
    body = pivot("Body", (0, 0.05, 0.12), root)
    parts["body"] = body
    block("Torso", (0.92, 0.86, 0.46), (0, 0.06, 0.36), mats["skin"], body, bevel=0.16, rotation=(-0.22, 0, 0))
    block("Back", (0.7, 0.6, 0.12), (0, 0.16, 0.6), mats["skin_dark"], body, bevel=0.05, rotation=(-0.22, 0, 0))
    for x, y, s in [(-0.18, 0.2, 0.1), (0.2, 0.08, 0.08), (0.04, 0.3, 0.07)]:
        block(f"Spot_{x}", (s, s, 0.03), (x, y, 0.67 - y * 0.2), mats["spots"], body, bevel=0.01, rotation=(-0.22, 0, 0))
    block("Belly", (0.66, 0.2, 0.34), (0, -0.33, 0.3), mats["belly"], body, bevel=0.08, rotation=(-0.22, 0, 0))

    # The throat: a soft pouch under the chin that puffs out
    throat = pivot("Throat", (0, -0.42, 0.3), body)
    parts["throat"] = throat
    block("ThroatPouch", (0.42, 0.14, 0.16), (0, -0.44, 0.3), mats["belly"], throat, bevel=0.06)

    # --- Head: part of the body block, with a wide mouth line and big eyes on top ---
    block("Snout", (0.84, 0.36, 0.3), (0, -0.3, 0.56), mats["skin"], body, bevel=0.13)
    block("Mouth", (0.6, 0.03, 0.03), (0, -0.48, 0.47), mats["mouth"], body, bevel=0.0)
    eyes = []
    for side, label in ((1, "L"), (-1, "R")):
        eye = pivot(f"Eye_{label}", (side * 0.27, -0.22, 0.74), body)
        dome(f"EyeBall_{label}", 0.17, (side * 0.27, -0.22, 0.74), mats["skin"], eye)
        dome(f"EyeWhite_{label}", 0.135, (side * 0.29, -0.3, 0.78), mats["eye"], eye)
        dome(f"Pupil_{label}", 0.075, (side * 0.3, -0.41, 0.79), mats["pupil"], eye, squash=1.25)
        dome(f"Shine_{label}", 0.028, (side * 0.27, -0.46, 0.84), mats["shine"], eye)
        eyes.append(eye)
        dome(f"Cheek_{label}", 0.07, (side * 0.36, -0.44, 0.52), mats["cheek"], body, squash=0.5)
    parts["eyes"] = eyes

    # --- Back legs: big folded thighs at the sides, with long feet in front of them ---
    back_legs = []
    for side, label in ((1, "L"), (-1, "R")):
        hip = pivot(f"LegBack_{label}", (side * 0.4, 0.22, 0.24), root)
        block(f"Thigh_{label}", (0.26, 0.5, 0.3), (side * 0.48, 0.12, 0.2), mats["skin_dark"], hip, bevel=0.1)
        block(f"Shin_{label}", (0.16, 0.42, 0.14), (side * 0.52, -0.08, 0.08), mats["skin"], hip, bevel=0.05)
        block(f"Foot_{label}", (0.22, 0.3, 0.05), (side * 0.56, -0.3, 0.025), mats["toes"], hip, bevel=0.02)
        back_legs.append(hip)
    parts["back_legs"] = back_legs

    # --- Front legs: short, planted in front of the belly ---
    front_legs = []
    for side, label in ((1, "L"), (-1, "R")):
        shoulder = pivot(f"LegFront_{label}", (side * 0.26, -0.3, 0.3), root)
        block(f"Arm_{label}", (0.14, 0.13, 0.26), (side * 0.28, -0.34, 0.15), mats["skin"], shoulder, bevel=0.04)
        block(f"Hand_{label}", (0.2, 0.18, 0.04), (side * 0.3, -0.4, 0.02), mats["toes"], shoulder, bevel=0.015)
        front_legs.append(shoulder)
    parts["front_legs"] = front_legs
    return parts


# ---------- Animation: each clip is its own action on every moving part, stacked into a named NLA track ----------

def key(obj, path, frame, value):
    setattr(obj, path, value)
    obj.keyframe_insert(path, frame=frame)


def store_clip(objects, clip_name, smooth=True):
    """Move each object's current action into an NLA track called clip_name, then clear it for the next clip."""
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


def reset(parts):
    for obj in [parts["body"], parts["throat"], *parts["eyes"], *parts["back_legs"], *parts["front_legs"]]:
        obj.rotation_euler = (0, 0, 0)
        obj.scale = (1, 1, 1)
    parts["body"].location = (0, 0.05, 0.12)


def animate_idle(parts):
    body, throat = parts["body"], parts["throat"]
    # Breathing: two slow breaths per loop
    for i in range(5):
        key(body, "scale", i * IDLE / 4, (1, 1, 1.0 if i % 2 == 0 else 1.03))
    # The throat puffs out twice, quickly, in the middle of the loop
    for frame, size in [(0, 1), (40, 1), (46, 1.45), (52, 1.05), (58, 1.4), (66, 1), (IDLE, 1)]:
        key(throat, "scale", frame, (size, size, size))
    # A blink at about 3 seconds
    for eye in parts["eyes"]:
        for frame, height in [(0, 1), (88, 1), (91, 0.15), (94, 1), (IDLE, 1)]:
            key(eye, "scale", frame, (1, 1, height))
    store_clip([body, throat, *parts["eyes"]], "Idle")


def animate_leap(parts):
    body = parts["body"]
    base = (0, 0.05, 0.12)
    # Body: squash down, stretch long in the air, squash on landing, settle
    for frame, (sx, sy, sz), lift, tilt in [
        (0, (1, 1, 1), 0, 0),
        (4, (1.08, 1.0, 0.8), -0.05, 0.12),     # crouch
        (8, (0.92, 1.18, 1.05), 0.05, -0.35),   # launch: long and leaning forward
        (14, (0.95, 1.1, 1.0), 0.05, -0.1),     # in the air
        (19, (1.1, 0.95, 0.82), -0.04, 0.12),   # land
        (24, (1, 1, 1), 0, 0),
    ]:
        key(body, "scale", frame, (sx, sy, sz))
        key(body, "location", frame, (base[0], base[1], base[2] + lift))
        key(body, "rotation_euler", frame, (tilt, 0, 0))
    # Back legs kick straight out behind, then fold back in
    for leg in parts["back_legs"]:
        for frame, angle in [(0, 0), (4, -0.15), (8, 1.9), (13, 1.5), (18, -0.1), (24, 0)]:
            key(leg, "rotation_euler", frame, (angle, 0, 0))
    # Front legs reach forward to land
    for leg in parts["front_legs"]:
        for frame, angle in [(0, 0), (4, 0.1), (8, 0.5), (14, -0.6), (19, 0.2), (24, 0)]:
            key(leg, "rotation_euler", frame, (angle, 0, 0))
    # Eyes squeeze shut on take-off, pop open in the air
    for eye in parts["eyes"]:
        for frame, height in [(0, 1), (5, 0.4), (9, 1.1), (24, 1)]:
            key(eye, "scale", frame, (1, 1, height))
    store_clip([body, *parts["back_legs"], *parts["front_legs"], *parts["eyes"]], "Leap")


def preview():
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x, scene.render.resolution_y = 640, 480
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.45, 0.8, 0.85, 1)
    bpy.ops.mesh.primitive_plane_add(size=20)
    ground = bpy.context.active_object
    ground.data.materials.append(make_material("ground", "#cfe8e4"))
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(40), math.radians(10), math.radians(30))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 60
    scene.collection.objects.link(cam)
    scene.camera = cam
    from mathutils import Vector
    target = Vector((0, 0, 0.4))
    # Show the idle pose, and the leap at take-off, by playing each NLA track on its own
    for name, position, track_name, frame in [("frog-front", (2.2, -4.2, 2.4), "Idle", 0),
                                              ("frog-side", (5, 0, 1.4), "Idle", 0),
                                              ("frog-leap", (5, -1.5, 1.6), "Leap", 10)]:
        for obj in bpy.data.objects:
            if obj.animation_data:
                for track in obj.animation_data.nla_tracks:
                    track.mute = track.name != track_name
        cam.location = position
        cam.rotation_euler = (target - Vector(position)).to_track_quat("-Z", "Y").to_euler()
        scene.frame_set(frame)
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        scene.render.filepath = os.path.join(PREVIEW_DIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)
    for obj in bpy.data.objects:
        if obj.animation_data:
            for track in obj.animation_data.nla_tracks:
                track.mute = False
    for obj in (ground, sun, cam):
        bpy.data.objects.remove(obj)


def export():
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(GLB_PATH),
        export_format="GLB",
        export_apply=True,
        export_animations=True,
        export_animation_mode="NLA_TRACKS",   # one clip per track name: "Idle" and "Leap"
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
    animate_leap(parts)
    reset(parts)
    if "--preview" in sys.argv:
        preview()
    export()
    print("FROG_DONE", os.path.abspath(GLB_PATH), os.path.getsize(GLB_PATH))
