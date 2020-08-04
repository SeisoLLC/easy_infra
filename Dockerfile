ARG FROM_IMAGE=ubuntu
ARG FROM_IMAGE_TAG=20.04

FROM "${FROM_IMAGE}":"${FROM_IMAGE_TAG}"

ARG VERSION

LABEL MAINTAINER="Seiso"
LABEL AUTHOR="Jon Zeolla"
LABEL COPYRIGHT="(c) 2020 Seiso, LLC"
LABEL LICENSE="BSD-3-Clause"
LABEL VERSION="${VERSION}"

# apt-get installs
ARG ANSIBLE_VERSION="2.9.6+dfsg-1"
ARG AZURE_CLI_VERSION="2.9.1-1~focal"
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && \
    apt-get -y install --no-install-recommends ca-certificates \
                                               curl \
                                               apt-transport-https \
                                               lsb-release \
                                               sudo \
                                               gnupg && \
    curl -sS https://dl.yarnpkg.com/debian/pubkey.gpg | apt-key add - && \
    echo "deb https://dl.yarnpkg.com/debian/ stable main" | sudo tee /etc/apt/sources.list.d/yarn.list > /dev/null && \
    curl -sL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null && \
    AZ_REPO=$(lsb_release -cs) && \
    echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $AZ_REPO main" | sudo tee /etc/apt/sources.list.d/azure-cli.list && \
    apt-get update && \
    apt-get -y install --no-install-recommends ansible=${ANSIBLE_VERSION} \
                                               azure-cli=${AZURE_CLI_VERSION} \
                                               git \
                                               jq \
                                               nodejs \
                                               python3 \
                                               python3-pip \
                                               unzip \
                                               yarn
# No cleanup due to /etc/apt/apt.conf.d/docker-clean in ubuntu:20.04

# binary downloads
ARG TFSEC_VERSION="v0.24.1"
ARG PACKER_VERSION="v1.6.1"
RUN curl -L https://github.com/liamg/tfsec/releases/download/${TFSEC_VERSION}/tfsec-linux-amd64 -o /usr/local/bin/tfsec && \
    chmod 0755 /usr/local/bin/tfsec && \
    curl -L https://releases.hashicorp.com/packer/${PACKER_VERSION#v}/packer_${PACKER_VERSION#v}_linux_amd64.zip -o /usr/local/bin/packer.zip && \
    unzip /usr/local/bin/packer.zip -d /usr/local/bin/ && \
    chmod 0755 /usr/local/bin/packer

# git installs
ARG TERRAFORM_VERSION="0.12.29"
ARG TFENV_VERSION="v2.0.0"
ENV PATH="/root/.tfenv/bin:${PATH}"
RUN git clone https://github.com/tfutils/tfenv.git ~/.tfenv && \
    echo 'PATH=/root/.tfenv/bin:${PATH}' >> ~/.bashrc && \
    . ~/.bashrc && \
    cd ~/.tfenv && \
    git checkout ${TFENV_VERSION} && \
    tfenv install ${TERRAFORM_VERSION} && \
    tfenv use ${TERRAFORM_VERSION}

# yarn adds
ARG MERMAID_VERSION="8.6.4"
ARG MERMAID_CLI_VERSION="8.6.4"
ENV PATH="/node_modules/.bin/:${PATH}"
RUN yarn add mermaid@${MERMAID_VERSION} \
             @mermaid-js/mermaid-cli@${MERMAID_CLI_VERSION}

# pip installs
COPY awscli.txt .
ENV PATH="/root/.local/bin:${PATH}"
RUN python3 -m pip install --upgrade pip && \
    pip install --user -r awscli.txt

# setup functions
COPY functions /functions
ENV BASH_ENV=/functions
RUN echo 'source ${BASH_ENV}' >> ~/.bashrc

WORKDIR /usr/local/bin/
COPY docker-entrypoint.sh .
ENTRYPOINT ["docker-entrypoint.sh"]

