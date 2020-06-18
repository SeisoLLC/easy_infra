#!/bin/bash

set -o nounset

VALUE="true"

if [[ "${VALUE:-}" == "true" ]]; then
   echo "yo"
else
   echo "whatever"
fi

