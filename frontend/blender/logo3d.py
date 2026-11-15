"""Cascade's logo in 3D, made in Blender: the same leaf as src/assets/icons/cascade-logo.svg, built up into
a chunky little model.

Run it (no Blender window needed):
    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python frontend/blender/logo3d.py

It makes frontend/blender/previews/logo-3d.png (a large preview on a see-through background) and logo3d.blend.

What's in it, following the flat logo:
    - a navy rim around the whole leaf, as tall as it: the logo's dark outline
    - the leaf itself, in the logo's green
    - the right side of the leaf rises in three terraces (light, mid, deeper green), like the tiered falls
    - the water: a glossy light-blue stream that runs along each ledge and drops to the next one, with a
      navy "outline" tube under it like the flat logo's stroke
    - the navy stem
"""
import math
import os
import sys

import bmesh
import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logo_concepts as lc  # noqa: E402  (shared helpers: materials, shapes, lights, camera)

# The flat logo's colors
lc.COLORS.update({
    "logoLeaf": "#3aa847",
    "tierTop": "#8fe05a",
    "tierMid": "#6fd04f",
    "tierLow": "#55c04a",
    "logoNavy": "#12324f",
    "logoWater": "#6fd6f2",
    "logoWaterLight": "#c8f1ff",
    "logoFoam": "#ffffff",
})

LEAF = lc.cubic((13, 53), (5, 35), (15, 12), (54, 7), 40) + lc.cubic((54, 7), (57, 34), (42, 52), (13, 53), 40)

BASE_Z = 0.0       # the navy outline plate
LEAF_Z = 0.22      # the leaf sits on it
LEAF_DEPTH = 0.32
TIERS = [          # (outline in the flat logo's grid, height above the leaf, color)
    ([(54, 4), (47, 14), (39, 14), (39, 64), (64, 64), (64, 4)], 0.42, "tierTop"),
    ([(39, 24), (29, 24), (29, 64), (39, 64)], 0.28, "tierMid"),
    ([(29, 34), (19, 34), (19, 64), (29, 64)], 0.14, "tierLow"),
]


def flat(outline):
    return [lc.svg(x, y) for x, y in outline]


def grow(outline, amount):
    """The same flat outline pushed outward by `amount` all round (each corner moves out along the
    average of its two sides' outward directions)."""
    area = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(outline, outline[1:] + outline[:1]))
    turn = 1 if area > 0 else -1   # which way round the points go decides which side is "out"
    out = []
    n = len(outline)
    for i, (x, y) in enumerate(outline):
        px, py = outline[i - 1]
        nx, ny = outline[(i + 1) % n]
        normals = []
        for (ax, ay), (bx, by) in (((px, py), (x, y)), ((x, y), (nx, ny))):
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1
            normals.append((turn * dy / length, -turn * dx / length))
        mx, my = normals[0][0] + normals[1][0], normals[0][1] + normals[1][1]
        length = math.hypot(mx, my) or 1
        mx, my = mx / length, my / length
        # keep sharp corners (the leaf's tip) from shooting out too far
        cos = max(0.5, mx * normals[0][0] + my * normals[0][1])
        out.append((x + mx * amount / cos, y + my * amount / cos))
    return out


def outlined_plate(outline, outset, depth, z, material):
    """The leaf's shape, grown outward by `outset` all round: the navy outline around the leaf."""
    return lc.prism(grow(outline, outset), depth, z, material, bevel=0.08)


def clip_to_leaf(obj, leaf_cutter):
    """Keep only the part of obj inside the leaf's outline."""
    mod = obj.modifiers.new("Clip", "BOOLEAN")
    mod.operation = "INTERSECT"
    mod.object = leaf_cutter
    mod.solver = "EXACT"
    bpy.context.view_layer.objects.active = obj
    # the bevel was added first; apply the clip before it so the cut edges get rounded too
    bpy.ops.object.modifier_move_to_index(modifier="Clip", index=0)
    bpy.ops.object.modifier_apply(modifier="Clip")


def build():
    lc.reset()
    scene = bpy.context.scene
    scene.render.film_transparent = True
    scene.render.resolution_x = scene.render.resolution_y = 1024

    navy = lc.mat("logoNavy", 0.55)
    leaf_outline = flat(LEAF)

    # 1. the navy outline plate, a bit bigger than the leaf
    rim = outlined_plate(leaf_outline, 0.17, LEAF_Z + LEAF_DEPTH, BASE_Z, navy)   # as tall as the leaf, so it rims it all round
    hole = lc.prism(leaf_outline, 3, LEAF_Z - 0.02, navy, bevel=0)   # ...with the leaf's shape cut out of its middle
    cut = rim.modifiers.new("Hole", "BOOLEAN")
    cut.operation = "DIFFERENCE"
    cut.object = hole
    cut.solver = "EXACT"
    bpy.context.view_layer.objects.active = rim
    bpy.ops.object.modifier_move_to_index(modifier="Hole", index=0)
    bpy.ops.object.modifier_apply(modifier="Hole")
    bpy.data.objects.remove(hole)

    # 2. the leaf
    lc.prism(leaf_outline, LEAF_DEPTH, LEAF_Z, lc.mat("logoLeaf", 0.5), bevel=0.07)

    # 3. the three terraces on the right, each cut to the leaf's outline
    cutter = lc.prism(leaf_outline, 3, -1, lc.mat("logoLeaf"), bevel=0)
    cutter.hide_render = True
    cutter.hide_set(True)
    for outline, rise, color in TIERS:
        tier = lc.prism(flat(outline), rise, LEAF_Z + LEAF_DEPTH - 0.02, lc.mat(color, 0.5), bevel=0.05)
        clip_to_leaf(tier, cutter)
    bpy.data.objects.remove(cutter)

    # 4. the water: along each ledge, then down to the next. Its height follows the terraces it runs on.
    top = LEAF_Z + LEAF_DEPTH
    levels = {"top": top + 0.42, "mid": top + 0.28, "low": top + 0.14, "leaf": top}
    path = [
        ((47, 14), "top"), ((40.5, 14), "top"),
        ((39, 15.5), "top"), ((39, 23), "mid"),
        ((37.5, 24), "mid"), ((30.5, 24), "mid"),
        ((29, 25.5), "mid"), ((29, 33), "low"),
        ((27.5, 34), "low"), ((20.5, 34), "low"),
        ((19, 35.5), "low"), ((19, 45), "leaf"), ((14, 51), "leaf"),
    ]
    points = [(*lc.svg(x, y), levels[level] + 0.1) for (x, y), level in path]
    lc.tube([(x, y, z - 0.08) for x, y, z in points], 0.3, navy)                        # the dark outline
    water = lc.mat("logoWater", 0.05, emission=0.15)
    lc.tube([(x, y, z + 0.1) for x, y, z in points], 0.24, water)                       # the stream
    shine = lc.mat("logoWaterLight", 0.1, emission=0.6)
    lc.tube([(x - 0.04, y + 0.04, z + 0.3) for x, y, z in points], 0.06, shine)         # light along its top

    # 5. the stem
    lc.tube([(*lc.svg(14, 52), BASE_Z + 0.2), (*lc.svg(8.5, 57.5), BASE_Z + 0.14)], 0.26, navy)

    # Tilt the whole logo back a little so its thickness shows, and look at it from slightly above-right
    for obj in bpy.data.objects:
        if obj.type in {"MESH", "CURVE"}:
            obj.rotation_euler = (math.radians(20), math.radians(-8), 0)
    lc.camera((1.0, -12.0, 5.0), (0.05, 0.1, 0.25), lens=62)
    lc.render("logo-3d.png")


if __name__ == "__main__":
    build()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "logo3d.blend"))
    print("LOGO3D_DONE")
