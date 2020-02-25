VERSION?=$$(git rev-parse --abbrev-ref HEAD)

.PHONY: all
all: marge-bot dockerize

.PHONY: marge-bot
marge-bot:
	nix-build --keep-failed --attr marge-bot

.PHONY: clean
clean:
	rm -rf .pytest_cache .cache .coverage dist result result-*

.PHONY: bump-sources
bump-sources:
	niv update

.PHONY: dockerize
dockerize:
	docker load --input $$(nix-build --attr marge-bot-image)

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
