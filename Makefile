VERSION?=$$(git rev-parse --abbrev-ref HEAD)

.PHONY: all
all: requirements_frozen.txt requirements.nix requirements_override.nix marge-bot dockerize

.PHONY: marge-bot
marge-bot:
	nix-build --keep-failed --attr marge-bot default.nix

.PHONY: clean
clean:
	rm -rf .cache result result-* requirements_frozen.txt

.PHONY: bump
bump: bump-requirements bump-sources

.PHONY: bump-sources
bump-sources:
	nix-shell --run niv update

.PHONY: bump-requirements
bump-requirements: clean requirements_frozen.txt

requirements_frozen.txt requirements.nix requirements_override.nix: requirements.txt
	pypi2nix -V 3.6 -r $^

.PHONY: dockerize
dockerize:
	docker load --input $$(nix-build --attr docker-image default.nix) --show-trace

.PHONY: docker-push
docker-push:
	if [ -n "$$DOCKER_USERNAME" -a -n "$$DOCKER_PASSWORD" ]; then \
		docker login -u "$${DOCKER_USERNAME}" -p "$${DOCKER_PASSWORD}"; \
	else \
		docker login; \
	fi
	docker tag smarkets/marge-bot:$$(cat version) smarkets/marge-bot:$(VERSION)
	if [ "$(VERSION)" = "$$(cat version)" ]; then \
		docker tag smarkets/marge-bot:$$(cat version) smarkets/marge-bot:latest; \
		docker tag smarkets/marge-bot:$$(cat version) smarkets/marge-bot:stable; \
		docker push smarkets/marge-bot:stable; \
		docker push smarkets/marge-bot:latest; \
	fi
	docker push smarkets/marge-bot:$(VERSION)
	# for backwards compatibility push to previous location
	docker tag smarkets/marge-bot:$$(cat version) smarketshq/marge-bot:latest
	docker tag smarkets/marge-bot:$$(cat version) smarketshq/marge-bot:$(VERSION)
	docker push smarketshq/marge-bot:$(VERSION)
	docker push smarketshq/marge-bot:latest
