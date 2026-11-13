"""Three 3D ideas for Cascade's logo, rendered in Blender. Ideas only: nothing here is used by the website.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/logo_concepts.py
    (add  -- a  /  -- b  /  -- c  to render just one)

It makes frontend/blender/previews/logo-a-leaf.png, logo-b-block.png and logo-c-badge.png, and logo_concepts.blend.
    A. Leaf & Falls  - the current leaf logo in 3D: a chunky leaf with a glossy stream stepping down its middle
    B. Cascade Block - a voxel cube like a piece of the Landing island: three grassy steps, water pouring into a pool
    C. Frog Badge    - a round badge with the tiered falls inside and the frog mascot (from frog.blend) by the pool
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
PREVIEWS = os.path.join(HERE, "previews")
FROG_BLEND = os.path.join(HERE, "frog.blend")

COLORS = {
    "leaf": "#3fb24a", "leafLight": "#86d94a", "stem": "#2c6b2f",
    "water": "#7fdcf0", "waterDeep": "#3fb3cc", "foam": "#ffffff",
    "grass": "#62cd36", "grassLight": "#7fdd4a", "stone": "#7b736c", "stoneDark": "#5f5852", "dirt": "#8d5f35",
    "navy": "#1d3f63", "rim": "#f3e6c4", "bush": "#2dbd4f",
}


# ---------- Helpers ----------

def linear(hex_color):
    out = []
    for i in (1, 3, 5):
        c = int(hex_color[i:i + 2], 16) / 255
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1)


MATERIALS = {}


def mat(name, roughness=0.6, emission=0.0, transmission=0.0):
    key = (name, roughness, emission, transmission)
    if key in MATERIALS:
        return MATERIALS[key]
    m = bpy.data.materials.new(f"{name}_{len(MATERIALS)}")
    m.use_nodes = True
    shader = m.node_tree.nodes["Principled BSDF"]
    shader.inputs["Base Color"].default_value = linear(COLORS[name])
    shader.inputs["Roughness"].default_value = roughness
    if emission:
        shader.inputs["Emission Color"].default_value = linear(COLORS[name])
        shader.inputs["Emission Strength"].default_value = emission
    if transmission:
        shader.inputs["Transmission Weight"].default_value = transmission
    MATERIALS[key] = m
    return m


def finish(obj, material, bevel=0.0, segments=3, smooth=False):
    if bevel:
        mod = obj.modifiers.new("Bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segments
        mod.limit_method = "ANGLE"
    obj.data.materials.append(material)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
    return obj


def box(size, location, material, bevel=0.04, rotation=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.scale = size
    bpy.ops.object.transform_apply(scale=True)
    return finish(obj, material, bevel)


def ball(radius, location, material, scale=(1, 1, 1), subdivisions=2, smooth=True):
    bpy.ops.mesh.primitive_ico_sphere_add(radius=radius, location=location, subdivisions=subdivisions)
    obj = bpy.context.active_object
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return finish(obj, material, smooth=smooth)


def disc(radius, depth, location, material, vertices=48, bevel=0.03, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, location=location, vertices=vertices)
    obj = bpy.context.active_object
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    return finish(obj, material, bevel, smooth=True)


def tube(points, radius, material):
    """A round tube along a path of points (a curve with a bevel)."""
    data = bpy.data.curves.new("Tube", "CURVE")
    data.dimensions = "3D"
    data.bevel_depth = radius
    data.bevel_resolution = 6
    spline = data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for p, co in zip(spline.points, points):
        p.co = (*co, 1)
    data.use_fill_caps = True
    obj = bpy.data.objects.new("Tube", data)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def prism(outline, depth, z, material, bevel=0.06):
    """Extrude a flat outline (list of (x, y)) up by depth, starting at height z."""
    bm = bmesh.new()
    verts = [bm.verts.new((x, y, z)) for x, y in outline]
    face = bm.faces.new(verts)
    bmesh.ops.recalc_face_normals(bm, faces=[face])
    if face.normal.z < 0:
        face.normal_flip()
    result = bmesh.ops.extrude_face_region(bm, geom=[face])
    top = [e for e in result["geom"] if isinstance(e, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=top, vec=(0, 0, depth))
    mesh = bpy.data.meshes.new("Prism")
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new("Prism", mesh)
    bpy.context.scene.collection.objects.link(obj)
    return finish(obj, material, bevel, segments=4)


def cubic(p0, p1, p2, p3, steps=24):
    out = []
    for i in range(steps):
        t = i / steps
        a = (1 - t) ** 3
        b = 3 * (1 - t) ** 2 * t
        c = 3 * (1 - t) * t * t
        d = t ** 3
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return out


def svg(x, y, scale=0.1):
    """The 2D logo's 64x64 grid (y down) -> Blender (x right, y up), centered."""
    return ((x - 32) * scale, (32 - y) * scale)


# ---------- Stage: lights, camera, background ----------

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    MATERIALS.clear()
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = scene.render.resolution_y = 900
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"   # true, bright colors like the website
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.72, 0.86, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
    sun = bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", "SUN"))
    sun.data.energy = 3.2
    sun.data.angle = math.radians(8)
    sun.rotation_euler = (math.radians(40), math.radians(-20), math.radians(35))
    scene.collection.objects.link(sun)
    fill = bpy.data.objects.new("Fill", bpy.data.lights.new("Fill", "AREA"))
    fill.data.energy = 300
    fill.data.size = 6
    fill.location = (-4, -5, 4)
    fill.rotation_euler = (math.radians(55), 0, math.radians(-40))
    scene.collection.objects.link(fill)


def camera(position, target, ortho=None, lens=70):
    cam = bpy.data.objects.new("Cam", bpy.data.cameras.new("Cam"))
    if ortho:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = ortho
    else:
        cam.data.lens = lens
    cam.location = position
    cam.rotation_euler = (Vector(target) - Vector(position)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(cam)
    bpy.context.scene.camera = cam


def render(name):
    os.makedirs(PREVIEWS, exist_ok=True)
    path = os.path.join(PREVIEWS, name)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("RENDERED", path)


# ---------- Shared: the three-step waterfall (used by B and C) ----------

def tiered_falls(origin=(0, 0, 0), s=1.0, with_pool=True):
    """Three grassy stone steps going down toward the viewer (-y), with water pouring over each one."""
    ox, oy, oz = origin
    steps = [  # (depth along y, top height)
        (0.7, 1.9),
        (0.7, 1.3),
        (0.7, 0.7),
    ]
    width = 2.0 * s
    y = 0.9 * s
    water = mat("water", roughness=0.08, emission=0.25)
    for i, (depth, top) in enumerate(steps):
        d, t = depth * s, top * s
        cy = y - d / 2
        box((width, d, t - 0.12 * s), (ox, oy + cy, oz + (t - 0.12 * s) / 2), mat("stone" if i % 2 == 0 else "stoneDark"), 0.05 * s)
        box((width + 0.02, d + 0.02, 0.16 * s), (ox, oy + cy, oz + t - 0.08 * s), mat("grass"), 0.05 * s)
        # water runs along the top of this step...
        box((0.7 * s, d + 0.02, 0.06 * s), (ox, oy + cy, oz + t + 0.02 * s), water, 0.02 * s)
        # ...and pours down its front face onto the next step (or the pool)
        below = steps[i + 1][1] * s if i + 1 < len(steps) else 0.05 * s
        box((0.7 * s, 0.07 * s, t - below + 0.04 * s), (ox, oy + y - d - 0.03 * s, oz + (t + below) / 2), water, 0.02 * s)
        for k in range(3):
            ball(0.09 * s, (ox - 0.25 * s + k * 0.25 * s, oy + y - d - 0.1 * s, oz + below + 0.06 * s), mat("foam", 0.4), (1.3, 1, 0.7))
        y -= d
    if with_pool:
        disc(1.15 * s, 0.1 * s, (ox, oy + y - 0.62 * s, oz + 0.1 * s), mat("waterDeep", 0.1, 0.15), scale=(1, 0.62, 1))
    # bushes on the top step
    for bx, by, r in [(-0.75, 0.6, 0.32), (0.78, 0.65, 0.28), (-0.85, 0.2, 0.22)]:
        ball(r * s, (ox + bx * s, oy + by * s, oz + 1.95 * s + r * s * 0.6), mat("bush", 0.7), subdivisions=1, smooth=False)


# ---------- A. Leaf & Falls ----------

def concept_leaf():
    reset()
    outline = [svg(*p) for p in cubic((13, 53), (5, 35), (15, 12), (54, 7)) + cubic((54, 7), (57, 34), (42, 52), (13, 53))]
    prism(outline, 0.35, 0, mat("leaf", 0.45), bevel=0.12)
    # the lighter half: the side of the leaf past the falls, a step higher
    light = [svg(*p) for p in [(47, 14), (39, 14), (39, 24), (29, 24), (29, 34), (19, 34), (19, 46), (14, 51)]]
    edge = [svg(*p) for p in cubic((54, 7), (57, 34), (42, 52), (13, 53))]
    prism(light[::-1] + edge[:-2], 0.12, 0.34, mat("leafLight", 0.45), bevel=0.04)
    # the stream: runs along each ledge, then drops
    path = [(47, 14), (40, 14), (39, 15), (39, 24), (30, 24), (29, 25), (29, 34), (20, 34), (19, 35), (19, 46), (14, 51)]
    tube([(*svg(x, y), 0.5) for x, y in path], 0.17, mat("water", 0.05, 0.4))
    # the stem
    tube([(*svg(14, 52), 0.17), (*svg(5, 61), 0.1)], 0.13, mat("stem", 0.6))
    # a few drops splashing off the bottom
    for x, y, r in [(9, 50, 0.1), (17, 57, 0.08), (11, 56, 0.06)]:
        ball(r, (*svg(x, y), 0.55), mat("water", 0.05, 0.4))
    obj = bpy.data.objects
    for o in obj:
        if o.type in {"MESH", "CURVE"}:
            o.rotation_euler = (math.radians(14), math.radians(-10), 0)
    camera((0.6, -11.5, 7.5), (0.2, 0.1, 0.2), lens=60)
    render("logo-a-leaf.png")


# ---------- B. Cascade Block ----------

def concept_block():
    reset()
    tiered_falls()
    # a soil base under it all, like a block lifted out of the island
    box((2.8, 4.4, 0.5), (0, -0.75, -0.25), mat("dirt", 0.8), 0.08)
    box((2.82, 4.42, 0.12), (0, -0.75, 0.02), mat("grassLight", 0.7), 0.05)
    camera((7.5, -7.5, 6.6), (0, -0.6, 0.7), ortho=6.0)
    render("logo-b-block.png")


# ---------- C. Frog Badge ----------

def append_frog(location, scale, turn):
    if not os.path.exists(FROG_BLEND):
        return
    with bpy.data.libraries.load(FROG_BLEND) as (source, target):
        target.objects = list(source.objects)
    holder = bpy.data.objects.new("FrogHolder", None)
    bpy.context.scene.collection.objects.link(holder)
    for obj in target.objects:
        if obj is None:
            continue
        bpy.context.scene.collection.objects.link(obj)
        obj.animation_data_clear()
        if obj.parent is None:
            obj.parent = holder
    holder.location = location
    holder.scale = (scale, scale, scale)
    holder.rotation_euler = (0, 0, turn)


def concept_badge():
    reset()
    # the badge: a cream rim around a navy disc, standing up
    rim = disc(2.55, 0.35, (0, 0.45, 0), mat("rim", 0.5), vertices=64, bevel=0.1)
    face = disc(2.25, 0.4, (0, 0.45, 0.02), mat("navy", 0.6), vertices=64, bevel=0.06)
    for obj in (rim, face):
        obj.rotation_euler = (math.radians(90), 0, 0)
    # inside it: the falls, and the frog sitting at the pool
    tiered_falls(origin=(0, -1.25, -1.75), s=1.1, with_pool=True)   # in front of the badge's face
    append_frog(location=(1.2, -3.15, -1.62), scale=0.55, turn=math.radians(-35))
    for x, z, r in [(-1.55, 1.25, 0.09), (1.35, 1.45, 0.07), (-0.6, 1.85, 0.06), (1.85, 0.55, 0.06), (0.55, 1.95, 0.05)]:
        ball(r, (x, 0.1, z), mat("foam", 0.3, 3.0), subdivisions=1)   # little stars in the night-blue sky
    camera((3.2, -12.5, 5.0), (0.15, -1.0, -0.2), lens=70)
    render("logo-c-badge.png")


if __name__ == "__main__":
    picks = [arg for arg in sys.argv[sys.argv.index("--") + 1:]] if "--" in sys.argv else ["a", "b", "c"]
    if "a" in picks:
        concept_leaf()
    if "b" in picks:
        concept_block()
    if "c" in picks:
        concept_badge()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "logo_concepts.blend"))
    print("LOGO_CONCEPTS_DONE")
