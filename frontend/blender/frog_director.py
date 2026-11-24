"""Cassie as a frog, built in Blender: the cute original frog (frog.py, the one from "How it works") with a tiny
director's kit. She sits in the corner of the Projects page and is the face of the AI Studio chat
(components/Cassie.jsx -> Mascot.jsx -> features/landing3d/mascotScene.js).

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/frog_director.py
    (add  -- --preview  to also render preview pictures into frontend/blender/previews/)

It makes:
    frontend/blender/frog_director.blend      - open this in Blender to look at or edit her
    frontend/public/models/frog_director.glb  - the file the website loads

She IS the original frog: frog.py builds her body, round eyes, cheeks, belly and legs, and her "Idle" and "Leap"
clips, so she looks exactly like the frog Sai called cute. This file only adds her kit, one of two (pick with  -- --kit camera ; the default is the director kit):
    director: at her front feet, a little clapperboard (black with white stripes) that snaps shut once per idle
              loop, and a little orange megaphone
    camera:   a little black camera with a blue lens and a blinking red light, on a tall thin tripod beside her
Both are small and rounded, so they read as cute toys, not as big blocks. They're attached to her front legs,
so they hop with her.
"""
import importlib.util
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("frog", os.path.join(HERE, "frog.py"))
frog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frog)

# Cassie's greens: softer and lighter than the pond frog's, matching the frog render Sai picked as the reference
frog.COLORS.update({
    "skin": "#86bf6f",
    "skin_dark": "#6aa85a",
    "spots": "#5f9a52",
    "toes": "#9dd088",
    "belly": "#e2e3c6",
    "mouth": "#3b5a36",
    "cheek": "#eaa1a4",
})
SMOOTH_ANGLE = math.radians(42)   # edges flatter than this are shaded smooth, so she looks soft, not blocky

# Which kit she has: "director" (clapperboard + megaphone) or "camera" (a camera on a tripod beside her).
# Pick with  -- --kit camera  on the command line; each kit has its own files, so both stay ready:
#   director -> frog_director.blend / public/models/frog_director.glb
#   camera   -> frog_camera.blend   / public/models/frog_camera.glb
# The website picks one in features/landing3d/mascotScene.js (CASSIE_KIT).
CHOSEN_KIT = sys.argv[sys.argv.index("--kit") + 1] if "--kit" in sys.argv else "director"
NAME = {"director": "frog_director", "camera": "frog_camera"}[CHOSEN_KIT]
BLEND_PATH = os.path.join(HERE, f"{NAME}.blend")
GLB_PATH = os.path.join(HERE, "..", "public", "models", f"{NAME}.glb")
PREVIEW_DIR = os.path.join(HERE, "previews")

KIT = {
    "board": "#2a2c31",
    "stripe": "#f6f4ee",
    "megaphone": "#f39a3a",
    "megaphone_rim": "#d8772a",
    # the camera kit
    "camera": "#25272c",
    "camera_top": "#3a3d44",
    "lens_ring": "#4f8fd8",
    "lens_glass": "#0f1a2a",
    "lens_shine": "#ffffff",
    "record": "#e8423a",
    "tripod": "#2b2d33",
}


def cone(name, radius_big, radius_small, depth, location, rotation, material, parent):
    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=radius_big, radius2=radius_small, depth=depth,
                                    location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width = 0.012
    mod.segments = 2
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material)
    frog.keep_world_parent(obj, parent)
    return obj


def add_kit(parts):
    m = {key: frog.make_material(key, value, roughness=0.6) for key, value in KIT.items()}
    # front_legs[0] is her +X side (your right as she faces you), front_legs[1] the -X side (your left)
    right_hand, left_hand = parts["front_legs"]

    # --- the clapperboard, standing at her left foot and leaning on her a little ---
    board_at = (-0.43, -0.44, 0.12)
    tilt = (0, math.radians(8), 0)
    frog.block("ClapBoard", (0.24, 0.04, 0.17), board_at, m["board"], left_hand, bevel=0.025, rotation=tilt)
    for i in range(2):
        frog.block(f"ClapLine_{i}", (0.18, 0.045, 0.014), (board_at[0], board_at[1] - 0.002, board_at[2] - 0.035 + i * 0.045),
                   m["stripe"], left_hand, bevel=0.005, rotation=tilt)
    stick = frog.pivot("ClapStick", (board_at[0] - 0.11, board_at[1], board_at[2] + 0.095), left_hand)   # hinge, left end
    for i in range(4):
        frog.block(f"ClapStripe_{i}", (0.06, 0.042, 0.05), (board_at[0] - 0.09 + i * 0.06, board_at[1], board_at[2] + 0.12),
                   m["stripe"] if i % 2 == 0 else m["board"], stick, bevel=0.008)
    parts["clap_stick"] = stick

    # --- the megaphone, at her right foot, pointing out and a little up ---
    turn = (0, math.radians(75), math.radians(-20))
    cone("Megaphone", 0.035, 0.085, 0.22, (0.46, -0.46, 0.12), turn, m["megaphone"], right_hand)
    cone("MegaphoneRim", 0.088, 0.088, 0.02, (0.565, -0.5, 0.15), turn, m["megaphone_rim"], right_hand)
    return parts


def rod(name, start, end, radius, material, parent):
    """A thin rounded rod from one point to another (tripod legs)."""
    from mathutils import Vector
    a, b = Vector(start), Vector(end)
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=radius, depth=(b - a).length, location=(a + b) / 2)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (b - a).to_track_quat("Z", "Y")
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
    obj.rotation_mode = "XYZ"
    bpy.ops.object.shade_smooth()
    obj.data.materials.append(material)
    frog.keep_world_parent(obj, parent)
    return obj


def add_camera_kit(parts):
    """A little black camera with a blue lens and a red light, on a tall thin tripod standing at her right side."""
    m = {key: frog.make_material(key, value, roughness=0.55) for key, value in KIT.items()}
    m["lens_glass"].node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.15
    root = parts["root"]
    rig = frog.pivot("CameraRig", (0.78, -0.05, 0), root)
    top = (0.78, -0.05, 0.74)
    for i, angle in enumerate((90, 210, 330)):   # three legs, spread out on the ground
        foot = (top[0] + math.cos(math.radians(angle)) * 0.2, top[1] + math.sin(math.radians(angle)) * 0.2, 0.0)
        rod(f"TripodLeg_{i}", top, foot, 0.014, m["tripod"], rig)
    rod("TripodPost", top, (top[0], top[1], top[2] + 0.08), 0.02, m["tripod"], rig)
    # the camera body, facing you (-Y), sitting on top of the tripod
    body_at = (top[0], top[1], top[2] + 0.18)
    frog.block("CameraBody", (0.3, 0.2, 0.2), body_at, m["camera"], rig, bevel=0.035)
    frog.block("CameraTop", (0.12, 0.12, 0.06), (body_at[0] - 0.06, body_at[1] + 0.02, body_at[2] + 0.12),
               m["camera_top"], rig, bevel=0.015)
    lens = (body_at[0] - 0.02, body_at[1] - 0.12, body_at[2] - 0.005)
    bpy.ops.mesh.primitive_cylinder_add(vertices=20, radius=0.075, depth=0.06, location=lens, rotation=(math.radians(90), 0, 0))
    ring = bpy.context.active_object
    ring.name = "LensRing"
    bpy.ops.object.shade_smooth()
    ring.data.materials.append(m["lens_ring"])
    frog.keep_world_parent(ring, rig)
    frog.dome("LensGlass", 0.052, (lens[0], lens[1] - 0.03, lens[2]), m["lens_glass"], rig, squash=0.6)
    frog.dome("LensShine", 0.014, (lens[0] - 0.02, lens[1] - 0.06, lens[2] + 0.02), m["lens_shine"], rig)
    light = frog.pivot("RecordLight", (body_at[0] + 0.1, body_at[1] - 0.105, body_at[2] + 0.06), rig)
    frog.dome("RecordDot", 0.022, (body_at[0] + 0.1, body_at[1] - 0.105, body_at[2] + 0.06), m["record"], light)
    parts["record_light"] = light
    return parts


def animate_record(parts):
    """Added to the "Idle" clip: the camera's red light blinks, like it's recording."""
    light = parts["record_light"]
    for frame, size in [(0, 1), (28, 1), (30, 0.2), (58, 0.2), (60, 1), (88, 1), (90, 0.2), (118, 0.2), (frog.IDLE, 1)]:
        frog.key(light, "scale", frame, (size, size, size))
    frog.store_clip([light], "Idle")


def smooth_shading():
    """Shade every part smoothly across its rounded edges (keeping only the sharpest corners crisp)."""
    bpy.ops.object.select_all(action="DESELECT")
    meshes = [obj for obj in bpy.data.objects if obj.type == "MESH"]
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.shade_smooth_by_angle(angle=SMOOTH_ANGLE)
    bpy.ops.object.select_all(action="DESELECT")


def animate_clap(parts):
    """Added to the "Idle" clip: the clapper stick is up, snaps shut at about 2 seconds, then lifts again."""
    stick = parts["clap_stick"]
    for frame, angle in [(0, 0.5), (52, 0.5), (58, 0.62), (62, 0.0), (74, 0.0), (92, 0.5), (frog.IDLE, 0.5)]:
        frog.key(stick, "rotation_euler", frame, (0, -angle, 0))
    frog.store_clip([stick], "Idle")


def preview():
    scene = bpy.context.scene
    engines = [item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items]
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in engines)
    scene.render.resolution_x, scene.render.resolution_y = 480, 400
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.62, 0.72, 0.74, 1)
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.5
    sun.rotation_euler = (math.radians(50), math.radians(-15), math.radians(25))
    scene.collection.objects.link(sun)
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    cam.data.lens = 55
    scene.collection.objects.link(cam)
    scene.camera = cam
    from mathutils import Vector
    for name, position, frame in [(f"{NAME.replace('_', '-')}-front", (0.3, -4.6, 1.6), 0),
                                  (f"{NAME.replace('_', '-')}-angle", (2.4, -3.8, 1.7), 0)]:
        target = Vector((0, 0, 0.4))
        cam.location = position
        cam.rotation_euler = (target - Vector(position)).to_track_quat("-Z", "Y").to_euler()
        scene.frame_set(frame)
        os.makedirs(PREVIEW_DIR, exist_ok=True)
        scene.render.filepath = os.path.join(PREVIEW_DIR, f"{name}.png")
        bpy.ops.render.render(write_still=True)
    for obj in (sun, cam):
        bpy.data.objects.remove(obj)


if __name__ == "__main__":
    if CHOSEN_KIT == "camera":
        parts = add_camera_kit(frog.build())
    else:
        parts = add_kit(frog.build())
    smooth_shading()
    frog.animate_idle(parts)
    if CHOSEN_KIT == "camera":
        animate_record(parts)
        frog.reset(parts)
        parts["record_light"].scale = (1, 1, 1)
    else:
        animate_clap(parts)
        frog.reset(parts)
        parts["clap_stick"].rotation_euler = (0, 0, 0)
    frog.animate_leap(parts)
    frog.reset(parts)
    if "--preview" in sys.argv:
        preview()
    frog.BLEND_PATH = BLEND_PATH   # frog.export() saves and exports to these
    frog.GLB_PATH = GLB_PATH
    frog.export()
    print("FROG_DIRECTOR_DONE", os.path.abspath(GLB_PATH), os.path.getsize(GLB_PATH))
