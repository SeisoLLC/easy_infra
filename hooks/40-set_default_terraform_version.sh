#!/usr/bin/env bash
# register_hook: terraform

# All private functions (start with _) come from here
# shellcheck disable=SC1091
source /usr/local/bin/common.sh

fully_qualified_script=$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )

current_version=$(cat /home/easy_infra/.tfenv/version)

if [[ "${TERRAFORM_VERSION}" == "${current_version}" ]]; then
  exit 0
fi

# TERRAFORM_VERSION is not the installed and active version; make it so
tfenv install "${TERRAFORM_VERSION}" &>/dev/null
return=$?
if [[ "${return}" != 0 ]]; then
  message="Unable to install Terraform ${TERRAFORM_VERSION}, continuing to use version ${current_version}..."
  _feedback WARNING "${message}"
  # shellcheck disable=SC2154 # dir is exported in the parent process, see functions.j2
  _log "easy_infra.hook" info failure "${fully_qualified_script}" "${dir}" string "${message}"
  exit 0
fi

_feedback INFORMATIONAL "Switching Terraform version to ${TERRAFORM_VERSION}..."
tfenv use "${TERRAFORM_VERSION}" &>/dev/null
exit $?
