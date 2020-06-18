#!/usr/bin/env bash

set -u # nounset
set -e # errexit
set -E # errtrap
set -o pipefail

function help() {
  exitCode="${1:-0}"
  # Purposefully using tabs for the HEREDOC
  cat <<- HEREDOC
		Preferred Usage: ./${0##*/} [--repo=REPO | --package=PACKAGE] [--version=VERSION]

		--repo           The repo name
		--package        The package name
		--version        The exact version
		-h|--help        Usage details
	HEREDOC

  exit "${exitCode}"
}

function clean() {
  local INPUT="$1"

  # Trim the longest match of */
  INPUT="${INPUT##*/}"

  # Translate to uppercase because global variables
  INPUT=$(echo "${INPUT}" | tr '[:lower:]' '[:upper:]')

  # Convert `-`s to `_`s
  INPUT="${INPUT//-/_}"

  # Return the cleaned input
  echo "${INPUT}"
}

OPTSPEC=":h-:"
REPO=
PACKAGE=
VERSION=

while getopts "${OPTSPEC}" optchar; do
  case "${optchar}" in
    -)
      case "${OPTARG}" in
        help)
          help ;;

        package)
          PACKAGE="${!OPTIND}"; OPTIND=$(( OPTIND + 1 )) ;;

        package=*)
          PACKAGE=${OPTARG#*=} ;;

        repo)
          REPO="${!OPTIND}"; OPTIND=$(( OPTIND + 1 )) ;;

        repo=*)
          REPO=${OPTARG#*=} ;;

        version)
          VERSION="${!OPTIND}"; OPTIND=$(( OPTIND + 1 )) ;;

        version=*)
          VERSION="${OPTARG#*=}" ;;

        *)
          if [ "${OPTERR}" = 1 ] && [ "${OPTSPEC:0:1}" != ":" ]; then
            echo "Invalid argument: --${OPTARG}" >&2
            help 64
          fi
          ;;
      esac
      ;;

    h)
      help
      ;;

    *)
      if [ "${OPTERR}" != 1 ] || [ "${OPTSPEC:0:1}" = ":" ]; then
        echo "Invalid argument: -${OPTARG}" >&2
        help 64
      fi
  esac
done

# either (--repo or --package) and --version is required
if [[ ( -n "${PACKAGE}" && -n "${REPO}" ) || -z "${VERSION}" ]]; then
  help 64
# --repo and --package are mutually exclusive
elif [[ -z "${PACKAGE}" && -z "${REPO}" ]]; then
  help 64
fi

if [[ -n "${PACKAGE}" ]]; then
  PACKAGE=$(clean "${PACKAGE}")

  # Apply the final result
  sed -i '' "s/\(ARG ${PACKAGE}_VERSION=\"\).*/\1${VERSION}\"/" Dockerfile
elif [[ -n "${REPO}" ]]; then
  REPO=$(clean "${REPO}")

  # Apply the final result
  sed -i '' "s/\(ARG ${REPO}_VERSION=\"\).*/\1${VERSION}\"/" Dockerfile
fi

