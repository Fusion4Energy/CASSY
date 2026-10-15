from __future__ import annotations

import logging
import sys
from argparse import ArgumentParser


def _parser() -> ArgumentParser:
    parser = ArgumentParser(
        prog="cassy",
        description="CASSY. Assessments are configured in the GUIs and saved as .json "
        "project files, which can be run here without opening the GUIs.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--pathsgui",
        help="Run the GUI for paths assessment",
        action="store_true",
    )
    group.add_argument(
        "--boltsgui",
        help="Run the GUI for bolts assessment",
        action="store_true",
    )
    group.add_argument(
        "--run",
        metavar="PROJECT",
        help="Run the paths or bolts assessment saved in a GUI project .json file, "
        "with the run options saved in it. Relative paths in the project are taken "
        "from the project folder.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)

    if args.pathsgui:
        from cassy.gui.paths_gui import main as run_paths_gui

        run_paths_gui()
    elif args.boltsgui:
        from cassy.gui.bolts_gui import main as run_bolts_gui

        run_bolts_gui()
    else:
        import json

        from cassy.runners.run_project import ProjectError, run_project

        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        try:
            root = run_project(args.run)
        # configuration errors (missing files, wrong project) without traceback;
        # any other error is raised with its full traceback
        except (ProjectError, FileNotFoundError, json.JSONDecodeError) as e:
            sys.exit(f"cassy: error: {e}")
        print(f"Assessment completed. Results in {root}")


if __name__ == "__main__":
    main()
