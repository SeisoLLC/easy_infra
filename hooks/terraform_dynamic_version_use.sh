#!/usr/bin/env bash
# register_hook: terraform

# All private functions (start with _) come from here
source /usr/local/bin/common.sh

# This script is not relevant if AUTODETECT is not set to true
if [[ "${AUTODETECT}" != "true" ]]; then
  exit 0
fi

# Use tfenv to get the minimum version of terraform specified in the terraform code (in the current directory)
terraform_min_required="$(tfenv min-required 2>/dev/null)"

if [[ "${terraform_min_required}" ]]; then
  terraform_version_without_patch="${TERRAFORM_VERSION%.*}"
  terraform_min_required_without_patch="${terraform_min_required%.*}"

  # The detected required major/minor version of terraform is compatible with the version installed at build time, so we'll use that
  if [[ "${terraform_min_required_without_patch}" == "${terraform_version_without_patch}" ]]; then
      _feedback INFORMATIONAL "The detected minimum Terraform version of ${terraform_min_required} is compatible with the currently installed version of ${TERRAFORM_VERSION}; using that..."
      tfenv use "${TERRAFORM_VERSION}" &>/dev/null
      exit $?
  fi

  # The detected required major/minor version of terraform is *not* compatible with the version installed at build time, so we should change versions
  terraform_min_required_latest_patch="$(tfenv list-remote | grep "^${terraform_min_required_without_patch}\." -m 1)"
  tfenv install "${terraform_min_required_latest_patch}" &>/dev/null
  return=$?
  if [[ "${return}" != 0 ]]; then
    _feedback WARNING "Unable to install a terraform version compatible with ${terraform_min_required}, falling back to ${TERRAFORM_VERSION}..."
    tfenv use "${TERRAFORM_VERSION}" &>/dev/null
    exit $?
  fi

  _feedback INFORMATIONAL "Switching Terraform version to ${terraform_min_required_latest_patch}..."
  tfenv use "${terraform_min_required_latest_patch}" &>/dev/null
  exit $?
else
  _feedback WARNING "Unable to detect the minimum required version of Terraform; using the built-in Terraform version of ${TERRAFORM_VERSION}"
  tfenv use "${TERRAFORM_VERSION}" &>/dev/null
  exit $?
fi
