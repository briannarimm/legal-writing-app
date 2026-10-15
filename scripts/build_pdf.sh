#!/bin/sh
# Multi-pass PDF build for briefs (they need page numbers in the tables).
# Runs inside the build image (or locally with USE_DOCKER=0), from the repo root.
#
#   sh scripts/build_pdf.sh <doc-dir> <template-dir> <out.pdf>
set -e
DOC="$1"; TDIR="$2"; OUT="$3"
DIR=$(dirname "$OUT"); JOB=$(basename "$OUT" .pdf)
SECTIONS=$(ls "$DOC"/[0-9]*.md | sort)
mkdir -p "$DIR"

# word count (for the certificate) -- same counting rules as `make wordcount`
WORDCOUNT_JSON="$DIR/words.json" pandoc -d defaults/common.yaml --metadata-file "$DOC/metadata.yaml" \
  --filter scripts/cites_filter.py --lua-filter filters/wordcount.lua -t plain $SECTIONS -o /dev/null 2>/dev/null
WORDS=$(python3 -c "import json,sys; print('{:,}'.format(json.load(open('$DIR/words.json'))['total']))")

pandoc -d defaults/common.yaml --filter scripts/cites_filter.py -d "$TDIR/pdf.yaml" --metadata-file "$DOC/metadata.yaml" \
  -M words="$WORDS" -s $SECTIONS -o "$DIR/$JOB.tex"

export TEXINPUTS="$DIR:"
tex() { xelatex -interaction=nonstopmode -halt-on-error -output-directory="$DIR" "$DIR/$JOB.tex" >"$DIR/$JOB.xelatex.log" 2>&1 \
  || { tail -40 "$DIR/$JOB.xelatex.log"; exit 1; }; }
tex                                  # pass 1: lays out the pages, records where authorities fall
python3 scripts/make_toa.py "$DIR" "$JOB"
tex                                  # pass 2: contents and authorities get their page numbers
tex                                  # pass 3: settle the table of contents' own page numbers
echo "Built $OUT ($WORDS words)"
