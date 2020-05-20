ARG FROM_IMAGE=alpine
ARG FROM_IMAGE_TAG=3

FROM "${FROM_IMAGE}":"${FROM_IMAGE_TAG}"

ARG VERSION

LABEL MAINTAINER="Seiso"
LABEL AUTHOR="Jon Zeolla"
LABEL COPYRIGHT="(c) 2020 Seiso, LLC"
LABEL LICENSE="BSD-3-Clause"
LABEL VERSION=${VERSION}

ARG ANSIBLE_VERSION="2.9.7-r0"
ARG TERRAFORM_VERSION="0.12.17-r1"

RUN apk add ansible=${ANSIBLE_VERSION} && \
  terraform=${TERRAFORM_VERSION}

ENTRYPOINT ["ansible-playbook"]

