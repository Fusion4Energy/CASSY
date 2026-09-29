# Run using the GUI

Once the package has been [installed](user_guide/installation), the user should create a folder where a specific assessment will be performed. From now on, such folder is referred as ``<root>``.

CASSY can now be run also from a GUI interface. These interfaces make it easier (and safer) to configure your
assessment. Moreover, it allows to import and export entire assessment configurations in .json format.

To start it, simply run for paths:

```bash
python -m cassy --pathsgui
```

or for bolts:

```shell
python -m cassy --boltsgui
```

!!! warning

    The GUIs are in beta! Expect (and report) bugs


# Run from command line


1. Setup the correct folder structure in ``<root>`` depending on the type of assessment.
   Jump to [Paths assessment](user_guide/paths) or [Bolts assessment](user_guide/bolts) for additional details.
2. open an anaconda prompt shell and change directory to ``<root>`` Then type:

```bash
python -m cassy
```

There a few arguments that can be provided through command line and are listed in the sections below.
Here is an example to run a paths assessment including fatigue assessment:

```bash
python -m cassy --assess paths --fatigue
```

## Mandatory arguments

- `--assess` this accepts either "paths" or "bolts" and it is used to specify which kind of assessment should
be performed.

## Optional arguments
- `--fatigue` if the argument is passed, the fatigue assessment will also be performed.
- `--root` by default is the current working directory, but with this command it can be changed to any other folder.
- `--matlib` this argument allows users to provide a path where additional material files are stored. Check the [additional materials section](user_guide/materials#additional-materials) for additional details.
- `--norecap` if used, the word recap is not printed. Only a global dataframe is dumped with all the assessment information (much faster execution).
- `--nomerge` merging cells in python docx is a pretty slow operations. Using this options allows to skip this step granting a faster execution. The price is a worse table formatting.
- `--onlybolts` in a bolts assessment allows to perform the assessment only on the bolts. By default, base material threads are included instead.