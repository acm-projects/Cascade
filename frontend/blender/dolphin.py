"""The leaping dolphin for Cascade's loading screen, built in Blender.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/dolphin.py

It makes:
    frontend/blender/dolphin.blend               - open this in Blender to look at or edit the dolphin
    frontend/blender/previews/dolphin.png        - the full-size render (not kept in git)
    frontend/public/loader/dolphin.webp          - the same, 320 px wide (about 5 KB): what the website loads
                                                   (needs ffmpeg on PATH, or set CASCADE_FFMPEG)
The loading screen (components/DolphinLoader.jsx) flies that picture along an arc over the water, so no 3D
code has to download just to show that something is loading.

The look matches the island and Cassie: chunky low-poly, flat shaded, a deep sea-blue back fading to a pale
belly, with a warm sunset rim light from behind so it pops against the evening sea.
The dolphin is built nose to +X, back up (+Z), and the camera looks from -Y at its profile.
"""
import math
import os
import shutil
import subprocess

import bpy
import bmesh
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
BLEND_PATH = os.path.join(HERE, "dolphin.blend")
PNG_PATH = os.path.join(HERE, "previews", "dolphin.png")
WEBP_PATH = os.path.join(HERE, "..", "public", "loader", "dolphin.webp")

COLORS = {"back": "#2f6fa8", "side": "#5a9bd0", "belly": "#e8f3fb", "fin": "#2a5f93", "eye": "#0f1a26", "shine": "#ffffff"}
LENGTH = 2.4          # nose to tail
RINGS = 18            # rings along the body (few, for the chunky low-poly look)
AROUND = 10           # sides around the body


def srgb_to_linear(channel):
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def material(name, hex_color, roughness=0.55):
    color = [srgb_to_linear(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5)]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = (*color, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Specular IOR Level"].default_value = 0.6
    return mat


def profile(t):
    """Body thickness along its length (t = 0 at the nose, 1 at the tail): a short beak, a round melon
    (forehead), the thickest part just behind the head, then a long taper to the tail stock."""
    if t < 0.08:
        return 0.06 + t * 0.9                       # the beak
    if t < 0.16:
        return 0.13 + (t - 0.08) * 1.9              # up into the melon
    if t < 0.42:
        return 0.28 + 0.04 * math.sin((t - 0.16) / 0.26 * math.pi)
    return max(0.035, 0.29 * max(0.0, 1 - (t - 0.42) / 0.58) ** 1.35)


def spine(t):
    """The centre line: arched like a dolphin mid-leap (nose and tail lower than the back)."""
    x = LENGTH * (0.5 - t)
    z = 0.32 * math.sin(math.pi * t) - 0.05
    return Vector((x, 0, z))


def body(mats):
    mesh = bpy.data.meshes.new("Body")
    obj = bpy.data.objects.new("Dolphin", mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    rings = []
    for i in range(RINGS + 1):
        t = i / RINGS
        centre = spine(t)
        ahead = spine(min(1, t + 0.01)) - spine(max(0, t - 0.01))
        tilt = math.atan2(ahead.z, -ahead.x) if ahead.length else 0
        radius = profile(t)
        ring = []
        for k in range(AROUND):
            a = 2 * math.pi * k / AROUND
            y = math.cos(a) * radius * 0.82                 # a little narrower than tall
            up = math.sin(a) * radius * (1.0 if math.sin(a) > 0 else 0.85)
            ring.append(bm.verts.new(centre + Vector((-math.sin(tilt) * up, y, math.cos(tilt) * up))))
        rings.append(ring)
    for i in range(RINGS):
        for k in range(AROUND):
            a, b = rings[i][k], rings[i][(k + 1) % AROUND]
            c, d = rings[i + 1][(k + 1) % AROUND], rings[i + 1][k]
            bm.faces.new((a, b, c, d))
    bm.faces.new(list(reversed(rings[0])))
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)   # all faces outward, so "facing up" really is the back
    # colour by which way each face looks: dark back, mid sides, pale belly
    for name in ("back", "side", "belly"):
        mesh.materials.append(mats[name])
    for face in bm.faces:
        n = face.normal
        face.material_index = 0 if n.z > 0.35 else (2 if n.z < -0.25 else 1)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = False
    return obj


def fin(name, points, thickness, mat, parent):
    """A flat low-poly fin from an outline in the X/Z plane, given a little thickness."""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    front = [bm.verts.new((x, -thickness / 2, z)) for x, z in points]
    back = [bm.verts.new((x, thickness / 2, z)) for x, z in points]
    bm.faces.new(front)
    bm.faces.new(list(reversed(back)))
    for i in range(len(points)):
        j = (i + 1) % len(points)
        bm.faces.new((front[i], front[j], back[j], back[i]))
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mat)
    obj.parent = parent
    return obj


def build():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mats = {name: material(name, hex_color) for name, hex_color in COLORS.items()}
    dolphin = body(mats)
    top = spine(0.42)
    # dorsal fin: swept back, on the highest part of the back
    fin("Dorsal", [(top.x + 0.2, top.z + 0.2), (top.x - 0.12, top.z + 0.5), (top.x - 0.26, top.z + 0.46),
                   (top.x - 0.16, top.z + 0.2)], 0.05, mats["fin"], dolphin)
    # tail flukes: a wide swallow-tail at the end of the tail stock, seen edge-on as a flat crescent
    end = spine(1.0)
    flukes = fin("Flukes", [(end.x + 0.08, end.z + 0.02), (end.x - 0.3, end.z + 0.26), (end.x - 0.2, end.z + 0.02),
                            (end.x - 0.3, end.z - 0.24)], 0.06, mats["fin"], dolphin)
    flukes.scale.y = 5   # wide side to side
    # pectoral fin: on the camera's side, angled down and back under the chest
    chest = spine(0.3)
    pec = fin("Pectoral", [(chest.x + 0.1, chest.z - 0.12), (chest.x - 0.08, chest.z - 0.42), (chest.x - 0.18, chest.z - 0.36),
                           (chest.x - 0.06, chest.z - 0.1)], 0.04, mats["fin"], dolphin)
    pec.location.y = -0.2
    # eye with a shine, and a smiling mouth line
    head = spine(0.13)
    for name, size, offset, mat in (("Eye", 0.045, (0.0, -0.22, 0.02), mats["eye"]),
                                    ("Shine", 0.016, (0.015, -0.255, 0.04), mats["shine"])):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=5, radius=size, location=head + Vector(offset))
        dot = bpy.context.active_object
        dot.name = name
        dot.data.materials.append(mat)
        dot.parent = dolphin
    return dolphin


def render():
    scene = bpy.context.scene
    engines = [item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items]
    scene.render.engine = next(e for e in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES") if e in engines)
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = 640, 360
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Standard"
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.25, 0.45, 0.7, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.7
    # soft sky light from above, and a warm sunset rim light from behind-left
    for name, energy, colour, rotation in (("Sky", 3.0, (1, 0.98, 0.95), (40, 10, 20)),
                                           ("Sunset", 6.0, (1.0, 0.62, 0.35), (100, 0, -150))):
        light = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
        light.data.energy = energy
        light.data.color = colour
        light.rotation_euler = [math.radians(v) for v in rotation]
        scene.collection.objects.link(light)
    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = 3.0
    camera.location = (0, -8, 0.15)
    camera.rotation_euler = (math.radians(90), 0, 0)
    scene.collection.objects.link(camera)
    scene.camera = camera
    os.makedirs(os.path.dirname(PNG_PATH), exist_ok=True)
    scene.render.filepath = os.path.abspath(PNG_PATH)
    bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    build()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    render()
    ffmpeg = os.getenv("CASCADE_FFMPEG") or shutil.which("ffmpeg")
    os.makedirs(os.path.dirname(WEBP_PATH), exist_ok=True)
    subprocess.run([ffmpeg, "-v", "error", "-y", "-i", PNG_PATH, "-vf", "scale=320:-1", "-c:v", "libwebp",
                    "-quality", "88", "-pix_fmt", "yuva420p", os.path.abspath(WEBP_PATH)], check=True)
    print("DOLPHIN_DONE", os.path.abspath(WEBP_PATH), os.path.getsize(WEBP_PATH))
