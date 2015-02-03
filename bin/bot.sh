#!/bin/bash
#
# http://stackoverflow.com/questions/59895/can-a-bash-script-tell-what-directory-its-stored-in
# http://stackoverflow.com/questions/3811345/how-to-pass-all-arguments-passed-to-my-bash-script-to-a-function-of-mine
#
subdir=$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )
PYTHONPATH="$subdir/.." "$subdir/bot.py" "$@"
