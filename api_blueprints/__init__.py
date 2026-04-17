"""
This module is responsible for exposing all the blueprints in the current
directory (api_blueprints) so that they can be easily imported in the main
script (api_server.py) and used as blueprints.
"""

from os.path import dirname as os_path_dirname
from os import listdir as os_listdir

# Script that through the __all__ variable exposes all the modules
# in the current directory in the directory (made a package by this __init__.py file)
# so that they can be easily imported in the main script (api_server.py) and used as blueprints.

__all__ = []
current_dir = os_path_dirname(__file__)
for file in os_listdir(current_dir):
    if file.endswith(".py") and file != "__init__.py" and file != "blueprints_utils.py":
        module_name = file[:-3]
        if module_name + "_bp" not in __all__:
            __all__.append(module_name)
