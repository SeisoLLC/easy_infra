ARG FROM_IMAGE=ubuntu
ARG FROM_IMAGE_TAG=20.04

FROM "${FROM_IMAGE}":"${FROM_IMAGE_TAG}" AS minimal

ARG EASY_INFRA_VERSION
ENV EASY_INFRA_VERSION="${EASY_INFRA_VERSION}"
ARG COMMIT_HASH

LABEL org.opencontainers.image.authors="Jon Zeolla"
LABEL org.opencontainers.image.licenses="BSD-3-Clause"
LABEL org.opencontainers.image.vendor="Seiso"
LABEL org.opencontainers.image.version="${EASY_INFRA_VERSION}"
LABEL org.opencontainers.image.title="easy_infra"
LABEL org.opencontainers.image.description="This is a docker container that simplifies and secures Infrastructure as Code deployments"
LABEL org.opencontainers.image.url="https://seisollc.com"
LABEL org.opencontainers.image.source="https://github.com/SeisoLLC/easy_infra"
LABEL org.opencontainers.image.revision="${COMMIT_HASH}"

# minimal setup
ARG BUILDARCH
ARG KICS_ARCH
ARG FLUENT_BIT_VERSION
ENV FLUENT_BIT_VERSION="${FLUENT_BIT_VERSION}"
ARG CONSUL_TEMPLATE_VERSION
ENV CONSUL_TEMPLATE_VERSION="${CONSUL_TEMPLATE_VERSION}"
ARG ENVCONSUL_VERSION
ENV ENVCONSUL_VERSION="${ENVCONSUL_VERSION}"
ARG ANSIBLE_VERSION
ENV ANSIBLE_VERSION="${ANSIBLE_VERSION}"
ARG TERRAFORM_VERSION
ENV TERRAFORM_VERSION="${TERRAFORM_VERSION}"
ARG TERRATAG_VERSION
ENV TERRATAG_VERSION="${TERRATAG_VERSION}"
ARG TFENV_VERSION
ENV TFENV_VERSION="${TFENV_VERSION}"
ARG CHECKOV_VERSION
ENV CHECKOV_VERSION="${CHECKOV_VERSION}"
ENV CHECKOV_JSON_REPORT_PATH="/tmp/reports/checkov"
ENV SKIP_CHECKOV="false"
ARG KICS_VERSION
ENV KICS_VERSION="${KICS_VERSION}"
ENV SKIP_KICS="false"
ENV KICS_INCLUDE_QUERIES_PATH="/home/easy_infra/.kics/assets/queries"
ENV KICS_LIBRARY_PATH="/home/easy_infra/.kics/assets/libraries"
ENV KICS_JSON_REPORT_PATH="/tmp/reports/kics"
ENV AUTODETECT="false"
ENV DISABLE_HOOKS="false"
ENV PATH="/home/easy_infra/.local/bin:${PATH}"
ARG DEBIAN_FRONTEND="noninteractive"
ARG TRACE="false"
# hadolint ignore=DL3003,DL3008,DL3013,SC1091
RUN groupadd --gid 53150 -r easy_infra \
 && useradd -r -g easy_infra -s "$(which bash)" --create-home --uid 53150 easy_infra \
 && apt-get update \
 && apt-get -y install --no-install-recommends ansible=${ANSIBLE_VERSION} \
                                               bsdmainutils \
                                               ca-certificates \
                                               curl \
                                               gettext \
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
 && apt-get -y upgrade \
 && mkdir -p /home/easy_infra/.ssh \
 && echo -e "# START preloaded known_hosts" >> /home/easy_infra/.ssh/known_hosts \
 && ssh-keyscan gitlab.com \
                github.com \
                bitbucket.org \
                ssh.dev.azure.com \
                git-codecommit.us-east-1.amazonaws.com \
                git-codecommit.us-east-2.amazonaws.com \
                git-codecommit.us-west-1.amazonaws.com \
                git-codecommit.us-west-2.amazonaws.com \
    >> /home/easy_infra/.ssh/known_hosts \
 && echo "# END preloaded known_hosts" >> /home/easy_infra/.ssh/known_hosts \
 && if [ "${TRACE}" = "true" ]; then \
    apt-get -y install --no-install-recommends libcap2-bin \
                                               strace \
  ; fi \
 && python3 -m pip install --upgrade --no-cache-dir pip \
 && su - easy_infra -c "pip install --user --no-cache-dir checkov==${CHECKOV_VERSION}" \
 && mkdir -p "${CHECKOV_JSON_REPORT_PATH}" \
 && echo "export PATH=/home/easy_infra/.local/bin:${PATH}" >> /home/easy_infra/.bashrc \
 && curl -L https://github.com/checkmarx/kics/releases/download/${KICS_VERSION}/kics_${KICS_VERSION#v}_linux_${KICS_ARCH}.tar.gz -o /usr/local/bin/kics.tar.gz \
 && tar -xvf /usr/local/bin/kics.tar.gz -C /usr/local/bin/ kics \
 && rm -f /usr/local/bin/kics.tar.gz \
 && chmod 0755 /usr/local/bin/kics \
 && chown root: /usr/local/bin/kics \
 && mkdir -p "${KICS_JSON_REPORT_PATH}" \
 && su easy_infra -c "git clone https://github.com/checkmarx/kics.git /home/easy_infra/.kics --depth 1 --branch ${KICS_VERSION}" \
 && rm -rf /home/easy_infra/.kics/.git \
 && curl -L https://github.com/env0/terratag/releases/download/${TERRATAG_VERSION}/terratag_${TERRATAG_VERSION#v}_linux_${BUILDARCH}.tar.gz -o /usr/local/bin/terratag.tar.gz \
 && tar -xvf /usr/local/bin/terratag.tar.gz -C /usr/local/bin/ terratag \
 && rm -f /usr/local/bin/terratag.tar.gz \
 && chmod 0755 /usr/local/bin/terratag \
 && chown root: /usr/local/bin/terratag \
 && su easy_infra -c "git clone https://github.com/tfutils/tfenv.git /home/easy_infra/.tfenv --depth 1 --branch ${TFENV_VERSION}" \
 && rm -rf /home/easy_infra/.tfenv/.git \
 && su easy_infra -c "mkdir -p /home/easy_infra/.local/bin/" \
 && ln -s /home/easy_infra/.tfenv/bin/* /home/easy_infra/.local/bin \
 && su easy_infra -c "mkdir -p /home/easy_infra/.terraform.d/plugin-cache" \
 && su - easy_infra -c "tfenv install ${TERRAFORM_VERSION}" \
 && su - easy_infra -c "tfenv use ${TERRAFORM_VERSION}" \
 && su - easy_infra -c "terraform -install-autocomplete" \
 && curl -L https://releases.hashicorp.com/consul-template/${CONSUL_TEMPLATE_VERSION#v}/consul-template_${CONSUL_TEMPLATE_VERSION#v}_linux_${BUILDARCH}.zip -o /usr/local/bin/consul-template.zip \
 && unzip /usr/local/bin/consul-template.zip -d /usr/local/bin/ \
 && rm -f /usr/local/bin/consul-template.zip \
 && chmod 0755 /usr/local/bin/consul-template \
 && curl -L https://releases.hashicorp.com/envconsul/${ENVCONSUL_VERSION#v}/envconsul_${ENVCONSUL_VERSION#v}_linux_${BUILDARCH}.zip -o /usr/local/bin/envconsul.zip \
 && unzip /usr/local/bin/envconsul.zip -d /usr/local/bin/ \
 && rm -f /usr/local/bin/envconsul.zip \
 && chmod 0755 /usr/local/bin/envconsul \
 && apt-get install -y --no-install-recommends cmake build-essential flex bison libyaml-dev \
 && git clone https://github.com/fluent/fluent-bit --depth 1 --branch ${FLUENT_BIT_VERSION} \
 && cd fluent-bit/build \
 && cmake ../ && make && make install \
 && cd ../.. \
 && rm -rf fluent-bit \
 && apt-get remove -y cmake build-essential flex bison libyaml-dev \
 && echo "source /functions" >> /home/easy_infra/.bashrc \
 && su easy_infra -c "mkdir /home/easy_infra/.ansible" \
 && apt-get clean autoclean \
 && apt-get -y autoremove \
 && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/* /tmp/* /var/tmp/* /var/log/* /var/cache/debconf/*-old \
 && touch /var/log/easy_infra.log /var/log/fluent-bit.log /var/log/40-set_default_terraform_version.log /var/log/50-terraform_dynamic_version_use.log \
 && chown -R easy_infra: /var/log/*.log
USER easy_infra

COPY --chown=easy_infra:easy_infra functions /functions
COPY --chown=easy_infra:easy_infra .terraformrc /home/easy_infra/
COPY --chown=easy_infra:easy_infra docker-entrypoint.sh /usr/local/bin/
COPY --chown=easy_infra:easy_infra common.sh /usr/local/bin/
COPY --chown=easy_infra:easy_infra hooks /opt/hooks/bin/
COPY --chown=easy_infra:easy_infra fluent-bit.conf /usr/local/etc/fluent-bit/fluent-bit.conf
COPY --chown=easy_infra:easy_infra fluent-bit.inputs.conf /usr/local/etc/fluent-bit/fluent-bit.inputs.conf
COPY --chown=easy_infra:easy_infra fluent-bit.outputs.conf /usr/local/etc/fluent-bit/fluent-bit.outputs.conf

ENV BASH_ENV=/functions
WORKDIR /iac
ENTRYPOINT ["tini", "-g", "--", "/usr/local/bin/docker-entrypoint.sh"]


FROM minimal AS az
USER root
ARG AZURE_CLI_VERSION
ENV AZURE_CLI_VERSION="${AZURE_CLI_VERSION}"
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
 # As of 2022-10-07 "The azure-cli deb package does not support ARM64 architecture"
 && echo "deb [arch=amd64] https://packages.microsoft.com/repos/azure-cli/ $AZ_REPO main" | tee /etc/apt/sources.list.d/azure-cli.list \
 && apt-get update \
 && apt-get -y install --no-install-recommends azure-cli=${AZURE_CLI_VERSION} \
 && apt-get clean autoclean \
 && apt-get -y autoremove \
 && rm -rf /var/cache/apt/archives/* /var/lib/apt/lists/* /tmp/* /var/tmp/* /var/cache/debconf/*-old \
 && su easy_infra -c "ansible-galaxy collection install azure.azcollection"
USER easy_infra


FROM minimal AS aws
USER root
ARG AWS_CLI_ARCH
ARG AWS_CLI_VERSION
ENV AWS_CLI_VERSION="${AWS_CLI_VERSION}"
RUN curl -L https://awscli.amazonaws.com/awscli-exe-linux-${AWS_CLI_ARCH}-${AWS_CLI_VERSION}.zip -o /tmp/awscliv2.zip \
 && unzip /tmp/awscliv2.zip -d /tmp/ \
 && /tmp/aws/install --bin-dir /aws-cli-bin/ \
 # Required for the *-aws images to be functional
 && ln -sf /aws-cli-bin/* /usr/local/bin/ \
 && rm -rf /tmp/* /var/tmp/* /var/cache/debconf/*-old \
 && su easy_infra -c "ansible-galaxy collection install amazon.aws" \
 && echo 'complete -C /usr/local/bin/aws_completer aws' >> /home/easy_infra/.bashrc
USER easy_infra


FROM minimal AS final

# AWS
COPY --from=aws --chown=easy_infra:easy_infra /usr/local/aws-cli/ /usr/local/aws-cli/
COPY --from=aws --chown=easy_infra:easy_infra /aws-cli-bin/ /usr/local/bin/
COPY --from=aws --chown=easy_infra:easy_infra /home/easy_infra/.bashrc /home/easy_infra/.bashrc
COPY --from=aws --chown=easy_infra:easy_infra /home/easy_infra/.ansible/collections/ansible_collections/amazon /home/easy_infra/.ansible/collections/ansible_collections/amazon
ARG AWS_CLI_VERSION
ENV AWS_CLI_VERSION="${AWS_CLI_VERSION}"

# Workaround due to moby/moby#37965 and docker-py BuildKit support is pending
# docker/docker-py#2230
RUN true

# Azure
COPY --from=az --chown=easy_infra:easy_infra /opt/az /opt/az
COPY --from=az --chown=easy_infra:easy_infra /usr/bin/az /usr/bin/az
COPY --from=az --chown=easy_infra:easy_infra /etc/apt/trusted.gpg.d/microsoft.gpg /etc/apt/trusted.gpg.d/microsoft.gpg
COPY --from=az --chown=easy_infra:easy_infra /etc/apt/sources.list.d/azure-cli.list /etc/apt/sources.list.d/azure-cli.list
COPY --from=az --chown=easy_infra:easy_infra /home/easy_infra/.ansible/collections/ansible_collections/azure /home/easy_infra/.ansible/collections/ansible_collections/azure
ARG AZURE_CLI_VERSION
ENV AZURE_CLI_VERSION="${AZURE_CLI_VERSION}"
