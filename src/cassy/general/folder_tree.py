import os
import shutil

from cassy.auxiliary.types import PathLike


class FolderTree:
    def __init__(self, root: PathLike) -> None:
        """Initialize the folder tree structure for the application.
        This sets up the necessary directories for configurations, assessments,
        images, and output files.

        Parameters
        ----------
        root : PathLike
            The root directory where the folder structure will be created.
        """
        self.configurations = os.path.join(root, "config")
        self.assessment_folder = os.path.join(root, "assessment")
        self.img_folder = os.path.join(root, "images")
        self.out_word = os.path.join(root, "Recap.docx")

        # Free up the assessment folder and images folder
        if os.path.exists(self.img_folder):
            shutil.rmtree(self.img_folder)
        os.mkdir(self.img_folder)
        if os.path.exists(self.assessment_folder):
            shutil.rmtree(self.assessment_folder)
        os.mkdir(self.assessment_folder)


class PathsFolderTree(FolderTree):
    def __init__(self, root: PathLike) -> None:
        super().__init__(root)
        self.stress_tensors = os.path.join(root, "stresses")


class BoltsFolderTree(FolderTree):
    def __init__(self, root: PathLike) -> None:
        super().__init__(root)
        self.actions_folder = os.path.join(root, "actions")
        self.geom_folder = os.path.join(root, "geometries")
