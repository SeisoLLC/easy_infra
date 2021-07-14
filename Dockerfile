ARG FROM_IMAGE=ubuntu
ARG FROM_IMAGE_TAG=20.04

FROM "${FROM_IMAGE}":"${FROM_IMAGE_TAG}" AS minimal

# apt-get installs
ARG ANSIBLE_VERSION
ENV DEBIAN_FRONTEND=noninteractive
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# hadolint ignore=DL3008
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
                                               time \
                                               tini \
                                               unzip \
 && apt-get clean autoclean \
 && apt-get -y autoremove \
 && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/*

# binary downloads and user creation
ARG KICS_VERSION
ARG TFSEC_VERSION
ARG PACKER_VERSION
ARG TERRASCAN_VERSION
RUN curl -L https://github.com/checkmarx/kics/releases/download/${KICS_VERSION}/kics_${KICS_VERSION#v}_linux_x64.tar.gz -o /usr/local/bin/kics.tar.gz \
 && tar -xvf /usr/local/bin/kics.tar.gz -C /usr/local/bin/ kics \
 && rm -f /usr/local/bin/kics.tar.gz \
 && chmod 0755 /usr/local/bin/kics \
 && chown root: /usr/local/bin/kics \
 && curl -L https://github.com/liamg/tfsec/releases/download/${TFSEC_VERSION}/tfsec-linux-amd64 -o /usr/local/bin/tfsec \
 && chmod 0755 /usr/local/bin/tfsec \
 && curl -L https://releases.hashicorp.com/packer/${PACKER_VERSION}/packer_${PACKER_VERSION}_linux_amd64.zip -o /usr/local/bin/packer.zip \
 && unzip /usr/local/bin/packer.zip -d /usr/local/bin/ \
 && rm -f /usr/local/bin/packer.zip \
 && chmod 0755 /usr/local/bin/packer \
 && curl -L https://github.com/accurics/terrascan/releases/download/${TERRASCAN_VERSION}/terrascan_${TERRASCAN_VERSION#v}_Linux_x86_64.tar.gz -o /usr/local/bin/terrascan.tar.gz \
 && tar -xvf /usr/local/bin/terrascan.tar.gz -C /usr/local/bin/ terrascan \
 && rm -f /usr/local/bin/terrascan.tar.gz \
 && chmod 0755 /usr/local/bin/terrascan \
 && chown root: /usr/local/bin/terrascan \
 && groupadd --gid 53150 -r easy_infra \
 && useradd -r -g easy_infra -s "$(which bash)" --create-home --uid 53150 easy_infra \
 && su easy_infra -c "terrascan init"
USER easy_infra
WORKDIR /home/easy_infra

# git installs
ARG TERRAFORM_VERSION
ARG TFENV_VERSION
COPY --chown=easy_infra:easy_infra .terraformrc /home/easy_infra/
ENV PATH="/home/easy_infra/.tfenv/bin:${PATH}"
# hadolint ignore=SC1091
RUN git clone https://github.com/tfutils/tfenv.git /home/easy_infra/.tfenv --depth 1 --branch ${TFENV_VERSION} \
 && echo "export PATH=/home/easy_infra/.tfenv/bin:${PATH}" >> /home/easy_infra/.bashrc \
 && source /home/easy_infra/.bashrc \
 && mkdir -p /home/easy_infra/.terraform.d/plugin-cache \
 && tfenv install ${TERRAFORM_VERSION} \
 && tfenv use ${TERRAFORM_VERSION} \
 && rm -rf /home/easy_infra/.tfenv/.git \
 && command terraform -install-autocomplete \
 && git clone https://github.com/checkmarx/kics.git /home/easy_infra/.kics --depth 1 --branch ${KICS_VERSION} \
 && rm -rf /home/easy_infra/.kics/.git
ENV KICS_QUERIES_PATH="/home/easy_infra/.kics/assets/queries"

# pip installs
ARG CHECKOV_VERSION
ENV PATH="/home/easy_infra/.local/bin:${PATH}"
# hadolint ignore=DL3013
RUN python3 -m pip install --upgrade --no-cache-dir pip \
 && pip install --user --no-cache-dir checkov==${CHECKOV_VERSION} \
 && echo "export PATH=/home/easy_infra/.local/bin:${PATH}" >> /home/easy_infra/.bashrc

# misc setup
COPY --chown=easy_infra:easy_infra functions /functions
ENV BASH_ENV=/functions
RUN echo "source ${BASH_ENV}" >> /home/easy_infra/.bashrc \
 && mkdir /home/easy_infra/.ansible

WORKDIR /iac
COPY --chown=easy_infra:easy_infra docker-entrypoint.sh /usr/local/bin/
ENTRYPOINT ["tini", "-g", "--", "/usr/local/bin/docker-entrypoint.sh"]

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


FROM minimal AS az
USER root
ARG AZURE_CLI_VERSION
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
# hadolint ignore=DL3008
RUN apt-get update \
 #####
 # Per Microsoft recommendation at https://docs.microsoft.com/en-us/cli/azure/install-azure-cli-linux?pivots=apt
 && apt-get remove azure-cli -y \
 && apt-get autoremove -y \
 #####
 && apt-get -y install --no-install-recommends ca-certificates \
                                               curl \
                                               apt-transport-https \
                                               lsb-release \
                                               gnupg \
 && curl -sL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor | tee /etc/apt/trusted.gpg.d/microsoft.gpg > /dev/null \
 && AZ_REPO=$(lsb_release -cs) \
 && echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $AZ_REPO main" | tee /etc/apt/sources.list.d/azure-cli.list \
 && apt-get update \
 && apt-get -y install --no-install-recommends azure-cli=${AZURE_CLI_VERSION} \
 && apt-get clean autoclean \
 && apt-get -y autoremove \
 && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/* \
 && su easy_infra -c "ansible-galaxy collection install azure.azcollection"
USER easy_infra


FROM minimal AS aws
USER root
ARG AWS_CLI_VERSION
RUN curl -L https://awscli.amazonaws.com/awscli-exe-linux-x86_64-${AWS_CLI_VERSION}.zip -o /tmp/awscliv2.zip \
 && unzip /tmp/awscliv2.zip -d /tmp/ \
 && /tmp/aws/install --bin-dir /aws-cli-bin/ \
 # Required for the *-aws images to be functional
 && ln -sf /aws-cli-bin/* /usr/local/bin/ \
 && rm -rf /tmp/* \
 && su easy_infra -c "ansible-galaxy collection install amazon.aws" \
 && echo 'complete -C /usr/local/bin/aws_completer aws' >> /home/easy_infra/.bashrc
USER easy_infra


FROM minimal AS final

# AWS
COPY --from=aws --chown=easy_infra:easy_infra /usr/local/aws-cli/ /usr/local/aws-cli/
COPY --from=aws --chown=easy_infra:easy_infra /aws-cli-bin/ /usr/local/bin/
COPY --from=aws --chown=easy_infra:easy_infra /home/easy_infra/.bashrc /home/easy_infra/.bashrc
COPY --from=aws --chown=easy_infra:easy_infra /home/easy_infra/.ansible/collections/ansible_collections/amazon /home/easy_infra/.ansible/collections/ansible_collections/amazon

# Workaround due to moby/moby#37965 and docker-py BuildKit support is pending
# docker/docker-py#2230
RUN true

# Azure
COPY --from=az --chown=easy_infra:easy_infra /opt/az /opt/az
COPY --from=az --chown=easy_infra:easy_infra /usr/bin/az /usr/bin/az
COPY --from=az --chown=easy_infra:easy_infra /etc/apt/trusted.gpg.d/microsoft.gpg /etc/apt/trusted.gpg.d/microsoft.gpg
COPY --from=az --chown=easy_infra:easy_infra /etc/apt/sources.list.d/azure-cli.list /etc/apt/sources.list.d/azure-cli.list
COPY --from=az --chown=easy_infra:easy_infra /home/easy_infra/.ansible/collections/ansible_collections/azure /home/easy_infra/.ansible/collections/ansible_collections/azure
