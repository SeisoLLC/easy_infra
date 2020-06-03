#!/usr/bin/env bash

set -u # nounset
set -e # errexit
set -E # errtrap
set -o pipefail

function help() {
  exitCode="${1:-0}"
  # Purposefully using tabs for the HEREDOC
  cat <<- HEREDOC
		Preferred Usage: ./${0##*/} [--package=PACKAGE] [--version=VERSION]

		--package        The apk package name
		--version        The exact version
		-h|--help        Usage details
	HEREDOC

  exit "${exitCode}"
}

OPTSPEC=":h-:"
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

# --package and --version are both required
if [[ -z "${PACKAGE}" || -z "${VERSION}" ]]; then
  help 64
fi

# Translate package name to uppercase because global variables
PACKAGE=$(echo "${PACKAGE}" | tr '[:lower:]' '[:upper:]')

# Remove yarn scope and convert `-`s to `_`s
PACKAGE=$(echo "${PACKAGE}" | sed 's_@.*/__g' | sed 's/-/_/g' )

sed -i '' "s/\(ARG ${PACKAGE}_VERSION=\"\).*/\1${VERSION}\"/" Dockerfile

