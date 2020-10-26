#!/usr/bin/env bash

# Intentionally not setting errexit to allow list constructs[1] in the docker run
# 1:  https://www.tldp.org/LDP/abs/html/list-cons.html

set -o nounset
set -o pipefail

if [ $# -eq 0 ]; then
  # Print select tool versions then open an bash shell
  echo -en "aws-cli\t\t" && command aws --version | awk -F' ' '{print $1}' | awk -F'/' '{print $2}'
  echo -en "azure-cli\t" && command az version | jq -r '.["azure-cli"]'
  echo -en "terraform\t" && command terraform version | head -1 | awk -F' ' '{print $2}' | sed 's/^v//'
  echo -en "packer\t\t"  && command packer --version
  echo -en "ansible\t\t" && command ansible --version | head -1 | awk -F' ' '{print $2}'

  exec bash
else
  "$@"
fi

