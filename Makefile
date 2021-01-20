## Initialization
APT_PACKAGES       = ansible azure-cli
COMMIT_HASH       := $(shell git rev-parse HEAD)
FROM_IMAGE         = ubuntu
FROM_IMAGE_TAG     = 20.04
GITHUB             = tfutils/tfenv tfsec/tfsec hashicorp/packer
LOCAL_IMAGE_NAME   = easy_infra
REMOTE_IMAGE_NAME  = seiso/easy_infra
VERSION            = 0.7.1-dirty


## Validation
ifndef COMMIT_HASH
$(error COMMIT_HASH was not properly set)
endif


## Functions
get_github_latest_version = $$(docker run --rm alpine:3.13 /bin/ash -c "apk add curl jq &>/dev/null && curl -s https://api.github.com/repos/$(1)/releases/latest | jq -r '.tag_name'")
update_dockerfile_package = ./update_components.sh --package=$(1) --version=$(2)
update_dockerfile_repo    = ./update_components.sh --repo=$(1) --version=$(2)


## Rules
.PHONY: all
all: build-all

.PHONY: update
update: update-dependencies

.PHONY: update-dependencies
update-dependencies: update-apt update-ci update-awscli update-checkov update-github update-terraform

.PHONY: lint
lint:
	@docker run --rm -v $$(pwd):/root/ projectatomic/dockerfile-lint dockerfile_lint -f /root/Dockerfile -r /root/.github/workflows/etc/oci_annotations.yml

.PHONY: generate-functions
generate-functions:
	@echo "Generating the functions..."
	@docker run --rm -v $$(pwd):/usr/src/app -w /usr/src/app python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip install --user -r ci.txt &>/dev/null && ./update_bash_env.py --config-file easy_infra.yml --output functions --template-file functions.j2"
	@echo "Done!"

.PHONY: build-all
build-all: build build-minimal build-az build-aws

.PHONY: build-minimal
build-minimal: generate-functions
	@echo "Building the minimal image..."
	@DOCKER_BUILDKIT=1 docker build --target base --rm -t $(LOCAL_IMAGE_NAME):latest-minimal -t $(LOCAL_IMAGE_NAME):$(VERSION)-minimal -t $(LOCAL_IMAGE_NAME):$(COMMIT_HASH)-minimal --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)-minimal" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" .
	@echo "Done!"

.PHONY: build
build: generate-functions
	@echo "Building the complete image..."
	@DOCKER_BUILDKIT=1 docker build --target final --rm -t $(LOCAL_IMAGE_NAME):latest -t $(LOCAL_IMAGE_NAME):$(VERSION) -t $(LOCAL_IMAGE_NAME):$(COMMIT_HASH) --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" .
	@echo "Done!"

.PHONY: build-az
build-az: generate-functions
	@echo "Building the az image..."
	@DOCKER_BUILDKIT=1 docker build --target az --rm -t $(LOCAL_IMAGE_NAME):latest-az -t $(LOCAL_IMAGE_NAME):$(VERSION)-az -t $(LOCAL_IMAGE_NAME):$(COMMIT_HASH)-az --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)-az" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" .
	@echo "Done!"

.PHONY: build-aws
build-aws: generate-functions
	@echo "Building the aws image..."
	@DOCKER_BUILDKIT=1 docker build --target aws --rm -t $(LOCAL_IMAGE_NAME):latest-aws -t $(LOCAL_IMAGE_NAME):$(VERSION)-aws -t $(LOCAL_IMAGE_NAME):$(COMMIT_HASH)-aws --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)-aws" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" .
	@echo "Done!"

.PHONY: build-ci
build-ci: generate-functions
	@echo "Building all of the images for CI..."
	@DOCKER_BUILDKIT=1 docker build --target base --rm -t $(REMOTE_IMAGE_NAME):latest-minimal -t $(REMOTE_IMAGE_NAME):$(VERSION)-minimal -t $(REMOTE_IMAGE_NAME):$(COMMIT_HASH)-minimal --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)-minimal" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" --build-arg BUILDKIT_INLINE_CACHE=1 .
	@DOCKER_BUILDKIT=1 docker build --target aws --rm -t $(REMOTE_IMAGE_NAME):latest-aws -t $(REMOTE_IMAGE_NAME):$(VERSION)-aws -t $(REMOTE_IMAGE_NAME):$(COMMIT_HASH)-aws --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)-aws" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" --build-arg BUILDKIT_INLINE_CACHE=1 .
	@DOCKER_BUILDKIT=1 docker build --target az --rm -t $(REMOTE_IMAGE_NAME):latest-az -t $(REMOTE_IMAGE_NAME):$(VERSION)-az -t $(REMOTE_IMAGE_NAME):$(COMMIT_HASH)-az --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)-az" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" --build-arg BUILDKIT_INLINE_CACHE=1 .
	@DOCKER_BUILDKIT=1 docker build --target final --rm -t $(REMOTE_IMAGE_NAME):latest -t $(REMOTE_IMAGE_NAME):$(VERSION) -t $(REMOTE_IMAGE_NAME):$(COMMIT_HASH) --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" --build-arg "VERSION=$(VERSION)" --build-arg "COMMIT_HASH=$(COMMIT_HASH)" --build-arg BUILDKIT_INLINE_CACHE=1 .
	@echo "Done!"

.PHONY: push
push:
	@docker push --all-tags $(REMOTE_IMAGE_NAME)

.PHONY: update-apt
update-apt:
	@echo "Updating the apt package versions..."
	@for package in $(APT_PACKAGES); do \
		version=$$(docker run --rm $(REMOTE_IMAGE_NAME):latest-az /bin/bash -c "apt-get update &>/dev/null && apt-cache policy $${package} | grep '^  Candidate:' | awk -F' ' '{print \$$NF}'"); \
		$(call update_dockerfile_package,$${package},$${version}); \
	done
	@echo "Done!"

.PHONY: update-ci
update-ci: ci-to-freeze.txt
	@echo "Updating ci.txt..."
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip3 install -r /usr/src/app/ci-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/ci.txt"
	@echo "Done!"

.PHONY: update-awscli
update-awscli: awscli-to-freeze.txt
	@echo "Updating awscli.txt..."
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip3 install -r /usr/src/app/awscli-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/awscli.txt"
	@echo "Done!"

.PHONY: update-checkov
update-checkov: checkov-to-freeze.txt
	@echo "Updating checkov.txt..."
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3.9 /bin/bash -c "python3 -m pip install --upgrade pip &>/dev/null && pip3 install -r /usr/src/app/checkov-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/checkov.txt"
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
	@version=$$(docker run --rm $(REMOTE_IMAGE_NAME):latest-minimal /bin/bash -c "tfenv list-remote 2>/dev/null | egrep -v '(rc|alpha|beta)' | head -1"); \
		$(call update_dockerfile_package,terraform,$${version})
	@echo "Done!"

.PHONY: release
release:
	@git tag v$(VERSION)
	@git push origin v$(VERSION)

