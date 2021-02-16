#!/usr/bin/env bash

# Intentionally not setting errexit to allow list constructs[1] in the docker run
# 1:  https://www.tldp.org/LDP/abs/html/list-cons.html

set -o pipefail

if [ "$#" -eq 0 ]; then
  # Print select tool versions then open an bash shell
  if [ -x "$(which aws)" ]; then
    echo -e "aws-cli\t\t $(command aws --version | awk -F' ' '{print $1}' | awk -F'/' '{print $2}')" &
  fi
  if [ -x "$(which az)" ]; then
    echo -e "azure-cli\t $(command az version | jq -r '.["azure-cli"]')" &
  fi
  echo -e "terraform\t $(command terraform version | head -1 | awk -F' ' '{print $2}' | sed 's/^v//')" &
  echo -e "packer\t\t $(command packer --version)" &
  echo -e "ansible\t\t $(command ansible --version | head -1 | awk -F' ' '{print $2}')" &
  wait

  exec bash
else
  "$@" # `exec` calls `execve()` which takes a `pathname` which "must be either
       # a binary executable, or a script starting with a line of the form". This
       # approach ensures the functions set via BASH_ENV are correctly sourced.
       # https://man7.org/linux/man-pages/man2/execve.2.html#DESCRIPTION
       # https://git.savannah.gnu.org/cgit/bash.git/tree/builtins/exec.def
fi

