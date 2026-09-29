# Installation

## User Installation
The procedure to install cassy is the following:

1) Create a new environment. If you are using anaconda as python package manager you can do this with:

``` bash
conda create -n cassy python=3.12
```

2) Activate the newly created python environment. If you are using anaconda:

```bash
conda activate cassy
```

2) Install the cassy package from PyPi

```bash
pip install cassy-f4e
```

If cassy is already installed and you simply want to update it to the latest release
you can use

```bash
pip install --upgrade cassy-f4e
```

## Developer installation

To perform a developer installation, follow the same step 1) and 2) of the 
User installation then clone the GitHub repository into a folder of your choice.
Move into the chosen folder and type:

```bash
git clone https://github.com/Fusion4Energy/CASSY.git
```


After the repository has been cloned, perform an "editable" installation:

```bash
pip install -e .[dev]
```

the flag ``-e`` tells pip that this is an editable installation. This means
that the code of the package is not stored in the manager folders but a link
is created with the cloned repository instead. Changing the code in the repo
(i.e. modifications or switching branches) will change the behaviour of the
package in real time.
The ``[dev]`` tells pip to install some additional dependencies that are
useful for development purposes such as ``pytest`` or ``ruff``.

If you have VS code you can download the GitLab extension, authenticate, and later clone repository from the F4E gitlab like you would from GitHub.

## Contributing to the doc

The doc is automatically built using the ``zensical`` package. Documentation text is written in markdown
format and it is stored under the ``docs/`` folder. While editing the documentation, a live preview can be activated at a localhost address running

```
python -m zensical serve
```

The doc will be updated in real time every time a file is saved.