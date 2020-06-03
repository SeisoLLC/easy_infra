## Initialization
COMMIT_HASH       := $(shell git rev-parse HEAD)
FROM_IMAGE         = alpine
FROM_IMAGE_TAG     = 3
IMAGE_NAME         = easy_infra
APK_PACKAGES       = ansible terraform
YARN_PACKAGES      = mermaid @mermaid-js/mermaid-cli
UNAME_S           := $(shell uname -s)
VERSION            = 0.2.0


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
update:
	@echo "Updating the apk package versions in the Dockerfile..."
	@for package in $(APK_PACKAGES); do \
		version=$$(docker run --rm $(FROM_IMAGE):$(FROM_IMAGE_TAG) /bin/ash -c "apk update &>/dev/null; apk add --no-cache $${package} &>/dev/null; echo \$$(apk search -x $${package} | sed 's/^$${package}-//g')"); \
		./update.sh --package=$${package} --version=$${version}; \
	done
	@echo "Done!"
	@echo "Updating the yarn package versions in the Dockerfile..."
	@for package in $(YARN_PACKAGES); do\
		version=$$(docker run --rm $(FROM_IMAGE):$(FROM_IMAGE_TAG) /bin/ash -c "apk update &>/dev/null; apk add --no-cache yarn jq &>/dev/null; yarn info $${package} --json | jq -r .data[\\\"dist-tags\\\"].latest"); \
		./update.sh --package=$${package} --version=$${version}; \
	done
	@echo "Done!"

.PHONY: push_tag
push_tag:
	@git tag v$(VERSION)
	@git push origin v$(VERSION)

.PHONY: awscli
awscli: awscli-to-freeze.txt
	@python3 -c 'print("Updating the awscli.txt file...")'
	@docker run --rm -v $$(pwd):/usr/src/app/ python:3.8 /bin/bash -c "pip3 install -r /usr/src/app/awscli-to-freeze.txt && pip3 freeze > /usr/src/app/awscli.txt"

