from argparse import ArgumentParser


def main():
    parser = ArgumentParser(
        description="CASSY. Assessments are configured and run from the GUIs."
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
    args = parser.parse_args()

    if args.pathsgui:
        from cassy.gui.paths_gui import main as run_paths_gui

        run_paths_gui()
    else:
        from cassy.gui.bolts_gui import main as run_bolts_gui

        run_bolts_gui()


if __name__ == "__main__":
    main()
