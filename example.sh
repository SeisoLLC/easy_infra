#!/usr/bin/env bash

#function thing() {
#  if [[ " ${@} " =~ " b " ]]; then
#    echo matched @
#  fi
#  echo deleting b
#  stuff=( "${thing[@]/b}" )
#  if [[ " ${stuff} " =~ " b " ]]; then
#    echo matched @
#  fi
#  if [[ " ${*} " =~ " c " ]]; then
#    echo matched *
#  fi
#  echo $1
#  echo $2
#}
#
#thing "a" "b" "c" "d" "e" "f" "g"

function modify() {
  arguments=("${@}")
  for i in "${!arguments[@]}"; do
    if [[ ${arguments[i]} == b ]]; then
      unset 'arguments[i]'
    fi
  done
#  for argument in "${arguments[@]}"; do
#    if [[ $argument == b ]]; then
#      thing=("${thing[@]/b}")
#    fi
#  done
  #thing=("${thing[@]/b}")
  echo "now ${arguments[*]}"
}
modify "$@"
