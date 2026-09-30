# Run using the GUI

Once the package has been [installed](user_guide/installation), the user should create a folder where a specific assessment will be performed. From now on, such folder is referred as ``<root>``.

CASSY can now be run also from a GUI interface. These interfaces make it easier (and safer) to configure your
assessment. Moreover, it allows to import and export entire assessment configurations in .json format.

To start it, simply run for paths:

```bash
python -m cassy --pathsgui
```

see [Paths assessment](user_guide/paths) for further details.

or for bolts:

```shell
python -m cassy --boltsgui
```

see [Bolts assessment](user_guide/bolts) for further details.

!!! warning

    The GUIs are in beta! Expect (and report) bugs

