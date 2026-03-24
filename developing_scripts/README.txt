N.B.: It is strongly recommended to use Docker in most stages of development (and production of course), these scripts are still featured in the repo to enable development and mantainability in the edge cases when Docker is not available.

All the scripts in this folder are meant to be used in conjuction with the servers running with Flask built-in server using the run function (it is required that both the relative *_DEBUG_MODE settings in the env file(s) are set to True).
These scripts are meant to be used to comfortably startup and shutdown the architecture while in the developing or testing phase, in real production the servers will be running with waitress.
To simulate the servers behaviour while using waitress check out the production_scripts folder.