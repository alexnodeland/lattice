# pyright: basic, reportMissingImports=false
"""Makes FreeCAD's corpus: one `.FCStd` per feature, run by FreeCAD itself, in its console.

Run as `freecadcmd make.py --pass DIRECTORY [FEATURE...]`, every feature if none is named. Each
file is the smallest document that holds its feature, made through FreeCAD's document API and
saved by FreeCAD, so its shapes are FreeCAD's own; `gui` then gains a `GuiDocument.xml` written
here, as FreeCAD's GUI would save one, since the console writes none. A new document's `Uid` and
dates are new each time, so a test compares what each feature's value is, not the bytes.
"""

import sys
import zipfile
from pathlib import Path

import FreeCAD as App
import Part
import Sketcher

GUI = """<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="1" HasExpansion="1">
    <ViewProviderData Count="1">
        <ViewProvider name="Box" expanded="0">
            <Properties Count="2" TransientCount="0">
                <Property name="ShapeAppearance" type="App::PropertyMaterialList">
                    <MaterialList file="ShapeAppearance" version="3"/>
                </Property>
                <Property name="Visibility" type="App::PropertyBool">
                    <Bool value="false"/>
                </Property>
            </Properties>
        </ViewProvider>
    </ViewProviderData>
    <Camera settings=""/>
</Document>
"""


def primitives(document):
    box = document.addObject("Part::Box", "Box")
    box.Length, box.Width, box.Height = 20, 10, 5
    cylinder = document.addObject("Part::Cylinder", "Cylinder")
    cylinder.Radius, cylinder.Height = 4, 12
    cylinder.Placement = App.Placement(App.Vector(30, 0, 0), App.Rotation())
    sphere = document.addObject("Part::Sphere", "Sphere")
    sphere.Radius = 6
    sphere.Placement = App.Placement(App.Vector(0, 30, 0), App.Rotation())
    cone = document.addObject("Part::Cone", "Cone")
    cone.Radius1, cone.Radius2, cone.Height = 5, 2, 8
    cone.Placement = App.Placement(App.Vector(30, 30, 0), App.Rotation())


def booleans(document):
    box = document.addObject("Part::Box", "Box")
    box.Length = box.Width = box.Height = 10
    cylinder = document.addObject("Part::Cylinder", "Cylinder")
    cylinder.Radius, cylinder.Height = 3, 10
    cylinder.Placement = App.Placement(App.Vector(5, 5, 0), App.Rotation())
    cut = document.addObject("Part::Cut", "Cut")
    cut.Base, cut.Tool = box, cylinder
    sphere = document.addObject("Part::Sphere", "Sphere")
    sphere.Radius = 4
    fused = document.addObject("Part::Fuse", "Fusion")
    fused.Base, fused.Tool = cut, sphere


def sketch(document):
    drawn = document.addObject("Sketcher::SketchObject", "Sketch")
    corners = [(0, 0), (20, 0), (20, 10), (0, 10)]
    for index, start in enumerate(corners):
        end = corners[(index + 1) % 4]
        drawn.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)))
    drawn.addGeometry(Part.Circle(App.Vector(10, 5, 0), App.Vector(0, 0, 1), 2))
    for index in range(4):
        drawn.addConstraint(Sketcher.Constraint("Coincident", index, 2, (index + 1) % 4, 1))
    drawn.addConstraint(Sketcher.Constraint("Horizontal", 0))
    drawn.addConstraint(Sketcher.Constraint("Vertical", 1))
    drawn.addConstraint(Sketcher.Constraint("DistanceX", 0, 1, 0, 2, 20))
    drawn.addConstraint(Sketcher.Constraint("Radius", 4, 2))


def extrusion(document):
    sketch(document)
    extruded = document.addObject("Part::Extrusion", "Extrude")
    extruded.Base, extruded.DirMode, extruded.Solid = document.Sketch, "Normal", True
    extruded.LengthFwd = 7


def part_design(document):
    body = document.addObject("PartDesign::Body", "Body")
    drawn = body.newObject("Sketcher::SketchObject", "Sketch")
    drawn.AttachmentSupport = [(body.Origin.OriginFeatures[3], "")]
    drawn.MapMode = "FlatFace"
    drawn.addGeometry(Part.Circle(App.Vector(0, 0, 0), App.Vector(0, 0, 1), 5))
    pad = body.newObject("PartDesign::Pad", "Pad")
    pad.Profile, pad.Length = drawn, 3


def spreadsheet(document):
    sheet = document.addObject("Spreadsheet::Sheet", "Spreadsheet")
    sheet.set("A1", "Length")
    sheet.set("B1", "42")
    sheet.setAlias("B1", "length")
    sheet.set("B2", "=B1 * 2")


def expressions(document):
    spreadsheet(document)
    box = document.addObject("Part::Box", "Box")
    box.setExpression("Length", "Spreadsheet.length")
    box.setExpression("Width", "Length / 2")


def placement(document):
    box = document.addObject("Part::Box", "Box")
    box.Placement = App.Placement(App.Vector(1, 2, 3), App.Rotation(App.Vector(0, 0, 1), 30))


def gui(document):
    box = document.addObject("Part::Box", "Box")
    box.Label = "Hidden box"


FEATURES = {
    "primitives": primitives,
    "booleans": booleans,
    "sketch": sketch,
    "extrusion": extrusion,
    "part_design": part_design,
    "spreadsheet": spreadsheet,
    "expressions": expressions,
    "placement": placement,
    "gui": gui,
}


def make(folder, feature):
    document = App.newDocument(feature)
    FEATURES[feature](document)
    document.recompute()
    path = folder / f"{feature}.FCStd"
    document.saveAs(str(path))
    App.closeDocument(document.Name)
    if feature == "gui":
        with zipfile.ZipFile(path, "a", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("GuiDocument.xml", GUI)


def main():
    given = sys.argv[sys.argv.index("--pass") + 1 :]
    folder = Path(given[0])
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("CreateBackupFiles", False)
    for feature in given[1:] or FEATURES:
        make(folder, feature)


main()
