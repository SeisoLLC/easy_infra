#!/usr/bin/env bash

# Color code lookups
# shellcheck disable=SC2034
ERROR='\033[0;31m'
WARNING='\033[0;33m'
DEBUGGING='\033[0;36m'
INFORMATIONAL='\033[0m'
DEFAULT='\033[0m'


function _log() {
  # Log fields, pulled from ECS
  # (https://www.elastic.co/guide/en/ecs/1.11/ecs-field-reference.html)
  timestamp="\"$(date --iso-8601=seconds --utc)\"" # @timestamp
  container_image_name='"easy_infra"' # container.image.name
  container_image_tag="[\"${EASY_INFRA_VERSION}\"]" # container.image.tag
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
  label_cwd="\"${5}\""
  message_type="${6}"
  if [[ "${message_type}" == "string" ]]; then
    message="$(jq -R <<< "${7}")" # message (JSON-escaped string)
  elif [[ "${message_type}" == "json" ]]; then
    message="${7}" # message (JSON)
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

  sleep .2 # Delay to give fluent-bit time to send the logs before container shutdown
}


function _feedback() {
  # Use the provided color code label
  color="${1}"
  case "${1}" in
    ERROR)
      # echo to stderr with the appropriate coloring
      >&2 echo -e "${!color}${1}:  ${2}${DEFAULT}" ;;
    WARNING)
      # echo to stderr with the appropriate coloring
      >&2 echo -e "${!color}${1}:  ${2}${DEFAULT}" ;;
    *)
      if [[ "${1}" != "DEBUGGING" ]]; then
        # echo to stdout with the appropriate coloring
        echo -e "${!color}${1}:  ${2}${DEFAULT}"
      elif [[ "${LOG_LEVEL}" == "DEBUG" && "${1}" == "DEBUGGING" ]]; then
        # echo to stdout with the appropriate coloring
        echo -e "${!color}${1}:  ${2}${DEFAULT}"
      fi ;;
  esac
}
