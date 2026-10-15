# Run using the GUI

Once the package has been [installed](installation), the user should create a folder where a specific assessment will be performed. From now on, such folder is referred as ``<root>``.

CASSY can now be run also from a GUI interface. These interfaces make it easier (and safer) to configure your
assessment. Moreover, it allows to import and export entire assessment configurations in .json format.

To start it, simply run for paths:

```bash
python -m cassy --pathsgui
```

see [Paths assessment](paths) for further details.

or for bolts:

```shell
python -m cassy --boltsgui
```

see [Bolts assessment](bolts) for further details.

!!! warning

    The GUIs are in beta! Expect (and report) bugs

!!! note

    Excel configuration files are no longer supported. Assessments are configured in the GUIs and
    saved as .json project files. Project files saved by older versions of the GUIs are upgraded
    automatically when opened.

## Run a project from the command line

A project saved from the GUIs can be run without opening them, e.g. on a remote machine or in a
batch of assessments:

```bash
python -m cassy --run <project>.json
```

The paths or bolts assessment is detected from the project content and run with the run options
saved in it (output folder, fatigue, trace, ...), exactly as the *Run* button of the GUI would.

## Portable projects

When a project is saved, the paths it contains (stress tensors or actions files, additional
materials folder, output folder) are stored relative to the project file if they are inside its
folder or subfolders, and absolute otherwise (e.g. data on a shared network drive). Relative paths
are taken from the folder of the project file, both by the GUIs and by ``--run``.

Keeping the data, materials and output inside the project folder, the whole folder can then be
moved, zipped or shared, also between Windows and Linux. Projects saved by older versions keep their
absolute paths until they are saved again.