# pyright: basic, reportMissingImports=false
"""Makes Blender's corpus: one `.blend` per feature, run by Blender itself, headless.

Run as `blender -b --factory-startup --disable-autoexec --python make.py -- --pass DIRECTORY
[FEATURE...]`, every feature if none is named, and `hostile` for the hostile files only Blender can
make. Each file starts from Blender's empty factory scene, holds the smallest scene that has its
feature, made through Blender's data API, and is saved by Blender, compressed, as its GUI saves by
default. The hostile ones are saved in `hostile/`, beside the features, each holding what the scan
must refuse.
"""

import sys
from pathlib import Path

import bmesh
import bpy


def mesh(name, build, at=(0, 0, 0)):
    """An object of a mesh `build` makes, at a point, in the scene's collection."""
    made = bmesh.new()
    build(made)
    data = bpy.data.meshes.new(name)
    made.to_mesh(data)
    made.free()
    obj = bpy.data.objects.new(name, data)
    obj.location = at
    bpy.context.scene.collection.objects.link(obj)
    return obj


def cube(name="Cube", size=2.0, at=(0, 0, 0)):
    return mesh(name, lambda made: bmesh.ops.create_cube(made, size=size), at)


def primitives():
    cube(size=2)
    mesh(
        "Sphere",
        lambda m: bmesh.ops.create_uvsphere(m, u_segments=32, v_segments=16, radius=1),
        (3, 0, 0),
    )
    mesh(
        "Cylinder",
        lambda m: bmesh.ops.create_cone(
            m, cap_ends=True, segments=32, radius1=1, radius2=1, depth=2
        ),
        (0, 3, 0),
    )
    mesh(
        "Cone",
        lambda m: bmesh.ops.create_cone(
            m, cap_ends=True, segments=32, radius1=1, radius2=0, depth=2
        ),
        (3, 3, 0),
    )
    mesh(
        "Plane", lambda m: bmesh.ops.create_grid(m, x_segments=1, y_segments=1, size=2), (0, 0, -1)
    )


def transforms():
    obj = cube()
    obj.location = (1, 2, 3)
    obj.rotation_euler = (0, 0, 0.5)
    obj.scale = (2, 1, 0.5)


def materials():
    obj = cube()
    material = bpy.data.materials.new("Red")
    material.diffuse_color = (0.8, 0.1, 0.1, 1)
    material.metallic, material.roughness = 0.5, 0.25
    obj.data.materials.append(material)


def modifiers():
    obj = cube()
    obj.modifiers.new("Subdivision", "SUBSURF").levels = 2
    bevel = obj.modifiers.new("Bevel", "BEVEL")
    bevel.width, bevel.segments = 0.1, 3
    array = obj.modifiers.new("Array", "ARRAY")
    array.count = 3
    obj.modifiers.new("Mirror", "MIRROR").use_axis = (True, False, False)
    obj.modifiers.new("Solidify", "SOLIDIFY").thickness = 0.2


def camera_light():
    cube()
    camera = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    camera.location, camera.rotation_euler = (7, -7, 5), (1.1, 0, 0.785)
    camera.data.lens = 35
    bpy.context.scene.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    for kind, at in (
        ("POINT", (4, 1, 6)),
        ("SUN", (0, 0, 10)),
        ("SPOT", (-4, 0, 4)),
        ("AREA", (0, -4, 4)),
    ):
        light = bpy.data.lights.new(kind.capitalize(), kind)
        light.energy = 2 if kind == "SUN" else 500
        light.color = (1, 0.9, 0.8)
        obj = bpy.data.objects.new(light.name, light)
        obj.location = at
        bpy.context.scene.collection.objects.link(obj)


def collections():
    props = bpy.data.collections.new("Props")
    bpy.context.scene.collection.children.link(props)
    small = bpy.data.collections.new("Small")
    props.children.link(small)
    obj = cube()
    bpy.context.scene.collection.objects.unlink(obj)
    small.objects.link(obj)


def render_settings():
    cube()
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 16
    scene.render.resolution_x, scene.render.resolution_y = 640, 360


FEATURES = {
    "primitives": primitives,
    "transforms": transforms,
    "materials": materials,
    "modifiers": modifiers,
    "camera_light": camera_light,
    "collections": collections,
    "render_settings": render_settings,
}


# ─── hostile files ────────────────────────────────────────────────────────────

RUN = "__import__('os').system('touch \"$HOME/ran\"')"


def text_block():
    cube()
    text = bpy.data.texts.new("startup.py")
    text.write(f"{RUN}\n")
    text.use_module = True


def python_driver():
    driver = cube().driver_add("location", 0).driver
    driver.type, driver.expression = "SCRIPTED", RUN


def simple_driver():
    driver = cube().driver_add("location", 0).driver
    driver.type, driver.expression = "SCRIPTED", "frame * 2"


def library_link(folder):
    with bpy.data.libraries.load(str(folder / "primitives.blend"), link=True) as (_, linked):
        linked.objects = ["Cube"]
    bpy.context.scene.collection.objects.link(linked.objects[0])


def packed_image():
    image = bpy.data.images.new("Packed", 4, 4)
    image.pack()
    image.use_fake_user = True
    cube()


def external_image():
    image = bpy.data.images.new("External", 4, 4)
    image.source, image.filepath = "FILE", "/etc/passwd"
    image.use_fake_user = True
    cube()


def script_node():
    obj = cube()
    material = bpy.data.materials.new("Scripted")
    tree = material.node_tree or material.node_tree_add()
    node = tree.nodes.new("ShaderNodeScript")
    node.mode, node.filepath = "EXTERNAL", "/etc/passwd"
    obj.data.materials.append(material)


def animation():
    obj = cube()
    obj.keyframe_insert("location", frame=1)


HOSTILE = {
    "text_block": text_block,
    "python_driver": python_driver,
    "simple_driver": simple_driver,
    "library_link": library_link,
    "packed_image": packed_image,
    "external_image": external_image,
    "script_node": script_node,
    "animation": animation,
}


def make(path, build, *args):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    build(*args)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), compress=True)


def main():
    given = sys.argv[sys.argv.index("--pass") + 1 :]
    folder = Path(given[0])
    for feature in given[1:] or FEATURES:
        if feature == "hostile":
            (folder / "hostile").mkdir(exist_ok=True)
            for name, build in HOSTILE.items():
                args = (folder,) if name == "library_link" else ()
                make(folder / "hostile" / f"{name}.blend", build, *args)
        else:
            make(folder / f"{feature}.blend", FEATURES[feature])


main()
