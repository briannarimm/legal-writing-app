# How ReWord formats citations

ReWord stores each source once, as structured fields, and formats it three ways:

- **Bluebook, law review type**: for academic legal documents (the law review article template).
  Citations in footnotes use large and small caps for books, periodical titles, constitutions,
  court rules, Restatements, committee reports and state code names. Case names are roman in
  full footnote citations and italic in short forms.
- **Bluebook, practitioner type**: for briefs, memos and email. Italics only, with no small caps.
- **Chicago (18th edition)**, notes and bibliography: for the Chicago journal template. Full notes,
  shortened notes (Author, *Short Title*, page) once a full note has been given (final draft only;
  Chicago 18 prefers them to ibid.), and a Bibliography with the first author inverted.
- **Chicago (18th edition)**, author-date: for the Chicago author-date journal template. In-text
  (Walker 2017, 45) and narrative Walker (2017, 45) forms, and a References list with the year after
  the author.
- **APA 7th edition**: for the assignment and APA journal templates. It produces a reference-list entry and in-text
  forms, both parenthetical (Walker, 2017, p. 12) and narrative, Walker (2017). For legal
  materials, APA uses legal citation form, so ReWord gives the practitioner Bluebook form with
  the case name in italics.

The code is `app/citeformat.py`, and its checks are in `tests/test_citeformat.py`. Run them with
`python3 tests/test_citeformat.py`.

## Sources

- *The Indigo Book: A Manual of Legal Citation*, 2d ed. (2023 revision), indigobook.github.io.
  It is CC0 (public domain). The rule numbers below are Indigo rules.
  - **Table T19** maps citations to the law review typeface.
  - **Abbreviation tables** T11, T12.1, T15 and T18 are copied into `app/data/abbreviations.json`.
    ReWord uses them to suggest periodical and website abbreviations.
- The Indigo Book you linked (law.resource.org, 2016 beta) matches the Bluebook's 20th edition.
  The 2023 Indigo Book is newer, but it is not the current Bluebook. Check unusual sources
  against the Bluebook itself.
- APA 7: *Publication Manual of the American Psychological Association* (7th ed. 2020).
  The formatter was written from knowledge of the manual, not checked against the book.

## Covered

| Source type | Full | Short | Notes |
|---|---|---|---|
| Case | R11–R14: name, reporter, pin, court/year (court left out for U.S./S. Ct.), unreported (docket, WL/LEXIS, full date, `at *7`), parallel cite, weight-of-authority parenthetical, subsequent history (*aff'd*, *rev'd*… italicized automatically) | R15: *Short*, vol rep at pin. A government first party gives way to the other party (*Carmel*, *Raich*). | *Id.* (R15.3) |
| Statute | R16–R17: U.S.C. (year optional), named act, state codes (year), unofficial codes (publisher), session laws (Pub. L. No., Stat.), status (repealed) | Full form minus year and publisher (R17.5) | §§ only when the section field has an en dash, a comma or "to". A plain hyphen is part of many section numbers. |
| Regulation | R19: C.F.R. § / pt., Federal Register, proposed rules (to be codified at) | Same as full minus year | |
| Constitution | R23 | Full form (no supra) | |
| Court rule | R18.1 | Full form | |
| Restatement, U.C.C., model and uniform acts | R18.2–R18.4, with the publisher in the parenthetical | Full form | |
| Journal / law review article | R30.1–R30.3, student Notes and Comments, et al. for 3+ authors | Author, *supra* note N, at pin (R31.2) | Periodical abbreviation is automatic (T15, then T11/T12) unless typed. |
| Book | R28: volume, author(s), title, pin, editor/translator/edition/year | R29.2: Author, *supra*, at pin | Law review: author and title in small caps. Editor and edition stay roman. |
| Chapter | T19 form: author, *chapter*, in BOOK (eds., year) | supra | |
| Newspaper / magazine | R30.4: print (date, at page) or online (date, URL) | supra | |
| Web page | R33: author, *title*, site, (date, time), URL, (last visited) | R34: supra | |
| Report | Institutional author, title, number, (publisher date), URL | supra | |
| Bill / resolution | R21.1–R21.3: federal and state, enacted, status | Full form | |
| Hearing | R21.4 | supra (allowed for hearings) | |
| Committee report | R21.5 with Conf. Rep. and *as reprinted in* | `H.R. Rep. No. 117-27, at 5` | |
| Court filing / record | R24–R26: own-case documents with ECF No. and date; documents from other cases; R. at 22 | Same title + pin (R26) | *Id.* is not used for record cites. |
| Other | Typed by hand (Bluebook, APA, short form) | | |

Every citation also has **manual overrides** under "Exceptions" in the form (Bluebook full, short,
APA). They are for the source that the rules don't produce correctly.

## Chicago

Chicago uses the same fields as Bluebook and APA. Chicago 18 dropped the place of publication, so
nothing new is needed. Legal materials (cases, statutes, rules, regulations, the record…) follow legal
citation form in Chicago (CMOS 14.269 ff.), so ReWord uses the practitioner Bluebook form for them and
leaves them out of the bibliography and reference list. An "Other" source can have a typed Chicago note;
otherwise its Bluebook text is used. `chicago_gaps()` lists the optional fields Chicago uses that a source
lacks (a book's publisher, a journal's pages, a web page's date or access date); the citation form shows
them, and switching a document to a Chicago template reports them.

Not covered: ibid., season dates for journals (type the month), and the place of publication (optional
in Chicago 18). The formatter was written from knowledge of the manual, not checked against the book.

## Not covered (yet)

- Hereinafter for cases, or automatic hereinafter when one author has two works. You can type
  a short title.
- Case-name abbreviation (T11 words in case names) and whether a court belongs in the parenthetical
  for state reporters. Both are typed by the person.
- Treaties, foreign and international materials, tax materials (R20), agency adjudications (R19.3).
  Use "Other".
- APA: the a/b suffix for the same author and year (2020a, 2020b), group-author abbreviations, and
  the retrieval date for changing pages.
