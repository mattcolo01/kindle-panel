VERSION := v1.0.0-beta.4
SRC_FILES := $(shell find src -name '*.sh' -o -name '*.png')
# Per-device files (git-ignored): copied only if present
DEVICE_FILES := $(wildcard src/local/ca.pem src/local/token)
TARGET_FILES := $(SRC_FILES:src/%=dist/%) $(DEVICE_FILES:src/%=dist/%)

# xh and next-wakeup are not rebuilt: they come from the upstream release
# tarball (see UPSTREAM.md).
RELEASE_URL := https://github.com/pascalw/kindle-dash/releases/download/$(VERSION)/kindle-dash-$(VERSION).tgz
RELEASE_SHA256 := 3bdf2626dd94bc9636e54ae159f193379aea257a4c39f4b3a91d5f395fa76889
XH_SHA256 := d77c9b66a5bcd2ef0375d922b7f709f8ce4697a9d57c4b2452d6cb7ce6eaef70
NEXT_WAKEUP_SHA256 := fb91e220f501be4a74cd5e06c61db26656c1db3e172d177fff90ac1de1c8f8b7
SHA256SUM ?= sha256sum

dist: dist/next-wakeup dist/xh dist/local/state ${TARGET_FILES}

tarball: dist
	tar -C dist -cvzf kindle-dash-${VERSION}.tgz ./

dist/%: src/%
	@echo "Copying $<"
	@mkdir -p $(@D)
	@cp "$<" "$@"

tmp/release.tgz:
	mkdir -p tmp/
	curl -fsSL -o $@.part $(RELEASE_URL)
	echo "$(RELEASE_SHA256)  $@.part" | $(SHA256SUM) -c -
	mv $@.part $@

dist/xh: tmp/release.tgz
	mkdir -p dist/
	tar -C dist --no-same-owner -xzf tmp/release.tgz ./xh
	echo "$(XH_SHA256)  $@" | $(SHA256SUM) -c -

dist/next-wakeup: tmp/release.tgz
	mkdir -p dist/
	tar -C dist --no-same-owner -xzf tmp/release.tgz ./next-wakeup
	echo "$(NEXT_WAKEUP_SHA256)  $@" | $(SHA256SUM) -c -

dist/local/state:
	mkdir -p dist/local/state

clean:
	rm -r dist/*

watch:
	watchexec -w src/ -p -- make

format:
	shfmt -i 2 -w -l src/**/*.sh

lint:
	shellcheck -s ash src/*.sh src/local/*.sh
	shfmt -i 2 -d src/*.sh src/local/*.sh

.PHONY: clean watch tarball format lint
