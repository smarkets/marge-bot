requirements_frozen.txt requirements.nix requirements_override.nix: requirements.txt
	pypi2nix -V 3.6 -r $^

.PHONY: all
all: requirements_frozen.txt requirements.nix requirements_override.nix default.nix
	nix-build -K .

.PHONY: clean
clean:
	rm -rf .cache result requirements_frozen.txt

.PHONY: bump-requirements
bump-requirements: clean requirements_frozen.txt
