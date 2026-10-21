# pyright: basic, reportMissingImports=false
"""The script Blender runs for each call: the call's JSON in, its result's JSON out.

It runs in Blender's own interpreter, by path, as `blender --background ... --python script.py --
--pass call.json`, so it imports Blender's modules and the standard library alone, nothing of
lattice's. The call names its step, `apply`, `inspect` or `render`; the source, if there is one, is
`in/document.blend`, as the scan wrote it, and what it saves or draws goes in `out/`. It writes
`result.json` beside the call: the version it ran on, and the step's result or why it refused.
Whatever else goes wrong writes no result, which the adapter reports as a crash (native files
ADR-0015).

The commands are lattice's own, carried out through Blender's data API, each argument checked by
type: none runs Python an agent or a file brings, and none makes a text, a driver or a link.
"""

import json
import math
import re
import shutil
import sys
from pathlib import Path

import bmesh
import bpy
from mathutils import Vector

DOCUMENT = "document.blend"
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
SEGMENTS = 32
MODIFIERS = {
    "subdivision": ("SUBSURF", {"levels": (int, 0, 4)}),
    "bevel": ("BEVEL", {"width": (float, 0, 1e6), "segments": (int, 1, 16)}),
    "array": ("ARRAY", {"count": (int, 1, 1000)}),
    "mirror": ("MIRROR", {}),
    "solidify": ("SOLIDIFY", {"thickness": (float, -1e6, 1e6)}),
}
"""Each modifier an agent may add: Blender's type, and the numbers it may set, with their bounds."""
LIGHTS = {"point": "POINT", "sun": "SUN", "spot": "SPOT", "area": "AREA"}
ENGINES = {"workbench": "BLENDER_WORKBENCH", "cycles": "CYCLES"}
SETTABLE = {"name": str, "hide_render": bool, "hide_viewport": bool}


class Refused(Exception):
    """The call is refused, with why: the adapter's `refused`."""


# ─── arguments ────────────────────────────────────────────────────────────────


def take(args, allowed, required=()):
    """The arguments, refused if one is unknown or a required one is missing."""
    if not isinstance(args, dict):
        raise Refused("args must be an object")
    if unknown := set(args) - set(allowed) - set(required):
        raise Refused(f"unknown argument {sorted(unknown)[0]}")
    if missing := [key for key in required if key not in args]:
        raise Refused(f"missing argument {missing[0]}")
    return args


def number(args, key, *, low=-1e9, high=1e9, default=None):
    """A finite number, within its bounds."""
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Refused(f"{key} must be a number")
    if not low <= value <= high:
        raise Refused(f"{key} must be from {low:g} to {high:g}")
    return float(value)


def whole(args, key, *, low, high, default=None):
    """A whole number, within its bounds."""
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise Refused(f"{key} must be a whole number from {low} to {high}")
    return value


def point(args, key, size=3, default=None, *, low=-1e9, high=1e9):
    """A point of `size` numbers."""
    value = args.get(key, default)
    if not isinstance(value, list) or len(value) != size:
        raise Refused(f"{key} must be {size} numbers")
    return [number({key: v}, key, low=low, high=high) for v in value]


def text(args, key):
    """A string."""
    value = args.get(key)
    if not isinstance(value, str):
        raise Refused(f"{key} must be a string")
    return value


def name(args, default, key="name"):
    """A name an argument gives, or its default."""
    value = args.get(key, default)
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise Refused(f"{key} must be letters, digits and underscores, not starting with a digit")
    return value


def found(collection, args, key):
    """The data-block an argument names, refused if there is none."""
    held = collection.get(text(args, key))
    if held is None:
        raise Refused(f"no {key} {args[key]}")
    return held


# ─── the commands ─────────────────────────────────────────────────────────────


def linked(obj, at):
    """An object, put at a point in the scene's own collection."""
    obj.location = at
    bpy.context.scene.collection.objects.link(obj)
    return obj


def primitive(default, sizes, build):
    """A command that adds a mesh, built by bmesh from its sizes, each a positive number."""

    def add(args):
        """Add the mesh, as an object of its own."""
        take(args, ("name", "at"), sizes)
        given = {size: number(args, size, low=1e-6) for size in sizes}
        made = bmesh.new()
        build(made, **given)
        data = bpy.data.meshes.new(name(args, default))
        made.to_mesh(data)
        made.free()
        linked(bpy.data.objects.new(data.name, data), point(args, "at", 3, [0, 0, 0]))

    return add


def cube(made, size):
    """A cube, its edges `size` long."""
    bmesh.ops.create_cube(made, size=size)


def sphere(made, radius):
    """A UV sphere."""
    bmesh.ops.create_uvsphere(made, u_segments=SEGMENTS, v_segments=SEGMENTS // 2, radius=radius)


def cylinder(made, radius, depth):
    """A cylinder, a cone with both radii the same."""
    cone(made, radius, radius, depth)


def cone(made, radius1, radius2, depth):
    """A cone, or a frustum, along Z."""
    bmesh.ops.create_cone(
        made, cap_ends=True, segments=SEGMENTS, radius1=radius1, radius2=radius2, depth=depth
    )


def plane(made, size):
    """A square, `size` wide, flat on XY."""
    bmesh.ops.create_grid(made, x_segments=1, y_segments=1, size=size / 2)


def move(args):
    """Place, rotate and scale an object."""
    take(args, ("at", "rotation", "scale"), ("object",))
    obj = found(bpy.data.objects, args, "object")
    if "at" in args:
        obj.location = point(args, "at")
    if "rotation" in args:
        obj.rotation_euler = [math.radians(a) for a in point(args, "rotation")]
    if "scale" in args:
        obj.scale = point(args, "scale")


def material(args):
    """Add a material: its colour, how metallic and how rough."""
    take(args, ("name", "color", "metallic", "roughness"))
    made = bpy.data.materials.new(name(args, "Material"))
    made.diffuse_color = [*point(args, "color", 3, [0.8, 0.8, 0.8], low=0, high=1), 1]
    made.metallic = number(args, "metallic", low=0, high=1, default=0)
    made.roughness = number(args, "roughness", low=0, high=1, default=0.5)
    # Workbench draws the viewport's colour; Cycles and EEVEE the surface's, which match it.
    if (surface := made.node_tree.nodes.get("Principled BSDF")) is not None:
        surface.inputs["Base Color"].default_value = made.diffuse_color
        surface.inputs["Metallic"].default_value = made.metallic
        surface.inputs["Roughness"].default_value = made.roughness


def assign(args):
    """Give a mesh object a material, in its first slot."""
    take(args, (), ("object", "material"))
    obj = found(bpy.data.objects, args, "object")
    given = found(bpy.data.materials, args, "material")
    if obj.type != "MESH":
        raise Refused(f"{obj.name} is not a mesh")
    if obj.data.materials:
        obj.data.materials[0] = given
    else:
        obj.data.materials.append(given)


def modifier(args):
    """Add a modifier to a mesh object, of an allowed type, with its numbers."""
    if not isinstance(args, dict) or args.get("type") not in MODIFIERS:
        raise Refused(f"type must be one of {sorted(MODIFIERS)}")
    blender, numbers = MODIFIERS[args["type"]]
    take(args, ("name", *numbers, *(("axes",) if blender == "MIRROR" else ())), ("object", "type"))
    obj = found(bpy.data.objects, args, "object")
    if obj.type != "MESH":
        raise Refused(f"{obj.name} is not a mesh")
    added = obj.modifiers.new(name(args, args["type"].capitalize()), blender)
    for key, (cast, low, high) in numbers.items():
        if key in args:
            given = whole if cast is int else number
            setattr(added, key, given(args, key, low=low, high=high))
    if "axes" in args:
        axes = args["axes"]
        if (
            not isinstance(axes, list)
            or len(axes) != 3
            or not all(isinstance(a, bool) for a in axes)
        ):
            raise Refused("axes must be 3 booleans")
        added.use_axis = axes


def aimed(obj, args):
    """Point an object at a point: the origin by default."""
    target = Vector(point(args, "look_at", 3, [0, 0, 0]))
    direction = target - obj.location
    if direction.length == 0:
        raise Refused("look_at must differ from at")
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def camera(args):
    """Add a camera at a point, looking at another, the scene's own unless it has one."""
    take(args, ("name", "look_at", "lens"), ("at",))
    data = bpy.data.cameras.new(name(args, "Camera"))
    data.lens = number(args, "lens", low=1, high=5000, default=50)
    obj = linked(bpy.data.objects.new(data.name, data), point(args, "at"))
    aimed(obj, args)
    if bpy.context.scene.camera is None:
        bpy.context.scene.camera = obj


def light(args):
    """Add a light of a type, its power in watts, at a point, looking at another."""
    take(args, ("name", "color", "look_at"), ("type", "energy", "at"))
    if (kind := LIGHTS.get(args["type"])) is None:
        raise Refused(f"type must be one of {sorted(LIGHTS)}")
    data = bpy.data.lights.new(name(args, args["type"].capitalize()), kind)
    data.energy = number(args, "energy", low=0, high=1e7)
    data.color = point(args, "color", 3, [1, 1, 1], low=0, high=1)
    aimed(linked(bpy.data.objects.new(data.name, data), point(args, "at")), args)


def collection(args):
    """Add a collection, in the scene's own or in another."""
    take(args, ("parent",), ("name",))
    parent = bpy.context.scene.collection
    if "parent" in args:
        parent = found(bpy.data.collections, args, "parent")
    made = bpy.data.collections.new(name(args, None))
    parent.children.link(made)


def link(args):
    """Move an object into a collection, out of every other."""
    take(args, (), ("object", "collection"))
    obj = found(bpy.data.objects, args, "object")
    target = found(bpy.data.collections, args, "collection")
    for holder in list(obj.users_collection):
        holder.objects.unlink(obj)
    target.objects.link(obj)


def render(args):
    """Set the scene's render: its engine, its size, and Cycles' samples."""
    take(args, ("engine", "width", "height", "samples"))
    settings = bpy.context.scene.render
    if "engine" in args:
        if (engine := ENGINES.get(args["engine"])) is None:
            raise Refused(f"engine must be one of {sorted(ENGINES)}")
        settings.engine = engine
    if "width" in args:
        settings.resolution_x = whole(args, "width", low=16, high=16384)
    if "height" in args:
        settings.resolution_y = whole(args, "height", low=16, high=16384)
    if "samples" in args:
        bpy.context.scene.cycles.samples = whole(args, "samples", low=1, high=4096)


def set_property(args):
    """Set an object's name, or whether it is rendered or shown."""
    take(args, (), ("object", "property", "value"))
    obj, prop, value = (
        found(bpy.data.objects, args, "object"),
        text(args, "property"),
        args["value"],
    )
    if (kind := SETTABLE.get(prop)) is None:
        raise Refused(f"property must be one of {sorted(SETTABLE)}")
    if not isinstance(value, kind) or (prop == "name" and not NAME.fullmatch(value)):
        raise Refused(f"{prop} must be a {kind.__name__}" + (", a name" if kind is str else ""))
    setattr(obj, prop, value)


def remove(args):
    """Remove an object that no other object is a child of."""
    take(args, (), ("object",))
    obj = found(bpy.data.objects, args, "object")
    if children := [child.name for child in obj.children]:
        raise Refused(f"{obj.name} is the parent of {', '.join(children)}")
    bpy.data.objects.remove(obj)


COMMANDS = {
    "cube": primitive("Cube", ("size",), cube),
    "sphere": primitive("Sphere", ("radius",), sphere),
    "cylinder": primitive("Cylinder", ("radius", "depth"), cylinder),
    "cone": primitive("Cone", ("radius1", "radius2", "depth"), cone),
    "plane": primitive("Plane", ("size",), plane),
    "move": move,
    "material": material,
    "assign": assign,
    "modifier": modifier,
    "camera": camera,
    "light": light,
    "collection": collection,
    "link": link,
    "render": render,
    "set": set_property,
    "remove": remove,
}


# ─── the steps ────────────────────────────────────────────────────────────────


def opened(here):
    """The source, opened where it is saved, with no script of its own run; or an empty scene.

    An empty scene is saved and opened as a source is, so both are saved from the same start.
    """
    source, out = here / "in" / DOCUMENT, here / "out" / DOCUMENT
    if source.exists():
        shutil.copy(source, out)
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(out))
    bpy.ops.wm.open_mainfile(filepath=str(out), load_ui=False, use_scripts=False)
    inert()


def inert():
    """Refuse what the scan refuses, as Blender read it: a second line, never the first."""
    if bpy.data.texts or bpy.data.libraries or bpy.data.images:
        raise Refused("it holds a text, a link to another file or an image")
    held = (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
            bpy.data.lights, bpy.data.scenes, bpy.data.collections)  # fmt: skip
    if any(getattr(each, "animation_data", None) for blocks in held for each in blocks):
        raise Refused("it holds animation or a driver")
    parents = {obj.name: obj.parent.name if obj.parent else None for obj in bpy.data.objects}
    for start in parents:
        seen, at = set(), start
        while at is not None:
            if at in seen:
                raise Refused(f"its objects' parents make a cycle: {start}")
            seen.add(at)
            at = parents.get(at)


def apply(commands):
    """Run the commands in order, refused whole at the first that fails."""
    for index, command in enumerate(commands):
        run = COMMANDS.get(command.get("name"))
        if run is None:
            raise Refused(f"command {index + 1}: no command {command.get('name')!r}")
        try:
            run(command.get("args", {}))
        except Refused as refused:
            raise Refused(f"command {index + 1}, {command['name']}: {refused}") from None
        except (TypeError, ValueError, RuntimeError) as error:
            raise Refused(f"command {index + 1}, {command['name']}: {error}") from None


def saved(here, compressed):
    """The scene saved, closed and opened again, then saved, so its next save is a fixpoint.

    The first save of a scene a batch made writes what a later open and save would change.
    """
    path = str(here / "out" / DOCUMENT)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=compressed)
    bpy.ops.wm.open_mainfile(filepath=path, load_ui=False, use_scripts=False)
    bpy.ops.wm.save_as_mainfile(filepath=path, compress=compressed)


def reading():
    """What the adapter reads the scene into: its objects, its materials and its collections."""
    return {
        "objects": [
            {"name": o.name, "type": o.type, "collections": [c.name for c in o.users_collection]}
            for o in bpy.data.objects
        ],
        "materials": [m.name for m in bpy.data.materials],
        "collections": [c.name for c in bpy.data.collections],
    }


def draw(width, path):
    """Draw the scene through its camera, by Workbench, `width` pixels wide."""
    scene = bpy.context.scene
    if scene.camera is None:
        raise Refused("nothing to draw: the scene has no camera")
    settings = scene.render
    aspect = settings.resolution_y / settings.resolution_x
    settings.engine = "BLENDER_WORKBENCH"
    # Neither a compositor's nodes nor the sequencer's strips run, nor write files of their own.
    settings.use_compositing = settings.use_sequencer = False
    settings.resolution_x, settings.resolution_y = width, max(16, round(width * aspect))
    settings.resolution_percentage = 100
    settings.image_settings.file_format = "PNG"
    settings.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def step(here, call):
    """The call's step, on the source or an empty scene."""
    try:
        opened(here)
    except Refused:
        raise
    except RuntimeError as error:
        raise Refused(f"Blender can't open it: {error}") from None
    if call["step"] == "render":
        if call["page"] != 1:
            raise Refused(f"no page {call['page']}: a scene is drawn as page 1")
        draw(call["width"], here / "out" / "page.png")
        return {}
    if call["step"] == "apply":
        apply(call["commands"])
        saved(here, call["compressed"])
    return reading()


def main():
    """Run the call, and write its result beside it."""
    called = Path(sys.argv[sys.argv.index("--pass") + 1])
    here = called.parent
    # No backup beside a save, no state between calls.
    bpy.context.preferences.filepaths.save_version = 0
    version = ".".join(str(part) for part in bpy.app.version)
    try:
        result = {"version": version, "result": step(here, json.loads(called.read_text()))}
    except Refused as refused:
        result = {"version": version, "refused": str(refused)}
    (here / "result.json").write_text(json.dumps(result))


# Blender runs a file it is given by --python as __main__; a test imports it under another name.
if __name__ == "__main__":
    main()
