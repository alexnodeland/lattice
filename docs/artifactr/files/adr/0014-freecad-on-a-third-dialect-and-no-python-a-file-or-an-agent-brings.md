# ADR-0014: FreeCAD on a third dialect, a script it runs, and no Python a file or an agent brings

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** [ADR-0009](0009-each-crafting-app-declared-once-on-one-of-two-dialects.md), whose apps were all storytold's, on one of two dialects, each started by `Spawn`

Adds FreeCAD as an app for native files, under lattice [RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md): its documents, `.FCStd`, kept as native files, edited by people in FreeCAD and by agents through a set of commands of lattice's own.

## Context

FreeCAD is a parametric 3D modeller, open source under LGPL-2.1-or-later, released by the FreeCAD project, not by storytold, so no brand licence binds its name. On 2026-10-20 we ran its release 1.1.4, the latest stable, in a Linux container on aarch64 (`docker run --network none`, as a user of its own), from its official AppImage, unpacked with `--appimage-extract`, whose SHA-256 matched the release's own `-SHA256.txt`:

- **No server of its own, a console.** FreeCAD itself ships no MCP server and no stdio protocol; the community's servers are below, under Option E. Its `freecadcmd` runs a Python script in FreeCAD's own interpreter, with no GUI: `freecadcmd -u USER.cfg -s SYSTEM.cfg --safe-mode SCRIPT --pass ARG` gives the script `ARG` in `sys.argv`, and starts in about a second. A script reads, edits and saves documents through FreeCAD's document API (`FreeCAD.openDocument`, `addObject`, `recompute`, `saveAs`).
- **The format.** An `.FCStd` is a zip: `Document.xml`, which holds every object's type and properties, a `.brp` per shape, which a recompute makes again, and, when the GUI saved it, `GuiDocument.xml` (colours, visibility, the camera) and a thumbnail. FreeCAD's own MIME file names it `application/x-extension-fcstd`.
- **What a save changes.** Opening a file sets the document's `Label` to the file's name, and every save sets `LastModifiedDate` to the second. Opened and saved again with no recompute, every other part was the same bytes, in three processes in a row. `freecadcmd` drops `GuiDocument.xml` and the thumbnail, since it has no GUI to write them.
- **Python in a file.** An object's type may be a Python feature (`App::FeaturePython`, `Part::FeaturePython`, and every Draft and BIM object), whose `Proxy` is a `PropertyPythonObject`: a class named by `module` and `class`, with its state. FreeCAD 1.1.4 refuses a pickled state (`PropertyPythonObject::Restore: unsupported serialisation`), and imports only FreeCAD's own modules and installed addons (`blocked import of module 'this' during document restore`): a file of ours whose pickle runs `os.system`, and one naming a standard library module, both opened without running either, with and without `--safe-mode`. A file naming a FreeCAD module, such as Draft's, does import it and run its code on the file's state; we did not try to make that run code of the file's.
- **Expressions.** A property or a cell may be an expression. `eval`, `__import__`, `module`, `App.ParamGet` and `builtins.open` in a cell were kept as text, not run.
- **Headless pages.** `freecadcmd` has no view to render. `TechDraw.projectEx` projects a shape's visible edges along a direction, with no GUI, and the AppImage carries Pillow, so a script can draw them as a PNG.
- **Releases.** The 1.1.4 release has an AppImage for each of Linux x86_64 and aarch64, a macOS disk image, Windows installers and the source, each with a `-SHA256.txt` beside it, and no signature. 0.21 is the last release before 1.0, and has neither guard on Python.

## Decision

- **FreeCAD is `CRAFTS["freecad"]`,** key `files:freecad`, off by default, its title and description plain: `FreeCAD: 3D models kept as native files, edited by people and agents.` `Craft` gains `cli` and `repository` as fields, `<name>-cli` and `storytold/<name>` by default, so FreeCAD's are `freecadcmd` and `FreeCAD/FreeCAD`. It keeps `.FCStd` under `FCSTD`, `application/x-extension-fcstd`, as a `CadModel`, registered as `cad_model`; its `roots` are `none`, since a script reads and writes wherever its user can, so its adapter is made only with `trusted=True`. It is meant to run in the worker; until stackr's image has FreeCAD (action item 4), nothing runs it there.
- **A third dialect, `script`.** `Script` is the one place a script CLI starts, as `Spawn` is for an MCP server: for every call, in an empty temporary directory, under the launcher, with the call's deadline, its `HOME` in the directory and nothing else of the environment but `PATH`, the locale and `QT_QPA_PLATFORM=offscreen`. FreeCAD's adapter gives `freecadcmd` its settings files in the directory and `--safe-mode`, so no user macro, addon or setting is loaded. The call is JSON in a file the script is given by `--pass`; the script writes its result as JSON beside it, with the version it ran on, which must be the pin. A result that is missing or doesn't parse is `crashed`, with the end of what the CLI printed; a result that says the script refused is `refused`. The script, `artifactr/files/freecad/console/script.py`, imports FreeCAD's modules and the standard library alone; it is shipped in the package, run by path, in a folder that isn't a package, so nothing that imports every module of artifactr reaches it.
- **FreeCAD is given only what the scan rebuilt.** The scan's zip reader is Python's, not FreeCAD's, and two readers can read one zip two ways (a part named twice, a part only a local header names, bytes before the first part). So the adapter never gives FreeCAD the bytes it was sent: it reads every part through the zip's directory, inflating each and counting what it inflates against the limit, whatever its header says, and gives FreeCAD a fresh zip of those parts, regular files with plain names, with the source's `GuiDocument.xml` put back on top for an apply. It refuses, as `refused`, a file that isn't a zip it can read (a header that understates a part's size fails its check), that has bytes before its first part, more than a thousand parts, a part named twice (ignoring case), a part named out of its folder (`..`, an absolute path, a backslash, `./`), or a part that isn't a regular file (a folder, a symlink); and, as `too_large`, one that inflates past the limit, or an XML part past 64 MiB. **The order is FreeCAD's own.** Read in FreeCAD's source at the `1.1.4` tag on 2026-10-20: `Document::restore` (`src/App/Document.cpp`) streams the zip with `zipios::ZipInputStream`, and `Base::XMLReader` parses its first entry as the document, whatever it is named; `XMLReader::readFiles` (`src/Base/Reader.cpp`) then takes the rest one by one, looks for each among the files still to be read, in the order objects asked for them (`addFile`), reads it if found and moves past it (`it = jt + 1`), and never goes back, so a part that comes after one asked for later is skipped. So the scan writes `Document.xml` first, then the parts in the order its `file` attributes name them, then `GuiDocument.xml` and the parts it names, whatever order they came in, and drops thumbnails; a part nothing names is refused. Run against 1.1.4 in a container, by live tests: a zip whose first entry is `a.txt`, holding a Python feature, opens as `a.txt`'s objects, not `Document.xml`'s; and the booleans corpus file with its parts sorted by name opens with shapes missing, where the scan's order opens with all of them. Neither is an audit of zipios or Xerces.
- **What the scan allows, it lists; the rest is refused.** It reads `Document.xml` and `GuiDocument.xml` with no DTD, no entity, no namespaced name and no element more than 256 deep, and refuses:
  - an object whose type isn't one the commands or the corpus make, by its exact type (`Part::Box`, `PartDesign::Pad`, `Sketcher::SketchObject`, `Spreadsheet::Sheet` and the rest), so a pin raised to a release with other types fails closed;
  - an extension or a property whose type isn't one they make, so a Python object, an included or linked file, a path, a persistent object or an external link (`PropertyFileIncluded`, `PropertyPath`, `PropertyPersistentObject`, `PropertyXLink`) is refused by its type, and a view provider's property outside the C++ view providers' plain types;
  - a `Python` element; an `XLink` naming a `file`, or an `XLinks` mapping documents (`DocMap`), which FreeCAD's `PropertyXLink::Restore` and `PropertyXLinkContainer::Restore` read (checked in FreeCAD 1.1.4's source);
  - an expression or a cell with a `#`, which names another document (`doc#Object`, `<<doc>>#Object`); `sheet.set` refuses one too;
  - an `Objects` or `ObjectData` list whose `Count` isn't how many objects it lists, since FreeCAD reads as many as it says;
  - an object attribute that isn't one `Document::Restore` reads (`ViewType`, which names a view provider to make, is refused), a view provider's other than its name, `expanded`, `treeRank` and `Extensions`, and a view provider's extension outside those FreeCAD's GUI saved for a box;
  - a name ending in a dot or a space.
  - The GUI's `<Camera settings>` is an Open Inventor string the GUI parses, and the console never reads; a camera with any attribute but `settings`, or in `Document.xml`, is refused, and the scan empties its settings, quoted either way, then reads the part again and refuses it if any camera still holds one. A file's camera isn't kept.
  - This refuses every Draft, BIM and addon file. It is what the scan proves of what FreeCAD is given; it is not an audit of FreeCAD's reader, and a shape's `.brp`, which OpenCASCADE parses, isn't scanned at all.
- **An agent's commands are lattice's, never Python.** The commands are a fixed set the script carries out through the document API: primitives (`box`, `cylinder`, `sphere`, `cone`), `boolean` (`cut`, `fuse`, `common`), `sketch`, `sketch.line`, `sketch.circle`, `sketch.constraint`, `extrude`, `move`, `set`, `remove`, `sheet`, `sheet.set` and `sheet.alias`. Each argument is checked by type; `set` writes only a number, a string or a boolean, and only to a property its object already has; nothing makes a Python feature or a macro. `commands(query)` finds them in the adapter, with no CLI started. After a batch the document is recomputed, and an object left invalid refuses the batch; then it is saved, closed and opened again before its save, since the first save of what a batch made differs from the next (in shapes' parts and in property flags), and a reopened one's doesn't. No command runs Python, and none will without a decision of its own.
- **What a save keeps.** The source is written as `document.FCStd`, the `Label` it held is set again after it is opened, a document whose objects' links make a cycle is refused, and it is saved with no recompute unless commands ran, so the shapes' bytes are kept. The adapter puts the source's `GuiDocument.xml` back into the saved file, so colours and visibility survive a save by an agent; an object a batch added has none until FreeCAD's GUI saves it. The thumbnail is dropped, since a batch may have made it stale.
- **The fingerprint is the document's, without its date:** the SHA-256 of every part's name and bytes, sorted by name, with `LastModifiedDate`'s value left out of `Document.xml` and the thumbnail left out, so a save that changes nothing of a file the GUI made keeps its fingerprint. Two saves in a row must have the same fingerprint, which the fidelity report holds.
- **A page is the model, drawn.** `render` draws page 1: every shape no other object uses, its visible edges projected isometrically by `TechDraw.projectEx`, drawn by Pillow `PREVIEW` times `scale` pixels wide. A document with no shape has nothing to draw, and is refused.
- **Pinned to 1.1.4, by its AppImages.** `scripts/crafts/freecad.sha256` holds the release's own lines for the x86_64 and aarch64 AppImages; `scripts/craft freecad cli` fetches and checks this machine's, unpacks it with `--appimage-extract`, since CI has no FUSE, and prints `usr/bin/freecadcmd`. There is no macOS CLI and no browser build: on macOS, and for `web`, it says so and fails. A release's notices are its own (`usr/share/licenses`, its Python's, its addons'), which `notices` lists.
- **The corpus is FreeCAD's own.** One `.FCStd` per feature, made by `make.py` running in `freecadcmd` in a Linux container, each a few kilobytes, committed as the other corpora are. Its files can't be made again where FreeCAD isn't, so its drift test runs with the live tests, and compares each feature's value, since a new document's `Uid` and dates are new each time. Its hostile files are a zip bomb, a `Document.xml` past its limit, XML nested past its depth, an entity, a Python feature with a pickled state, one naming a FreeCAD module, a GUI document with a view provider's proxy, a link to `/etc/passwd` in a real property (of its own type, and inside an allowed one), a `Document.xml` with Python before the zip that only a local header names, a duplicate `Document.xml`, names that leave the folder or are absolute or hold a backslash, a symlink, a part whose headers understate its size, a list whose count lies, and objects whose links make a cycle; every one but the cycle is refused before FreeCAD starts, and the cycle by the script. Each ended within two seconds, and under the worker's default limits (2 GiB of address space) an edit with every command took 0.45 s and a render 0.26 s, on aarch64 only: the x86_64 AppImage, its pin line and Nightly's job have never run.

## Options considered

### Option A: A script run by `freecadcmd`, curated commands, and refusing Python-bearing files (chosen)

| Dimension | Assessment |
|---|---|
| Fit | The App port's four calls, each one process, as every other app |
| Safety | No command runs Python, and FreeCAD is given only a rebuilt document of allowed types; FreeCAD's own guards stay behind ours; the worker is meant to confine the rest |
| Cost | A third dialect, a script that can be tested only live, and Draft and BIM files refused |

### Option B: Trust FreeCAD 1.1.4's restore guard, and the worker

**Pros:** Draft and BIM files open, as do addons' objects installed in the image.

**Cons:** the guard lets FreeCAD's own modules run on a file's state, Draft's alone being thousands of lines of Python; we can't say that is safe, only that we didn't break it. The worker would be the only line.

### Option C: Expose Python to the agent, as FreeCAD's own console does

**Pros:** everything FreeCAD can do.

**Cons:** an agent writing Python in FreeCAD's interpreter is code execution, confined only by the worker, and a prompt in a file could write it. That is the owner's to decide, if ever, in a record of its own.

### Option D: An MCP server of our own around FreeCAD

**Cons:** a long-lived server per call adds a protocol for one app; a script that reads a file and writes one is the call itself.

### Option E: A community FreeCAD MCP server

Checked on 2026-10-20 by reading their repositories, not by running them. The best known is `neka-nat/freecad-mcp` (MIT, about 3,000 stars, active this month): an addon inside a running FreeCAD GUI starts an XML-RPC server on localhost, with no authentication unless a token is set, and an MCP server calls it. Its tools include `create_object`, `edit_object` and `get_view`, and, at its core, `execute_code` (Python on FreeCAD's GUI thread, in a namespace that persists between calls), `execute_code_async` and `execute_code_headless` (any script in a `freecadcmd` process). `spkane/freecad-addon-robust-mcp-server` (MIT, about 250 stars, active) has 150 and more tools, a headless mode, an XML-RPC or JSON-RPC bridge on a port, and `execute_python`. Others (`bonninr/freecad_mcp`, `ATOI-Ming/FreeCAD-MCP`, `blwfish/freecad-mcp`) take the same shape.

**Pros:** many more operations than our sixteen, screenshots from the GUI, and maintainers.

**Cons:** each is a long-lived FreeCAD with documents open between calls, listening on a port, where ADR-0004 wants a stateless call and RFC-0003's worker wants no listener; most need the GUI; and each makes arbitrary Python a tool, which is Option C. Using one with its Python tools removed would mean auditing and pinning a third party's server for a subset of what our script does. Not adopted; it doesn't change the decision. A curated tool set of one, such as `spkane`'s, is worth reading when the commands grow.

## Trade-off analysis

A script per call keeps each call one process, as ADR-0004 wants, and costs one runner beside `Spawn`. Refusing Python-bearing files costs every Draft and BIM drawing, which a person can still keep as an upload; in exchange no file of a type the scan doesn't allow reaches FreeCAD, and so none with a Python feature; what FreeCAD's own readers, and OpenCASCADE's, do with an allowed file is still theirs. Lattice's own commands are fewer than FreeCAD's API, and each says what it may touch.

## Consequences

- Easier: a solid model, its sketches and its spreadsheet are kept, diffed by fingerprint and drawn, by people and agents.
- Easier: a later third-party app with a console and no server can use `Script`.
- Harder: `console/script.py` needs FreeCAD's modules, so its coverage isn't measured on pull requests; its pure checks are tested there against stand-ins for those modules, and its live tests, in Nightly's fidelity job, run every command and step.
- Harder: `--safe-mode` keeps out user macros and addons; it is not a sandbox. The checksums come from the same GitHub release as the AppImages, so the pin holds the bytes to what was first checked, not to a signature.
- Harder: a file from FreeCAD's GUI with a view provider's property or extension outside the allowed sets is refused, never read loosely; the sets hold what FreeCAD 1.1.4's GUI saved for a coloured, hidden box (run offscreen in a container, a test's file), and grow with evidence. Such a file's first save by the console isn't a fixpoint (property flags and a shape's part are written again), so it costs one revision; the next is.
- Harder: a thousand parts is a limit, and a large legitimate model with more shapes is refused.
- Harder: a call holds the file sent, its inflated parts and the rebuilt zip at once: about three times the file's inflated size at its peak, within the worker's limits.
- Harder: FreeCAD runs only under `trusted=True`, so in the worker; its key stays off. Nothing measures yet how much memory a recompute of a hostile model may take, but the worker's limits.
- Harder: an object an agent adds has no colour until a person saves it in FreeCAD.
- Revisit: Draft, BIM and addons, under Option B, once there is evidence about FreeCAD's own proxies on hostile state; exporting a STEP or an STL, which the App port has no call for; each new FreeCAD release's guards before its pin is raised.

## Action items

1. [x] `Craft.cli` and `Craft.repository`; the `script` dialect, `Script`; FreeCAD's adapter, `artifactr.files.freecad`, its scan, its rebuilt zip and its script; `FCSTD` and `CadModel`.
2. [x] The key in lattice-core's registry, and portalr's generated copies.
3. [x] The pin, `scripts/craft`'s AppImage, the corpus, the hostile files and Nightly's fidelity entry. That every command's output passes the scan is held only live (an apply of a batch's output, in Nightly), since no pull request has FreeCAD; Nightly's first FreeCAD run is still to come.
4. [ ] stackr: FreeCAD in a worker image of its own, from the pinned AppImage.
