"""The leaping dolphins on Cascade's loading screens, built and animated in Blender.

Run it (no Blender window needed; ffmpeg must be on PATH, or set CASCADE_FFMPEG):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/dolphin.py

It makes:
    frontend/blender/dolphin.blend            - the dolphin at its first pose, to open in Blender
    frontend/blender/previews/dolphin_*.png   - every rendered frame, full size (not kept in git)
    frontend/public/loader/dolphin.webp       - all the frames side by side in one strip, 208 x 116 each:
                                                what the website loads (components/DolphinLoader.jsx plays it)

The dolphin: a smooth, glossy body lofted along an arched spine, counter-shaded from a deep sea-blue back to a
white belly, with a curved dorsal fin, flippers, horizontal tail flukes, a beak and a bright eye. It is seen from
a three-quarter angle (a little in front and above), so it reads as a real 3D animal, lit by a soft sky light and a
warm rim light. One swim cycle of FRAMES frames: the tail beats up and down (the whole back half of the body flexes,
most at the tail), the flukes pitch with it and the flippers paddle. The loading screen flies the strip along an
arc out of the water, so the leap itself is CSS and the dolphin never stops swimming.
Nose points +X, back up (+Z); the camera looks from -Y.
"""
import math
import os
import shutil
import subprocess

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "dolphin.blend")
FRAME_DIR = os.path.join(HERE, "previews")
STRIP_PATH = os.path.join(HERE, "..", "public", "loader", "dolphin.webp")

FRAMES = 16             # one tail beat
SIZE = (208, 116)       # each frame in the strip (twice the size it shows at, so it stays sharp)
RENDER_SCALE = 2        # render bigger and shrink, for smooth edges
LENGTH = 2.4            # nose to tail stock
RINGS = 40
AROUND = 18

COLORS = {"back": "#174f86", "side": "#3f8cc8", "belly": "#f3f9fd", "fin": "#18497a", "eye": "#0b121b",
          "shine": "#ffffff"}


def linear(hex_color):
    def channel(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return [channel(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5)] + [1]


def skin_material():
    """Counter-shading by which way the surface faces: dark back, bright sides, white belly; glossy like wet skin."""
    mat = bpy.data.materials.new("Skin")
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes["Principled BSDF"]
    shader.inputs["Roughness"].default_value = 0.28
    shader.inputs["Coat Weight"].default_value = 0.35
    shader.inputs["Coat Roughness"].default_value = 0.15
    geometry = nodes.new("ShaderNodeNewGeometry")
    split = nodes.new("ShaderNodeSeparateXYZ")
    ramp = nodes.new("ShaderNodeValToRGB")
    elements = ramp.color_ramp.elements
    elements[0].position, elements[0].color = 0.32, linear(COLORS["belly"])
    elements[1].position, elements[1].color = 0.62, linear(COLORS["back"])
    middle = elements.new(0.47)
    middle.color = linear(COLORS["side"])
    to_unit = nodes.new("ShaderNodeMapRange")       # normal z (-1 belly .. 1 back) -> 0 .. 1
    to_unit.inputs["From Min"].default_value = -1.0
    links.new(geometry.outputs["Normal"], split.inputs["Vector"])
    links.new(split.outputs["Z"], to_unit.inputs["Value"])
    links.new(to_unit.outputs["Result"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    return mat


def flat_material(name, hex_color, roughness=0.35):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = linear(hex_color)
    shader.inputs["Roughness"].default_value = roughness
    return mat


def profile(t):
    """Body radius along its length (t = 0 at the beak tip, 1 at the tail stock)."""
    if t < 0.07:
        return 0.05 + t * 0.9                                  # the beak
    if t < 0.17:
        return 0.113 + (t - 0.07) * 1.75                       # up over the melon (forehead)
    if t < 0.45:
        return 0.288 + 0.025 * math.sin((t - 0.17) / 0.28 * math.pi)
    return max(0.03, 0.29 * max(0.0, 1 - (t - 0.45) / 0.55) ** 1.4)


def bend(t, phase):
    """How far the spine is pushed up or down at t: a travelling wave that grows toward the tail (the tail beat)."""
    return 0.44 * math.sin(phase - 3.6 * t) * max(0.0, t - 0.25) ** 2.2


def spine(t, phase):
    x = LENGTH * (0.5 - t)
    z = 0.22 * math.sin(math.pi * t) - 0.05 + bend(t, phase)   # arched, plus the beat
    return Vector((x, 0, z))


def frame_at(t, phase):
    """Position and orientation (forward = toward the nose, up) of the body at t."""
    here = spine(t, phase)
    ahead = spine(max(0.0, t - 0.01), phase) - spine(min(1.0, t + 0.01), phase)
    forward = ahead.normalized()
    up = Vector((0, 0, 1))
    up = (up - forward * up.dot(forward)).normalized()
    return here, forward, up


def body(skin, phase):
    mesh = bpy.data.meshes.new("Body")
    obj = bpy.data.objects.new("Dolphin", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    rings = []
    for i in range(RINGS + 1):
        t = i / RINGS
        centre, forward, up = frame_at(t, phase)
        side = up.cross(forward).normalized()
        radius = profile(t)
        ring = []
        for k in range(AROUND):
            a = 2 * math.pi * k / AROUND
            s, c = math.sin(a), math.cos(a)
            height = radius * (1.0 if s > 0 else 0.86)      # a slightly flatter belly
            ring.append(bm.verts.new(centre + side * (c * radius * 0.84) + up * (s * height)))
        rings.append(ring)
    for i in range(RINGS):
        for k in range(AROUND):
            bm.faces.new((rings[i][k], rings[i][(k + 1) % AROUND], rings[i + 1][(k + 1) % AROUND], rings[i + 1][k]))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(skin)
    for poly in mesh.polygons:
        poly.use_smooth = True
    subdivide = obj.modifiers.new("Smooth", "SUBSURF")
    subdivide.levels = subdivide.render_levels = 1
    return obj


def fin(name, outline, thickness, mat, matrix):
    """A smooth fin from an outline in its own X/Z plane (X toward the nose), placed with `matrix`."""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    front = [bm.verts.new((x, -thickness / 2, z)) for x, z in outline]
    back = [bm.verts.new((x, thickness / 2, z)) for x, z in outline]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((front[i], front[j], back[j], back[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = True
    smooth = obj.modifiers.new("Smooth", "SUBSURF")
    smooth.levels = smooth.render_levels = 2
    obj.matrix_world = matrix
    return obj


def place(t, phase, offset=(0.0, 0.0, 0.0)):
    """A matrix at body position t, turned to match the body there (local X toward the nose, Z up, Y to the
    dolphin's left), then moved by `offset` in that local frame."""
    centre, forward, up = frame_at(t, phase)
    left = up.cross(forward).normalized()
    basis = Matrix((forward, left, up)).transposed().to_4x4()
    return Matrix.Translation(centre + forward * offset[0] + left * offset[1] + up * offset[2]) @ basis


def build(phase):
    for obj in list(bpy.data.objects):
        if obj.type == "MESH":
            bpy.data.objects.remove(obj)
    skin = bpy.data.materials.get("Skin") or skin_material()
    fin_mat = bpy.data.materials.get("Fin") or flat_material("Fin", COLORS["fin"], 0.3)
    eye_mat = bpy.data.materials.get("Eye") or flat_material("Eye", COLORS["eye"], 0.1)
    shine_mat = bpy.data.materials.get("Shine") or flat_material("Shine", COLORS["shine"], 0.05)
    body(skin, phase)
    # dorsal fin: curved and swept back, rising from the top of the back
    fin("Dorsal", [(0.18, 0.2), (0.05, 0.36), (-0.12, 0.5), (-0.24, 0.52), (-0.2, 0.42), (-0.16, 0.26), (-0.14, 0.18)],
        0.06, fin_mat, place(0.44, phase))
    # flippers on both sides, angled down and back, paddling a little with the beat
    paddle = 0.25 * math.sin(phase + 1.0)
    for side in (-1, 1):
        tilt = Matrix.Rotation(side * (0.7 + paddle), 4, "X")
        fin(f"Flipper_{side}", [(0.1, 0.0), (0.0, -0.06), (-0.18, -0.3), (-0.24, -0.27), (-0.12, -0.05)],
            0.04, fin_mat, place(0.28, phase, (0.0, side * 0.2, -0.12)) @ tilt)
    # tail flukes: a wide horizontal swallow-tail, pitching with the end of the tail
    lay_flat = Matrix.Rotation(math.pi / 2, 4, "X")   # the outline's Z becomes sideways: the flukes spread left/right
    # (it starts a little inside the tail stock, which the smoothing makes thinner, so the two stay joined)
    fin("Flukes", [(0.2, 0.0), (0.0, 0.1), (-0.16, 0.34), (-0.3, 0.42), (-0.24, 0.16), (-0.18, 0.0), (-0.24, -0.16),
                   (-0.3, -0.42), (-0.16, -0.34), (0.0, -0.1)], 0.06, fin_mat, place(0.97, phase) @ lay_flat)
    # eyes with a bright shine
    centre, forward, up = frame_at(0.15, phase)
    left = up.cross(forward).normalized()
    for side in (-1, 1):
        for name, radius, out, rise, ahead, mat in (("Eye", 0.042, 0.2, 0.03, 0.0, eye_mat),
                                                    ("Shine", 0.014, 0.235, 0.05, 0.012, shine_mat)):
            bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=radius,
                                                 location=centre + left * side * out + up * rise + forward * ahead)
            dot = bpy.context.active_object
            dot.name = f"{name}_{side}"
            dot.data.materials.append(mat)
            bpy.ops.object.shade_smooth()


def set_up_render():
    scene = bpy.context.scene
    engines = [item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items]
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in engines)
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = SIZE[0] * RENDER_SCALE, SIZE[1] * RENDER_SCALE
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.55, 0.8, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    # a soft sky light from above-front, a warm sunset rim light from behind so the edges glow, a cool fill below
    for name, energy, colour, rotation in (("Sky", 3.2, (1, 0.98, 0.95), (35, 15, 25)),
                                           ("Rim", 5.0, (1.0, 0.7, 0.45), (105, 0, -160)),
                                           ("Fill", 1.2, (0.7, 0.85, 1.0), (120, 0, 40))):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        light.data.energy = energy
        light.data.color = colour
        light.rotation_euler = [math.radians(v) for v in rotation]
        scene.collection.objects.link(light)
    # three-quarter view: a little in front of the dolphin and above it, so its round body and fins show
    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3.1
    camera.location = Vector((1.4, -7.0, 1.9))
    camera.rotation_euler = (Vector((0, 0, 0.1)) - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.collection.objects.link(camera)
    scene.camera = camera


def render_frames():
    scene = bpy.context.scene
    os.makedirs(FRAME_DIR, exist_ok=True)
    for n in range(FRAMES):
        build(2 * math.pi * n / FRAMES)
        if n == 0:
            bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
        scene.render.filepath = os.path.join(FRAME_DIR, f"dolphin_{n:02d}.png")
        bpy.ops.render.render(write_still=True)


def make_strip():
    ffmpeg = os.getenv("CASCADE_FFMPEG") or shutil.which("ffmpeg")
    os.makedirs(os.path.dirname(STRIP_PATH), exist_ok=True)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", os.path.join(FRAME_DIR, "dolphin_%02d.png"),
                    "-vf", f"scale={SIZE[0]}:{SIZE[1]}:flags=lanczos,tile={FRAMES}x1",
                    "-frames:v", "1", "-c:v", "libwebp", "-quality", "90", "-pix_fmt", "yuva420p",
                    os.path.abspath(STRIP_PATH)], check=True)


if __name__ == "__main__":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    set_up_render()
    render_frames()
    make_strip()
    print("DOLPHIN_DONE", os.path.abspath(STRIP_PATH), os.path.getsize(STRIP_PATH), FRAMES, SIZE)
