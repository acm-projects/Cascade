"""Cascade's capybara mascot, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/capybara.py

It makes:
    frontend/blender/capybara.blend      - open this in Blender to look at or edit the model
    frontend/public/models/capybara.glb  - the file the website loads (features/landing3d/mascotScene.js)
    frontend/blender/previews/*.png      - preview pictures, if you run it with  -- --preview

The look: chunky low-poly blocks with softly bevelled edges and flat shading, like the Landing island.
It faces +X, stands on the ground at Z = 0 and is about 2.4 long.
The "Idle" animation loops every 6 seconds: slow breathing, a lazy nod, two blinks and an ear flick.
"""
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "capybara.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", "capybara.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

FPS = 30
LOOP = 6 * FPS   # frames in one loop of the idle animation

COLORS = {
    "fur": "#a8703d",
    "fur_dark": "#87562d",
    "fur_back": "#99633a",
    "fur_light": "#c58f5c",
    "belly": "#d3a473",
    "feet": "#5e3a1d",
    "nose": "#33200f",
    "eye": "#1a0f08",
    "shine": "#ffffff",
    "cheek": "#e98f78",
}


def srgb_to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def make_material(name, hex_color, roughness=0.85):
    color = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*[srgb_to_linear(c) for c in color], 1)
    shader.inputs["Roughness"].default_value = roughness
    mat.diffuse_color = (*[srgb_to_linear(c) for c in color], 1)
    return mat


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


def keep_world_parent(child, parent):
    world = child.matrix_world.copy()
    child.parent = parent
    child.matrix_world = world


def pivot(name, location, parent=None):
    """An empty to rotate/scale a group of parts around a point (head, ears, eyes)."""
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_size = 0.15
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
    scene.frame_start = 0
    scene.frame_end = LOOP

    mats = {key: make_material(key, value) for key, value in COLORS.items()}
    mats["eye"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.3

    root = pivot("Capybara", (0, 0, 0))

    # --- Body: a big loaf with a rounder rump, a darker back and a lighter belly ---
    body = pivot("Body", (0, 0, 0.24), root)   # breathing scales around the belly line
    block("Torso", (1.95, 1.2, 1.0), (0, 0, 0.72), mats["fur"], body, bevel=0.22)
    block("Back", (1.55, 1.04, 0.24), (-0.1, 0, 1.18), mats["fur_back"], body, bevel=0.12)   # a soft hump, close to the fur color
    block("Rump", (0.42, 1.08, 0.86), (-0.84, 0, 0.7), mats["fur_back"], body, bevel=0.2)
    block("Chest", (0.3, 0.94, 0.62), (0.88, 0, 0.58), mats["belly"], body, bevel=0.12)
    block("Belly", (1.4, 0.92, 0.16), (0.05, 0, 0.25), mats["belly"], body, bevel=0.06)

    # --- Stubby legs with dark feet ---
    for x in (-0.6, 0.58):
        for y in (-0.38, 0.38):
            block(f"Leg_{'back' if x < 0 else 'front'}_{'L' if y > 0 else 'R'}",
                  (0.34, 0.32, 0.22), (x, y, 0.16), mats["fur_dark"], root, bevel=0.06)
            block(f"Foot_{'back' if x < 0 else 'front'}_{'L' if y > 0 else 'R'}",
                  (0.38, 0.32, 0.1), (x + 0.04, y, 0.05), mats["feet"], root, bevel=0.03)

    # --- Head: big, boxy and blunt, with a square snout ---
    head = pivot("Head", (0.9, 0, 0.94), root)   # nods around the neck
    block("Skull", (1.0, 0.88, 0.82), (1.12, 0, 1.26), mats["fur"], head, bevel=0.18)
    block("Brow", (0.62, 0.8, 0.14), (1.02, 0, 1.68), mats["fur_back"], head, bevel=0.06)
    block("Snout", (0.52, 0.8, 0.66), (1.72, 0, 1.18), mats["fur_light"], head, bevel=0.16)
    block("Chin", (0.44, 0.62, 0.12), (1.64, 0, 0.86), mats["belly"], head, bevel=0.05)
    block("Mouth", (0.05, 0.22, 0.04), (1.98, 0, 0.98), mats["nose"], head, bevel=0.0)

    eyes, ears = [], []
    for side, label in ((1, "L"), (-1, "R")):
        block(f"Nostril_{label}", (0.06, 0.1, 0.08), (2.0, side * 0.17, 1.36), mats["nose"], head, bevel=0.02)
        eye = pivot(f"Eye_{label}", (1.36, side * 0.45, 1.4), head)
        block(f"Eyeball_{label}", (0.17, 0.05, 0.19), (1.36, side * 0.45, 1.4), mats["eye"], eye, bevel=0.02)
        block(f"Shine_{label}", (0.05, 0.02, 0.05), (1.4, side * 0.48, 1.45), mats["shine"], eye, bevel=0.0)
        eyes.append(eye)
        block(f"Cheek_{label}", (0.16, 0.03, 0.08), (1.3, side * 0.45, 1.2), mats["cheek"], head, bevel=0.0)
        ear = pivot(f"Ear_{label}", (0.82, side * 0.3, 1.64), head)
        block(f"EarFlap_{label}", (0.2, 0.14, 0.2), (0.82, side * 0.3, 1.74), mats["fur_dark"], ear, bevel=0.05)
        ears.append(ear)

    animate(body, head, eyes, ears)
    return root


def animate(body, head, eyes, ears):
    # Breathing: two slow breaths per loop (scale the body up a hair along Z)
    for i in range(0, 5):
        frame = i * LOOP / 4
        body.scale = (1, 1, 1.0 if i % 2 == 0 else 1.025)
        body.keyframe_insert("scale", frame=frame)
    # A lazy nod: the head tips down a little and back, twice per loop
    for i, angle in enumerate([0, -0.05, 0, -0.04, 0]):
        head.rotation_euler = (0, -angle, 0)
        head.keyframe_insert("rotation_euler", frame=i * LOOP / 4)
    # Blinks at 2s and 4.6s
    for eye in eyes:
        for frame, height in [(0, 1), (58, 1), (61, 0.1), (64, 1), (136, 1), (139, 0.1), (142, 1), (LOOP, 1)]:
            eye.scale = (1, 1, height)
            eye.keyframe_insert("scale", frame=frame)
    # An ear flick around 3.3s
    for side, ear in zip((1, -1), ears):
        for frame, angle in [(0, 0), (96, 0), (99, side * 0.35), (102, -side * 0.15), (105, side * 0.25), (110, 0), (LOOP, 0)]:
            ear.rotation_euler = (angle, 0, 0)
            ear.keyframe_insert("rotation_euler", frame=frame)
    # Smooth curves for breathing and nodding, quick snaps for blinks and flicks
    for obj in [body, head]:
        for curve in obj.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "SINE"
                point.easing = "EASE_IN_OUT"


def preview():
    """Render a few pictures to check the look (frame 0 front-3/4, side, and mid-blink)."""
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 640
    scene.render.resolution_y = 480
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("World")
    world.color = (0.86, 0.95, 0.94)
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.75, 0.9, 0.9, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, 0))
    ground = bpy.context.active_object
    ground.data.materials.append(make_material("ground", "#cfe8e4"))

    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.5
    sun_obj = bpy.data.objects.new("Sun", sun)
    sun_obj.rotation_euler = (math.radians(45), math.radians(10), math.radians(-35))
    scene.collection.objects.link(sun_obj)

    cam = bpy.data.cameras.new("Cam")
    cam.lens = 60
    cam_obj = bpy.data.objects.new("Cam", cam)
    scene.collection.objects.link(cam_obj)
    scene.camera = cam_obj
    os.makedirs(PREVIEW_DIR, exist_ok=True)
    target = (0.35, 0, 0.8)
    for name, position, frame in [("three-quarter", (5.2, -4.4, 3.0), 0), ("side", (0.4, -7.5, 1.2), 0),
                                  ("front", (7.5, 0, 1.6), 0), ("blink", (5.2, -4.4, 3.0), 61)]:
        cam_obj.location = position
        direction = [t - p for t, p in zip(target, position)]
        cam_obj.rotation_euler = vector_to_euler(direction)
        scene.frame_set(frame)
        scene.render.filepath = os.path.join(PREVIEW_DIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)
    # Remove the preview stage again so it isn't saved or exported
    for obj in (ground, sun_obj, cam_obj):
        bpy.data.objects.remove(obj)


def vector_to_euler(direction):
    from mathutils import Vector
    return Vector(direction).to_track_quat("-Z", "Y").to_euler()


def export():
    os.makedirs(os.path.dirname(GLB_PATH), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    bpy.ops.export_scene.gltf(
        filepath=os.path.abspath(GLB_PATH),
        export_format="GLB",
        export_apply=True,
        export_animations=True,
        export_animation_mode="SCENE",   # one "Idle" clip with every part's motion
        export_frame_range=True,
        export_force_sampling=True,
        export_optimize_animation_size=True,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
    )


if __name__ == "__main__":
    build()
    if "--preview" in sys.argv:
        preview()
    export()
    print("CAPYBARA_DONE", os.path.abspath(GLB_PATH), os.path.getsize(GLB_PATH))
