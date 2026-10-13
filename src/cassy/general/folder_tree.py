import os
import shutil

from cassy.auxiliary.types import PathLike


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

        # Free up the assessment folder
        if os.path.exists(self.assessment_folder):
            shutil.rmtree(self.assessment_folder)
        os.makedirs(self.assessment_folder)
