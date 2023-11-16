#!/usr/bin/env bash
# register_hook: tofu

# All private functions (start with _) come from here
# shellcheck disable=SC1091
source /usr/local/bin/common.sh


current_version=$(cat /home/easy_infra/.tfenv/version)
output_log="/var/log/$(basename "${BASH_SOURCE[0]%%.sh}.log")"

if [[ -z "${OPENTOFU_VERSION}" ]]; then
  # OPENTOFU_VERSION is either empty or not set
  exit 0
elif [[ "${OPENTOFU_VERSION}" == "${current_version}" ]]; then
  # The OPENTOFU_VERSION is already in use
  exit 0
fi

# OPENTOFU_VERSION is not the installed and active version; make it so
tfenv install "${OPENTOFU_VERSION}" &>>"${output_log}"
return=$?
if [[ "${return}" != 0 ]]; then
  message="Unable to install OpenTofu ${OPENTOFU_VERSION}, continuing to use version ${current_version}..."
  _feedback WARNING "${message}" | tee -a "${output_log}"
  fully_qualified_script=$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )
  # shellcheck disable=SC2154 # dir is exported in the parent process, see functions.j2
  _log "easy_infra.hook" info failure "${fully_qualified_script}" "${dir}" string "${message}"
  exit 0
fi

_feedback INFO "Switching OpenTofu version to ${OPENTOFU_VERSION} due to the provided OPENTOFU_VERSION environment variable..." | tee -a "${output_log}"
tfenv use "${OPENTOFU_VERSION}" &>>"${output_log}"
exit $?
