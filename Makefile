## Initialization
COMMIT_HASH       := $(shell git rev-parse HEAD)
DOCKER             = docker
FROM_IMAGE         = alpine
FROM_IMAGE_TAG     = 3
IMAGE_NAME         = easy_infra
PACKAGES           = ansible terraform
UNAME_S           := $(shell uname -s)
VERSION            = 0.1.0


## Validation
ifneq ($(UNAME_S),Darwin)
$(error This project currently only supports Darwin)
endif
ifndef COMMIT_HASH
$(error COMMIT_HASH was not properly set)
endif


## Rules
build:
	@DOCKER_BUILDKIT=1 $(DOCKER) build --rm -t $(IMAGE_NAME):latest -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):$(COMMIT_HASH) --build-arg "FROM_IMAGE=$(FROM_IMAGE)" --build-arg "FROM_IMAGE_TAG=$(FROM_IMAGE_TAG)" .

update:
	@echo "Updating the package versions in the Dockerfile..."
	@for package in $(PACKAGES); do \
		version=$$($(DOCKER) run --rm $(FROM_IMAGE):$(FROM_IMAGE_TAG) /bin/ash -c "apk update &>/dev/null; apk add --no-cache $${package} &>/dev/null; echo \$$(apk search -x $${package} | sed 's/^$${package}-//g')"); \
		./update.sh --package=$${package} --version=$${version}; \
	done
	@echo "Done!"

push_tag:
	@git tag v$(VERSION)
	@git push origin v$(VERSION)

.PHONY: build update push_tag

