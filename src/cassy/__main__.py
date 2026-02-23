import os
from argparse import ArgumentParser

from cassy.auxiliary.init_folders import init_bolts_assessment, init_paths_assessment
from cassy.runners.run_bolts import run_bolts
from cassy.runners.run_paths import run_paths


def main():
    parser = ArgumentParser(description="CASSY")
    parser.add_argument(
        "--fatigue", help="Assess also fatigue", action="store_true", default=False
    )
    parser.add_argument(
        "--assess",
        help="chose type of assessment",
        choices=["bolts", "paths"],
        default="paths",
    )
    parser.add_argument(
        "--root", help="Root folder, by default CWD", default=os.getcwd()
    )
    parser.add_argument(
        "--matlib", help="Path to material library", default=None
    )  # Replace with actual version
    parser.add_argument(
        "--norecap",
        help="print the complete recap assessment in word and excel",
        default=False,
        action="store_true",
    )
    parser.add_argument(
        "--nomerge",
        help="Skip merging the tables in the Word document (faster)",
        default=True,
        action="store_false",
    )
    parser.add_argument(
        "--init",
        help="Initialize the assessment paths",
        choices=["bolts", "paths"],
        default=None,
    )
    args = parser.parse_args()
    print_recap = not args.norecap

    if args.init is not None:
        if args.init == "bolts":
            init_bolts_assessment(args.root)
        elif args.init == "paths":
            init_paths_assessment(args.root)
    elif args.assess == "bolts":
        run_bolts(
            args.root,
            args.fatigue,
            matlib=args.matlib,
            print_recap=print_recap,
            merge=args.nomerge,
        )
    elif args.assess == "paths":
        run_paths(args.root, args.fatigue, matlib=args.matlib, print_recap=print_recap)
    else:
        raise ValueError(
            "Assessment type not recognized, please choose between bolts and paths"
        )


if __name__ == "__main__":
    main()
