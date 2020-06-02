#!/usr/bin/env ash

set -u # nounset
set -o pipefail

# Print the ansible version
ansible --version

# Print the awscli version
aws --version

# Print the terraform version
terraform version

# Run the CMD, otherwise open an ash shell
if [ $# -eq 0 ]; then
  /usr/bin/env ash
else
  $@
fi

