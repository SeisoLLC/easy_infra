#!/usr/bin/env bash

# Intentionally not setting errexit to allow list constructs[1] in the docker run
# 1:  https://www.tldp.org/LDP/abs/html/list-cons.html

set -o nounset
set -o pipefail

if [ "$#" -eq 0 ]; then
  # Print select tool versions then open an bash shell
  echo -en "terraform\t" && command terraform version | head -1 | awk -F' ' '{print $2}' | sed 's/^v//'
  echo -en "packer\t\t"  && command packer --version
  echo -en "ansible\t\t" && command ansible --version | head -1 | awk -F' ' '{print $2}'

  exec bash
else
  "$@" # `exec` calls `execve()` which takes a `pathname` which "must be either
       # a binary executable, or a script starting with a line of the form". This
       # approach ensures the functions set via BASH_ENV are correctly sourced.
       # https://man7.org/linux/man-pages/man2/execve.2.html#DESCRIPTION
       # https://git.savannah.gnu.org/cgit/bash.git/tree/builtins/exec.def
fi

