# Pinned build image. Every build (your laptop and GitHub Actions) runs in here,
# so Pandoc and LaTeX output are identical everywhere.
#
# To upgrade Pandoc: change PANDOC_VERSION, rebuild, compare a PDF, commit.
# For a fully reproducible pin, replace the tag with its digest after the first
# pull:  docker inspect --format='{{index .RepoDigests 0}}' pandoc/latex:3.9.0.2
ARG PANDOC_VERSION=3.9.0.2
# pandoc/latex is published for Intel (amd64) only. The Makefile passes
# --platform linux/amd64, so Apple Silicon Macs run it under emulation:
# a little slower, same output.
FROM pandoc/latex:${PANDOC_VERSION}

# LaTeX packages the template needs beyond the base image.
# tlmgr must update itself before it will install anything.
RUN tlmgr update --self \
 && tlmgr install \
      titlesec enumitem footmisc setspace ulem xcolor \
      tex-gyre fontspec booktabs etoolbox microtype hyperref
RUN apk add --no-cache python3 git make

WORKDIR /data
ENTRYPOINT []
