## Initialization
APT_PACKAGES       = ansible azure-cli
COMMIT_HASH       := $(shell git rev-parse HEAD)
FROM_IMAGE         = ubuntu
FROM_IMAGE_TAG     = 20.04
GITHUB             = tfutils/tfenv tfsec/tfsec hashicorp/packer
IMAGE_NAME         = easy_infra
UNAME_S           := $(shell uname -s)
VERSION            = 0.7.1
YARN_PACKAGES      = mermaid @mermaid-js/mermaid-cli


## Validation
ifneq ($(UNAME_S),Darwin)
$(error This project currently only supports Darwin)
endif

ifndef COMMIT_HASH
$(error COMMIT_HASH was not properly set)
endif


## Functions
get_github_latest_version = $$(docker run --rm easy_infra:latest /bin/bash -c "curl -s https://api.github.com/repos/$(1)/releases/latest | jq -r '.tag_name'")
update_dockerfile_package = ./update_components.sh --package=$(1) --version=$(2)
update_dockerfile_repo    = ./update_components.sh --repo=$(1) --version=$(2)


## Rules
.PHONY: all
all: update build

.PHONY: update
update: update-deps update-functions

.PHONY: update-deps
update-deps: update-apt update-requirements update-awscli update-github update-terraform update-yarn


.PHONY: update-functions
update-functions:
	@echo "Updating the functions..."
	@docker run --rm -v $$(pwd):/usr/src/app -w /usr/src/app python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip install --user -r requirements.txt &>/dev/null && ./update_bash_env.py --config-file easy_infra.yml --output functions --template-file functions.j2"
	@echo "Done!"

.PHONY: build
build:
	@DOCKER_BUILDKIT=1 docker build --rm -t $(IMAGE_NAME):latest -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):$(COMMIT_HASH) --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" .

.PHONY: update-apt
update-apt:
	@echo "Updating the apt package versions..."
	@for package in $(APT_PACKAGES); do \
		version=$$(docker run --rm easy_infra:latest /bin/bash -c "apt-get update &>/dev/null && apt-cache policy $${package} | grep '^  Candidate:' | awk -F' ' '{print \$$NF}'"); \
		$(call update_dockerfile_package,$${package},$${version}); \
	done
	@echo "Done!"

.PHONY: update-requirements
update-requirements: requirements-to-freeze.txt
	@echo "Updating requirements.txt..."
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip3 install -r /usr/src/app/requirements-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/requirements.txt"
	@echo "Done!"

.PHONY: update-awscli
update-awscli: awscli-to-freeze.txt
	@echo "Updating the awscli.txt..."
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip3 install -r /usr/src/app/awscli-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/awscli.txt"
	@echo "Done!"

.PHONY: update-github
update-github:
	@echo "Updating github repo tags..."
	@for repo in $(GITHUB); do \
		version=$(call get_github_latest_version,$${repo}); \
		$(call update_dockerfile_repo,$${repo},$${version}); \
	done
	@echo "Done!"

.PHONY: update-terraform
update-terraform:
	@echo "Updating the terraform version..."
	@version=$$(docker run --rm easy_infra:latest /bin/bash -c "tfenv list-remote 2>/dev/null | egrep -v '(rc|alpha|beta)' | head -1"); \
		$(call update_dockerfile_package,terraform,$${version})
	@echo "Done!"

.PHONY: update-yarn
update-yarn:
	@echo "Updating the yarn package versions..."
	@for package in $(YARN_PACKAGES); do\
		version=$$(docker run --rm easy_infra:latest /bin/bash -c "yarn info $${package} --json 2>/dev/null | jq -r .data[\\\"dist-tags\\\"].latest"); \
		$(call update_dockerfile_package,$${package},$${version}); \
	done
	@echo "Done!"


.PHONY: push_tag
push_tag:
	@git tag v$(VERSION)
	@git push origin v$(VERSION)

