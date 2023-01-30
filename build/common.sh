#!/usr/bin/env bash

# Color code lookups
# shellcheck disable=SC2034
ERROR='\033[0;31m'
WARNING='\033[0;33m'
DEBUGGING='\033[0;36m'
INFO='\033[0m'
DEFAULT='\033[0m'


function _log() {
  # Log fields, pulled from ECS
  # (https://www.elastic.co/guide/en/ecs/1.11/ecs-field-reference.html)
  timestamp="\"$(date --iso-8601=seconds --utc)\"" # @timestamp
  container_image_name='"seiso/easy_infra"' # container.image.name
  container_image_tag="[\"${EASY_INFRA_TAG}\"]" # container.image.tag
  ecs_version='"1.11"' # ecs.version
  event_kind='"state"' # event.kind
  event_category='"configuration"' # event.category
  event_provider='"easy_infra"' # event.provider
  git_labels="$(git rev-parse --is-inside-work-tree 2>/dev/null)"
  if [[ "${git_labels}" == "true" ]]; then
    git_labels_git_branch_name="\"$(git branch --show-current)\""
    git_labels_git_branch_ref="\"$(git rev-parse HEAD)\""
    git_labels_git_remote_origin_url="\"$(git config --get remote.origin.url)\""
  fi

  event_dataset="\"${1}\"" # event.dataset
  event_type="\"${2}\"" # event.type
  event_outcome="\"${3}\"" # event.outcome
  event_action="$(jq -R <<< "${4}")" # event.action (JSON-escaped string)
  # If $5 is already double quoted, don't double quote it again
  if [[ "${5}" == \"*\" ]]; then
    label_cwd="${5}"
  else
    label_cwd="\"${5}\""
  fi
  message_type="${6}"
  if [[ "${message_type}" == "string" ]]; then
    message="$(jq -R <<< "${7}")" # message (JSON-escaped string)
  elif [[ "${message_type}" == "json" ]]; then
    message="${7}" # message (JSON)
  else
    _feedback ERROR "Incorrect message type of ${message_type:-null or unset} sent to the _log function"
    exit 230
  fi

  # Validation
  # Note: This technically is a deviation from ECS.  denied and allowed are not
  # valid event types for an event category of configuration.  See
  # https://www.elastic.co/guide/en/ecs/1.11/ecs-allowed-values-event-category.html#ecs-event-category-configuration
  if [[ "${event_type}" != '"denied"' && "${event_type}" != '"allowed"' && "${event_type}" != '"info"' ]]; then
    _feedback ERROR "Incorrect event.type of ${event_type} sent to the _log function"
    exit 230
  elif [[ "${event_outcome}" != '"failure"' && "${event_outcome}" != '"success"' && "${event_outcome}" != '"unknown"' ]]; then
    _feedback ERROR "Incorrect event.outcome of ${event_outcome} sent to the _log function"
    exit 230
  fi

  if [[ "${git_labels}" == "true" ]]; then
    LOG_MESSAGE=$(jq -c -n                                             \
      "{                                                               \
      \"@timestamp\": ${timestamp},                                    \
      \"container.image.name\": ${container_image_name},               \
      \"container.image.tag\": ${container_image_tag},                 \
      \"ecs.version\": ${ecs_version},                                 \
      \"event.action\": ${event_action},                               \
      \"event.category\": ${event_category},                           \
      \"event.kind\": ${event_kind},                                   \
      \"event.outcome\": ${event_outcome},                             \
      \"event.provider\": ${event_provider},                           \
      \"event.type\": ${event_type},                                   \
      \"labels\": {                                                    \
        \"cwd\": ${label_cwd},                                         \
        \"git.branch.name\": ${git_labels_git_branch_name},            \
        \"git.branch.ref\": ${git_labels_git_branch_ref},              \
        \"git.remote.origin.url\": ${git_labels_git_remote_origin_url} \
      },                                                               \
      \"message\": ${message}                                          \
      }"                                                               \
    ) || { _feedback ERROR "Failed to generate a valid JSON log message"; _log "easy_infra.stdouterr" info unknown "easy_infra" "${label_cwd}" string "Failed to generate a valid JSON log message"; }
  else
    LOG_MESSAGE=$(jq -c -n                               \
      "{                                                 \
      \"@timestamp\": ${timestamp},                      \
      \"container.image.name\": ${container_image_name}, \
      \"container.image.tag\": ${container_image_tag},   \
      \"ecs.version\": ${ecs_version},                   \
      \"event.action\": ${event_action},                 \
      \"event.category\": ${event_category},             \
      \"event.kind\": ${event_kind},                     \
      \"event.outcome\": ${event_outcome},               \
      \"event.provider\": ${event_provider},             \
      \"event.type\": ${event_type},                     \
      \"labels\": {                                      \
        \"cwd\": ${label_cwd}                            \
      },                                                 \
      \"message\": ${message}                            \
      }"                                                 \
    ) || { _feedback ERROR "Failed to generate a valid JSON log message"; _log "easy_infra.stdouterr" info unknown "easy_infra" "${label_cwd}" string "Failed to generate a valid JSON log message"; }
  fi
  echo "${LOG_MESSAGE}" &>> /var/log/easy_infra.log
}


function _feedback() {
  timestamp="$(date -Ins)"
  # Use the provided color code label
  color="${1}"
  case "${1}" in
    ERROR)
      # echo to stderr with the appropriate coloring
      >&2 echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}" ;;
    WARNING)
      # echo to stderr with the appropriate coloring
      >&2 echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}" ;;
    *)
      if [[ "${1}" != "DEBUGGING" ]]; then
        # echo to stdout with the appropriate coloring
        echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}"
      elif [[ "${LOG_LEVEL}" == "DEBUG" && "${1}" == "DEBUGGING" ]]; then
        # echo to stdout with the appropriate coloring
        echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}"
      fi ;;
  esac
}


function _clone() {
  # This function expects up to 4 positional arguments:
  # - (Required) The version control system base domain (i.e. github.com)
  # - (Required) A comma-separated list of the namespace and repository names (i.e. seisollc/easy_infra or seisollc/easy_infra,seisollc/easy_sast)
  # - (Optional) The protocol (defaults to "ssh")
  # - (Optional) The base path where the repository should be cloned (defaults to "/iac")

  local vcs_domain
  vcs_domain="${1}"
  local namespace_and_repository_list
  namespace_and_repository_list="${2}"
  local protocol
  protocol="${3:-ssh}"
  local base_clone_path
  base_clone_path="${4:-/iac}"
  local clone_error_log
  clone_error_log="/var/log/clone.err.log"

  local unique_namespace_and_repository_list
  unique_namespace_and_repository_list=$(tr ',' '\n' <<< "${namespace_and_repository_list}" | sort -u | tr '\n' ',' | sed 's/,$//')
  IFS=',' read -r -a namespaces_and_repositories <<< "${unique_namespace_and_repository_list}"
  local message

  if [[ ! -d "${base_clone_path}" ]]; then
    # This will attempt to mkdir and if it fails it will pass the if statement, generating a failure log
    if ! mkdir -p "${base_clone_path}" &>/dev/null ; then
      message="Failed to create ${base_clone_path}"
      _feedback ERROR "${message}"
      _log "easy_infra.stdouterr" denied failure "easy_infra" "${PWD}" string "${message}"
      exit 230
    fi
  fi

  if [[ -n "$(ls -A "${base_clone_path}")" ]]; then
    _feedback WARNING "${base_clone_path} is not empty"
  fi

  for namespace_and_repository in "${namespaces_and_repositories[@]}"; do
    local clone_url
    if [[ "${protocol}" == "ssh" ]]; then
      clone_url="git@${vcs_domain}:${namespace_and_repository}.git"
    elif [[ "${protocol}" == "https" ]]; then
      clone_url="https://${vcs_domain}/${namespace_and_repository}"
    else
      # This validation could happen prior to the loop, but putting it here for simiplicity
      message="Invalid protocol of ${protocol} was provided to the _clone function; exiting..."
      _feedback ERROR "${message}"
      _log "easy_infra.stdouterr" denied failure "easy_infra" "${PWD}" string "${message}"
      exit 230
    fi

    local clone_destination
    clone_destination="${base_clone_path}/${namespace_and_repository}"
    local is_git_repo
    is_git_repo="false"

    local message
    if [[ -d "${clone_destination}" ]]; then
      pushd "${clone_destination}" &>/dev/null
      is_git_repo="$(git rev-parse --is-inside-work-tree)"
      popd &>/dev/null

      if [[ "${is_git_repo,,}" == "true" ]]; then
        message="The directory ${clone_destination} already exists and is a git repo, skipping..."
        _feedback "WARNING" "${message}"
        _log "easy_infra.stdouterr" info unknown "easy_infra" "${PWD}" string "${message}"
      else
        message="The directory ${clone_destination} already exists and is not a git repo; exiting..."
        _feedback "ERROR" "${message}"
        _log "easy_infra.stdouterr" info unknown "easy_infra" "${PWD}" string "${message}"
        exit 230
      fi
    else
      # If this fails, the script will continue but stderr goes into the clone error log and is analyzed later
      GIT_TERMINAL_PROMPT=0 git clone --single-branch --depth 1 --quiet "${clone_url}" "${clone_destination}" >/dev/null 2>>"${clone_error_log}" &
    fi
  done

  wait

  error_count=$(grep '^fatal:' "${clone_error_log}" | sed -n '$=' || echo 0)
  if [[ "${error_count}" -gt 0 ]]; then
    # Print the cloning errors to the screen
    cat "${clone_error_log}"

    message="Encountered ${error_count} fatal errors while cloning ${namespace_and_repository_list} repositories into ${base_clone_path} using ${protocol}"
    _feedback ERROR "${message}"
    _log "easy_infra.stdouterr" denied failure "easy_infra" "${PWD}" string "${message}"
    exit 230
  fi

  folder_count=$(find "${clone_destination}" -maxdepth 2 -mindepth 2 -type d | wc -l)
  clone_log="/var/log/clone.log"
  echo "$(date): Cloned ${folder_count} folders" >> "${clone_log}"
}
