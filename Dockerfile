ARG FROM_IMAGE=alpine
ARG FROM_IMAGE_TAG=3

FROM "${FROM_IMAGE}":"${FROM_IMAGE_TAG}"

ARG VERSION

LABEL MAINTAINER="Seiso"
LABEL AUTHOR="Jon Zeolla"
LABEL COPYRIGHT="(c) 2020 Seiso, LLC"
LABEL LICENSE="BSD-3-Clause"
LABEL VERSION=${VERSION}

# apk adds
ARG ANSIBLE_VERSION="2.9.9-r0"
ARG TERRAFORM_VERSION="0.12.25-r0"
RUN apk add --no-cache ansible=${ANSIBLE_VERSION} \
                       terraform=${TERRAFORM_VERSION} && \
    apk add --no-cache --update jq \
                                python3 \
                                py3-pip \
                                yarn

# pip installs
COPY awscli.txt .
ENV PATH="/root/.local/bin:${PATH}"
RUN python3 -m pip install --upgrade pip && \
    pip3 install --user -r awscli.txt

# yarn adds
ARG MERMAID_VERSION="8.5.1"
ARG MERMAID_CLI_VERSION="8.5.1-2"
ENV PATH="/node_modules/.bin/:${PATH}"
RUN yarn add mermaid@${MERMAID_VERSION} \
             @mermaid-js/mermaid-cli@${MERMAID_CLI_VERSION}

COPY entrypoint.sh .
ENTRYPOINT ["./entrypoint.sh"]

