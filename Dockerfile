ARG FROM_IMAGE=ubuntu
ARG FROM_IMAGE_TAG=20.04

FROM "${FROM_IMAGE}":"${FROM_IMAGE_TAG}" as base

ARG VERSION
ARG COMMIT_HASH

LABEL org.opencontainers.image.authors="Jon Zeolla"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"
LABEL org.opencontainers.image.vendor="Seiso"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.title="easy_infra"
LABEL org.opencontainers.image.description="This is a docker container that simplifies and secures Infrastructure as Code deployments"
LABEL org.opencontainers.image.url="https://seisollc.com"
LABEL org.opencontainers.image.source="https://github.com/SeisoLLC/easy_infra"
LABEL org.opencontainers.image.revision="${COMMIT_HASH}"

# apt-get installs
ARG ANSIBLE_VERSION="2.9.6+dfsg-1"
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update \
 && apt-get -y install --no-install-recommends ansible=${ANSIBLE_VERSION} \
                                               bsdmainutils \
                                               ca-certificates \
                                               curl \
                                               git \
                                               groff \
                                               jq \
                                               less \
                                               nodejs \
                                               python3 \
                                               python3-pip \
                                               sudo \
                                               time \
                                               unzip \
 && apt-get clean autoclean \
 && apt-get -y autoremove \
 && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*

# binary downloads
ARG TFSEC_VERSION="v0.30.1"
ARG PACKER_VERSION="v1.6.4"
RUN curl -L https://github.com/liamg/tfsec/releases/download/${TFSEC_VERSION}/tfsec-linux-amd64 -o /usr/local/bin/tfsec \
 && chmod 0755 /usr/local/bin/tfsec \
 && curl -L https://releases.hashicorp.com/packer/${PACKER_VERSION#v}/packer_${PACKER_VERSION#v}_linux_amd64.zip -o /usr/local/bin/packer.zip \
 && unzip /usr/local/bin/packer.zip -d /usr/local/bin/ \
 && rm -f /usr/local/bin/packer.zip \
 && chmod 0755 /usr/local/bin/packer

# git installs
ARG TERRAFORM_VERSION="0.13.4"
ARG TFENV_VERSION="v2.0.0"
COPY .terraformrc /root/
ENV PATH="/root/.tfenv/bin:${PATH}"
RUN git clone https://github.com/tfutils/tfenv.git ~/.tfenv \
 && echo 'PATH=/root/.tfenv/bin:${PATH}' >> ~/.bashrc \
 && . ~/.bashrc \
 && cd ~/.tfenv \
 && git checkout ${TFENV_VERSION} \
 && mkdir -p ~/.terraform.d/plugin-cache \
 && tfenv install ${TERRAFORM_VERSION} \
 && tfenv use ${TERRAFORM_VERSION} \
 && rm -rf ~/.tfenv/.git \
 && command terraform -install-autocomplete

# pip installs
COPY checkov.txt ./
ENV PATH="/root/.local/bin:${PATH}"
RUN python3 -m pip install --upgrade --no-cache-dir pip \
 && pip install --user --no-cache-dir -r checkov.txt

# setup functions
COPY functions /functions
ENV BASH_ENV=/functions
RUN echo 'source ${BASH_ENV}' >> ~/.bashrc

WORKDIR /iac
COPY docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

FROM base as az
ARG AZURE_CLI_VERSION="2.12.1-1~focal"
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update \
 #####
 # Per Microsoft recommendation at https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt
 && sudo apt remove azure-cli -y \
 && sudo apt autoremove -y \
 #####
 && apt-get -y install --no-install-recommends ca-certificates \
                                               curl \
                                               apt-transport-https \
                                               lsb-release \
                                               gnupg \
 && curl -sL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null \
 && AZ_REPO=$(lsb_release -cs) \
 && echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $AZ_REPO main" | sudo tee /etc/apt/sources.list.d/azure-cli.list \
 && apt-get update \
 && apt-get -y install --no-install-recommends azure-cli=${AZURE_CLI_VERSION} \
 && apt-get clean autoclean \
 && apt-get -y autoremove \
 && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*

FROM base as aws
# pip installs
COPY awscli.txt ./
RUN python3 -m pip install --upgrade --no-cache-dir pip \
 && pip install --user --no-cache-dir -r awscli.txt

# Add aws autocomplete
RUN echo 'complete -C /root/.local/bin/aws_completer aws' >> ~/.bashrc

from base as final

# AWS
COPY --from=aws /root/.local /root/.local

# Azure
COPY --from=az /opt/az /opt/az
COPY --from=az /usr/bin/az /usr/bin/az
COPY --from=az /etc/apt/sources.list.d/azure-cli.list /etc/apt/sources.list.d/azure-cli.list
