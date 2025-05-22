import os
import shutil

from cassy.auxiliary.types import PathLike


class FolderTree:
    def __init__(self, root: PathLike) -> None:
        self.configurations = os.path.join(root, "Configurations")
        self.assessment_folder = os.path.join(root, "Assessment")
        self.img_folder = os.path.join(root, "Images")
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
        self.stress_tensors = os.path.join(root, "Stresses")


class BoltsFolderTree(FolderTree):
    def __init__(self, root: PathLike) -> None:
        super().__init__(root)
        self.actions_folder = os.path.join(root, "Actions")
