import os
from pathlib import Path
from typing import Union

# Create a custom type
PathLike = Union[str, os.PathLike, Path]
