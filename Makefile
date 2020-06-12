## Initialization
COMMIT_HASH       := $(shell git rev-parse HEAD)
FROM_IMAGE         = alpine
FROM_IMAGE_TAG     = 3
IMAGE_NAME         = easy_infra
APK_PACKAGES       = ansible
YARN_PACKAGES      = mermaid @mermaid-js/mermaid-cli
UNAME_S           := $(shell uname -s)
VERSION            = 0.3.1


## Validation
ifneq ($(UNAME_S),Darwin)
$(error This project currently only supports Darwin)
endif

ifndef COMMIT_HASH
$(error COMMIT_HASH was not properly set)
endif


## Rules
.PHONY: build
build:
	@DOCKER_BUILDKIT=1 docker build --rm -t $(IMAGE_NAME):latest -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):$(COMMIT_HASH) --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" .


.PHONY: update
update: update-apk update-awscli update-terraform update-yarn

.PHONY: update-apk
update-apk:
	@echo "Updating the apk package versions..."
	@for package in $(APK_PACKAGES); do \
		version=$$(docker run --rm easy_infra:latest "apk update &>/dev/null && apk search -x $${package} | sed 's/^$${package}-//g'"); \
		./update.sh --package=$${package} --version=$${version}; \
	done
	@echo "Done!"

.PHONY: update-awscli
update-awscli: awscli-to-freeze.txt
	@echo "Updating the awscli.txt..."
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3 /bin/bash -c "pip3 install -r /usr/src/app/awscli-to-freeze.txt &>/dev/null && pip3 freeze > /usr/src/app/awscli.txt"
	@echo "Done!"

.PHONY: update-terraform
update-terraform:
	@echo "Updating the terraform version..."
	@version=$$(docker run --rm easy_infra:latest "tfenv list-remote 2>/dev/null | egrep -v '(rc|beta)' | head -1"); \
		./update.sh --package=terraform --version=$${version}
	@echo "Done!"

.PHONY: update-yarn
update-yarn:
	@echo "Updating the yarn package versions..."
	@for package in $(YARN_PACKAGES); do\
		version=$$(docker run --rm easy_infra:latest "yarn info $${package} --json 2>/dev/null | jq -r .data[\\\"dist-tags\\\"].latest"); \
		./update.sh --package=$${package} --version=$${version}; \
	done
	@echo "Done!"


.PHONY: push_tag
push_tag:
	@git tag v$(VERSION)
	@git push origin v$(VERSION)

