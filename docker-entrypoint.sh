#!/usr/bin/env bash

# Intentionally not setting errexit to allow list constructs[1] in the docker run
# 1:  https://www.tldp.org/LDP/abs/html/list-cons.html

set -o pipefail
shopt -s dotglob

# The fluent-bit banner and other logs go to stderr, but warnings and errors go
# to stdout
fluent-bit -c /usr/local/etc/fluent-bit/fluent-bit.conf --verbose 2>/dev/null

if [ "$#" -eq 0 ]; then
  # Print select tool versions then open an bash shell
  if [ -x "$(which aws)" ]; then
    echo -e "aws-cli\t\t ${AWS_CLI_VERSION}"
  fi
  if [ -x "$(which az)" ]; then
    echo -e "azure-cli\t ${AZURE_CLI_VERSION}"
  fi
  if [ -x "$(which ansible)" ]; then
    echo -e "ansible\t\t ${ANSIBLE_VERSION}"
  fi
  if [ -x "$(which terraform)" ]; then
    echo -e "terraform\t ${TERRAFORM_VERSION}"
  fi
  if [ -x "$(which packer)" ]; then
    echo -e "packer\t\t ${PACKER_VERSION}"
  fi

  exec bash
else
  "$@" # `exec` calls `execve()` which takes a `pathname` which "must be either
       # a binary executable, or a script starting with a line of the form". This
       # approach ensures the functions set via BASH_ENV are correctly sourced.
       # https://man7.org/linux/man-pages/man2/execve.2.html#DESCRIPTION
       # https://git.savannah.gnu.org/cgit/bash.git/tree/builtins/exec.def
fi

