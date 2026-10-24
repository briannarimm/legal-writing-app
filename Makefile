# Build one document.   make                          -> build the first document
#                       make DOC=documents/my-memo   -> build that document (PDF/Word/HTML per its template)
#                       make redline DOC=…           -> redline vs. that document's last version tag
#                       make import-edits DOC=… FILE=edits/from-editors.docx
#                       make app                     -> open ReWord in Terminal (the Mac app is the usual way)
#                       make mac-app                 -> (re)build ReWord.app, the double-clickable app
#                       make dist                    -> the downloadable zip in distro/
#                       make check                   -> the checks for a change to ReWord: the tests, and
#                                                       the Mac window and PDF helper compile (on a Mac)
#
# Documents live in documents/<name>/ (document.json says which template they use, and
# templates/<id>/ says how that template builds). Output goes to build/<name>/.
# Everything runs inside the pinned Docker image (docker/Dockerfile) so output is the same
# on every machine. Set USE_DOCKER=0 to use a local pandoc instead.
#
# There is no hosted CI: `make check` is what a pull request should pass, run on a Mac.

IMAGE      ?= lawreview-build:latest
USE_DOCKER ?= 1

DOC      ?= $(patsubst %/,%,$(firstword $(filter-out documents/_%,$(wildcard documents/*/))))
SLUG     := $(notdir $(DOC))
TEMPLATE := $(shell sed -n 's/.*"template": *"\([^"]*\)".*/\1/p' $(DOC)/document.json 2>/dev/null)
TDIR     := templates/$(TEMPLATE)
BUILD    := build/$(SLUG)

# `make app`, `make image` and `make clean` don't need a document.
ifneq ($(filter-out app mac-app dist check test mac-check image clean,$(or $(MAKECMDGOALS),all)),)
ifeq ($(TEMPLATE),)
$(error No document found. Create one in the app, or pass DOC=documents/<name>)
endif
include $(TDIR)/template.mk     # sets OUTPUTS (and PDF_BUILDER for briefs)
endif

SECTIONS := $(sort $(wildcard $(DOC)/[0-9]*.md))
DEPS     := $(SECTIONS) $(DOC)/metadata.yaml $(DOC)/document.json $(wildcard defaults/*.yaml) \
            $(wildcard $(TDIR)/*) $(wildcard templates/_brief/*) $(wildcard templates/_chicago/*) $(wildcard filters/*.lua) \
            $(wildcard library/citations/*.md)

ifeq ($(USE_DOCKER),1)
RUN := docker run --rm --platform linux/amd64 -v "$(CURDIR)":/data -w /data \
       -u $(shell id -u):$(shell id -g) -e HOME=/tmp -e GHCRTS=-V0 \
       -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/data \
       $(IMAGE)
else
RUN :=
endif

# Optional: CITEPROC=1 renders [@citekey] citations from the Zotero export using
# refs/*.csl (see README). Off by default: citations are written by hand or inserted
# from the app's citation library.
ifeq ($(CITEPROC),1)
CSL  := $(firstword $(wildcard refs/*.csl))
CITE := --citeproc --bibliography refs/references.bib -M suppress-bibliography=true $(if $(CSL),--csl $(CSL),)
endif

# Live citations ({.cite tag=…}) are formatted by scripts/cites_filter.py. FINAL=1 builds the final-draft forms.
CITES_ENV := env CITES_TEMPLATE=$(TDIR)/template.json CITES_MODE=$(if $(FINAL),final,draft)
PANDOC := $(RUN) $(CITES_ENV) pandoc -d defaults/common.yaml --metadata-file $(DOC)/metadata.yaml --filter scripts/cites_filter.py $(CITE)

# Redline base: this document's most recent git version tag (<name>/vN.N) unless you pass BASE=<ref>.
# The app instead passes BASE=<version name> BASE_DIR=<folder holding that saved version>.
BASE ?= $(shell git describe --tags --abbrev=0 --match '$(SLUG)/v*' 2>/dev/null)

.PHONY: all wordcount redline import-edits app mac-app dist check test mac-check watch image clean $(OUTPUTS)

all: $(foreach o,$(OUTPUTS),$(BUILD)/$(SLUG).$(o)) wordcount

$(OUTPUTS): %: $(BUILD)/$(SLUG).%

$(BUILD):
	@mkdir -p $(BUILD)

$(BUILD)/$(SLUG).pdf: $(DEPS) | $(BUILD)
ifeq ($(PDF_BUILDER),script)
	$(RUN) $(CITES_ENV) sh scripts/build_pdf.sh $(DOC) $(TDIR) $@
else
	$(PANDOC) -d $(TDIR)/pdf.yaml $(SECTIONS) -o $@
endif

$(BUILD)/$(SLUG).tex: $(DEPS) | $(BUILD)
	$(PANDOC) -d $(TDIR)/pdf.yaml -s $(SECTIONS) -o $@

$(BUILD)/$(SLUG).docx: $(DEPS) | $(BUILD)
	$(PANDOC) -d $(TDIR)/docx.yaml $(SECTIONS) -o $@

$(BUILD)/$(SLUG).html: $(DEPS) | $(BUILD)
	$(PANDOC) -d $(TDIR)/html.yaml $(SECTIONS) -o $@

$(BUILD)/$(SLUG).txt: $(DEPS) | $(BUILD)
	$(PANDOC) -d $(TDIR)/txt.yaml $(SECTIONS) -o $@

wordcount: | $(BUILD)
	@$(PANDOC) --lua-filter filters/wordcount.lua -t plain $(SECTIONS) -o /dev/null

redline: | $(BUILD)
	@if [ -z "$(BASE)" ]; then echo "No version tag to compare against. Use Tag version in the app, or pass BASE=<ref>."; exit 1; fi
	$(RUN) python3 scripts/redline.py --doc $(DOC) --template $(TDIR) --base "$(BASE)" $(if $(BASE_DIR),--base-dir "$(BASE_DIR)",) \
	  --out $(BUILD)/redline-vs-$(subst /,-,$(patsubst $(SLUG)/%,%,$(BASE)))

import-edits: | $(BUILD)
	@if [ -z "$(FILE)" ]; then echo "Usage: make import-edits DOC=documents/<name> FILE=edits/marked-up.docx [APPLY=1]"; exit 1; fi
	$(RUN) python3 scripts/import_edits.py --doc $(DOC) "$(FILE)" $(if $(APPLY),--apply,)

app:
	python3 app/server.py

mac-app:
	python3 scripts/make_app.py

# The download for other people: distro/ReWord-<version>-mac-arm64.zip (empty data folder, never your work)
dist:
	python3 scripts/make_app.py --out build/dist-app --dist

# The tests use ReWord's own pandoc once `make mac-app` has unpacked it (or pandoc on the PATH).
check: test mac-check
	@echo "ReWord: all checks passed."

test:
	@for t in tests/test_*.py; do echo "== $$t"; python3 "$$t" || exit 1; done

mac-check:
	@command -v swiftc >/dev/null || { echo "mac-check needs a Mac with Xcode or its command-line tools"; exit 1; }
	@mkdir -p build/mac-check
	swiftc -O -target arm64-apple-macos12.0 -framework AppKit -framework WebKit app/mac/main.swift -o build/mac-check/ReWord-shell
	swiftc -O -target arm64-apple-macos12.0 -framework AppKit -framework WebKit -framework PDFKit app/mac/rwpdf.swift -o build/mac-check/rwpdf

watch:
	@command -v watchexec >/dev/null || { echo "Install watchexec (brew install watchexec)"; exit 1; }
	watchexec --watch documents --watch templates --watch filters --watch defaults --watch library \
	  --exts md,yaml,latex,lua,docx,json --debounce 1s -- $(MAKE) all DOC=$(DOC)

image:
	docker build --platform linux/amd64 -t $(IMAGE) docker

clean:
	rm -rf build
