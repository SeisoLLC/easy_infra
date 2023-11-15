#!/usr/bin/env bash
# register_hook: tofu

# All private functions (start with _) come from here
# shellcheck disable=SC1091
source /usr/local/bin/common.sh

fully_qualified_script=$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )
output_log="/var/log/$(basename "${BASH_SOURCE[0]%%.sh}.log")"

# The rest of this script is not relevant if AUTODETECT is not set to true
if [[ "${AUTODETECT}" != "true" ]]; then
  exit 0
fi

# TODO: Does this change?
current_version=$(cat /home/easy_infra/.tfenv/version)

# Use tfenv to get the minimum version of opentofu specified in the opentofu code (in the current directory)
opentofu_min_required="$(tfenv min-required 2>>"${output_log}")"

if [[ ! "${opentofu_min_required}" ]]; then
  message="Unable to detect the minimum required version of OpenTofu, falling back to version ${OPENTOFU_VERSION}"
  _feedback WARNING "${message}" | tee -a "${output_log}"
  # shellcheck disable=SC2154 # dir is exported in the parent process, see functions.j2
  _log "easy_infra.hook" info failure "${fully_qualified_script}" "${dir}" string "${message}"
  tfenv use "${OPENTOFU_VERSION}" &>>"${output_log}"
  exit $?
fi

if [[ "${OPENTOFU_VERSION}" == "${opentofu_min_required}" && "${OPENTOFU_VERSION}" == "${current_version}" ]]; then
  _feedback INFO "The detected minimum OpenTofu version of ${opentofu_min_required} is already installed and in use" | tee -a "${output_log}"
  exit 0
fi

## Check if the detected required version of opentofu is already installed, and if so, use it
if [[ "${OPENTOFU_VERSION}" == "${opentofu_min_required}" ]]; then
  _feedback INFO "The detected minimum OpenTofu version of ${opentofu_min_required} is already installed; ensuring it's in use..." | tee -a "${output_log}"
  tfenv use "${OPENTOFU_VERSION}" &>>"${output_log}"
  exit $?
fi

## Change versions to the detected min_required
tfenv install "${opentofu_min_required}" &>/dev/null
return=$?
if [[ "${return}" != 0 ]]; then
  message="Unable to install OpenTofu ${opentofu_min_required}, falling back to version ${OPENTOFU_VERSION}..."
  _feedback WARNING "${message}" | tee -a "${output_log}"
  # shellcheck disable=SC2154 # dir is exported in the parent process, see functions.j2
  _log "easy_infra.hook" info failure "${fully_qualified_script}" "${dir}" string "${message}"
  tfenv use "${OPENTOFU_VERSION}" &>/dev/null
  exit $?
fi

_feedback INFO "Switching OpenTofu version to ${opentofu_min_required}..." | tee -a "${output_log}"
tfenv use "${opentofu_min_required}" &>>"${output_log}"
exit $?
