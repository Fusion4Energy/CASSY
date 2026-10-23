import os
import shutil

from cassy.auxiliary.types import PathLike

# simplified geometries of the trace reports (see cassy.office.geometry_view), kept
# between runs and shared by the people running the assessment in the same folder
STL_CACHE_FOLDER = "_cached_stl"


def stl_cache_folder(root: PathLike) -> str:
    """Folder of the simplified geometries in the output root folder ``root``."""
    return os.path.join(root, STL_CACHE_FOLDER)


class FolderTree:
    def __init__(self, root: PathLike) -> None:
        """Output folder structure of an assessment.

        Parameters
        ----------
        root : PathLike
            The root directory where the outputs will be written.
        """
        self.assessment_folder = os.path.join(root, "assessment")
        self.out_word = os.path.join(root, "Recap.docx")
        self.stl_cache = stl_cache_folder(root)

        # Free up the assessment folder
        if os.path.exists(self.assessment_folder):
            shutil.rmtree(self.assessment_folder)
        os.makedirs(self.assessment_folder)
