import os
from argparse import ArgumentParser

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
        "--recap",
        help="print the complete recap assessment in word and excel",
        action="store_true",
        default=True,
    )
    args = parser.parse_args()

    if args.assess == "bolts":
        run_bolts(args.root, args.fatigue, matlib=args.matlib, print_recap=args.recap)
    elif args.assess == "paths":
        run_paths(args.root, args.fatigue, matlib=args.matlib, print_recap=args.recap)
    else:
        raise ValueError(
            "Assessment type not recognized, please choose between bolts and paths"
        )


if __name__ == "__main__":
    main()
