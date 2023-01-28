#!/usr/bin/env bash

# Color code lookups
# shellcheck disable=SC2034
ERROR='\033[0;31m'
WARNING='\033[0;33m'
DEBUGGING='\033[0;36m'
INFO='\033[0m'
DEFAULT='\033[0m'


function _log() {
  # This function expects 7 positional arguments:
  # - A event.dataset (see ECS)
  # - A event.type (see ECS)
  # - A event.outcome (see ECS)
  # - A event.action (see ECS)
  # - The directory context for the log
  # - A message type (json or string) describing the contents of the message
  # - A message, which can be a file path inside the container, or a string

  # Log fields, pulled from ECS
  # (https://www.elastic.co/guide/en/ecs/1.11/ecs-field-reference.html)
  local timestamp
  timestamp="\"$(date --iso-8601=seconds --utc)\"" # @timestamp
  local container_image_name
  container_image_name='"seiso/easy_infra"' # container.image.name
  local container_image_tag
  container_image_tag="[\"${EASY_INFRA_TAG}\"]" # container.image.tag
  local ecs_version
  ecs_version='"1.11"' # ecs.version
  local event_kind
  event_kind='"state"' # event.kind
  local event_category
  event_category='"configuration"' # event.category
  local event_provider
  event_provider='"easy_infra"' # event.provider
  local git_labels
  git_labels="$(git rev-parse --is-inside-work-tree 2>/dev/null)"

  if [[ "${git_labels}" == "true" ]]; then
    local git_labels_git_branch_name
    git_labels_git_branch_name="\"$(git branch --show-current)\""
    local git_labels_git_branch_ref
    git_labels_git_branch_ref="\"$(git rev-parse HEAD)\""
    local git_labels_git_remote_origin_url
    git_labels_git_remote_origin_url="\"$(git config --get remote.origin.url)\""
  fi

  local event_dataset
  event_dataset="\"${1}\"" # event.dataset
  local event_type
  event_type="\"${2}\"" # event.type
  local event_outcome
  event_outcome="\"${3}\"" # event.outcome
  local event_action
  event_action="$(jq -R <<< "${4}")" # event.action (JSON-escaped string)

  # If $5 is already double quoted, don't double quote it again
  local label_cwd
  if [[ "${5}" == \"*\" ]]; then
    label_cwd="${5}"
  else
    label_cwd="\"${5}\""
  fi

  local message_type
  message_type="${6}"
  local message_file_or_string
  message_file_or_string="${7}"

  local message

  if [[ ! -r "${message_file_or_string}" ]]; then
    # _log was provided a raw string, not a file
    _feedback DEBUGGING "_log was not provided a readable file; we assume it is a string and will escape the JSON special characters..."
    message="$(jq --raw-input <<< "${message_file_or_string}")"
  elif [[ "${message_type}" == "string" ]]; then
    message_file="${message_file_or_string}"
    # The provided file contains non-JSON strings; put it all on one line and escape the JSON special characters
    message="$(jq --raw-input < <(tr '\n' '\t' < "${message_file}"))"
  elif [[ "${message_type}" == "json" ]]; then
    message_file="${message_file_or_string}"
    # The provided file should contain valid JSON (validation must occur prior to writing it to the final log location)
    message="$(cat "${message_file}")"
  else
    _feedback ERROR "Incorrect message type of ${message_type:-null or unset} sent to the _log function"
    exit 1
  fi

  # Validation
  # Note: This technically is a deviation from ECS.  denied and allowed are not
  # valid event types for an event category of configuration.  See
  # https://www.elastic.co/guide/en/ecs/1.11/ecs-allowed-values-event-category.html#ecs-event-category-configuration
  if [[ "${event_type}" != '"denied"' && "${event_type}" != '"allowed"' && "${event_type}" != '"info"' ]]; then
    _feedback ERROR "Incorrect event.type of ${event_type} sent to the _log function"
    exit 1
  elif [[ "${event_outcome}" != '"failure"' && "${event_outcome}" != '"success"' && "${event_outcome}" != '"unknown"' ]]; then
    _feedback ERROR "Incorrect event.outcome of ${event_outcome} sent to the _log function"
    exit 1
  fi

  # Begin constructing the log
  local temporary_log
  temporary_log="/tmp/easy_infra.log.tmp"

  local log_header
  log_header="{                                                    \
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
    \"cwd\": ${label_cwd}"

  if [[ "${git_labels}" == "true" ]]; then
    log_header="${log_header},                                       \
      \"git.branch.name\": ${git_labels_git_branch_name},            \
      \"git.branch.ref\": ${git_labels_git_branch_ref},              \
      \"git.remote.origin.url\": ${git_labels_git_remote_origin_url} \
    },"
  else
    log_header="${log_header}},"
  fi

  log_header="${log_header}\"message\":"
  local log_trailer
  log_trailer="}"

  local one_line_log
  one_line_log="${log_header} ${message} ${log_trailer}"

  # This adds a newline to the end of the one line log and write it out
  echo "${one_line_log}" > "${temporary_log}"

  # Validate the log using jq
  if jq empty "${temporary_log}" &>/dev/null ; then
    # Ensure that the temporary log is all on one line
    jq -c < "${temporary_log}" &>> /var/log/easy_infra.log
  else
    _feedback ERROR "Failed to generate a valid JSON log message"
    _log "easy_infra.stdouterr" info unknown "easy_infra" "${label_cwd}" string "Failed to generate a valid JSON log message"
  fi
}


function _feedback() {
  local timestamp
  timestamp="$(date --iso-8601=seconds --utc)"
  # Use the provided color code label
  local color
  color="${1}"
  case "${1}" in
    ERROR)
      >&2 echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}" ;;
    WARNING)
      >&2 echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}" ;;
    *)
      if [[ "${1}" != "DEBUGGING" ]]; then
        echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}"
      elif [[ "${LOG_LEVEL}" == "DEBUG" && "${1}" == "DEBUGGING" ]]; then
        echo -e "${!color}${timestamp} - ${1}:  ${2}${DEFAULT}"
      fi ;;
  esac
}
