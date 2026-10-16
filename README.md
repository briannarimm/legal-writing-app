# ReWord

ReWord is a writing application for legal and academic documents. You write in an editor that
looks like a word processor. ReWord makes the finished PDF and Word files. It also keeps your
research notes and your source library in the same place.

ReWord runs on Apple Silicon Macs (M1 or newer). It does not need an internet connection to make
documents. It does not need other software on the computer.

**To download ReWord, go to the [distro](distro/) folder.**

> **Note: this application is vibe-coded.** An AI coding assistant (Claude Code, by Anthropic) wrote
> almost all of the code and documentation. The owner of this repository supplied the requirements,
> the legal-writing knowledge, the decisions and the testing, but did not write the code by hand.
> Thus, examine the code before you depend on it. Do not use ReWord as your only copy of important
> work. Make sure that each citation and court rule agrees with the official sources.

## Contents

1. [What ReWord does](#1-what-reword-does)
2. [Requirements](#2-requirements)
3. [Install ReWord](#3-install-reword)
4. [Start and stop ReWord](#4-start-and-stop-reword)
5. [The three work areas](#5-the-three-work-areas)
6. [Projects](#6-projects)
7. [Documents](#7-documents)
8. [Sources and citations](#8-sources-and-citations)
9. [Research notes](#9-research-notes)
10. [Finished files and GitHub](#10-finished-files-and-github)
11. [Keyboard shortcuts](#11-keyboard-shortcuts)
12. [Use ReWord from a USB drive](#12-use-reword-from-a-usb-drive)
13. [Troubleshooting](#13-troubleshooting)
14. [For developers](#14-for-developers)
15. [Limits](#15-limits)
16. [License](#16-license)

## 1. What ReWord does

| Function | Description |
|---|---|
| Write | Write in a rich-text editor with italics, bold, small caps, headings, lists, block quotes and footnotes. |
| Format | Make a formatted PDF and Word file from a template. The **Save** button (⌘S) does this. |
| Cite | Keep each source one time in a library. ReWord formats the source in Bluebook or APA 7 style. |
| Shorten citations | Make a final draft that uses *Id.*, short forms and *supra* where the rules permit them. |
| Compare versions | Save a version. Make a "redline" that shows the changes since that version (Word tracked changes and a color PDF). |
| Research | Keep notes, attach PDFs of sources, and highlight and comment on them. |
| Group | Put documents, notes and sources into projects. |
| Back up | Send your work to a private GitHub repository (optional). |

Templates:

| Template | Output |
|---|---|
| Law review article | PDF and Word. Double spacing, footnotes, law review citation typeface. |
| Assignment (APA 7th) | PDF and Word. Title page, APA headings, automatic References page. |
| Journal submission (APA 7th) | PDF and Word. Professional title page with running head and author note, abstract and keywords, automatic References page. |
| Journal submission (Chicago notes) | PDF and Word. Title page, footnotes in Chicago notes-and-bibliography style (shortened notes in the final draft), automatic Bibliography. |
| Journal submission (Chicago author-date) | PDF and Word. Title page, in-text citations like (Walker 2017, 45), automatic References list. |
| Annotated bibliography | PDF and Word. Sorted entries in APA, Bluebook or Chicago style, each with an annotation. |
| Legal memo | PDF and Word. MEMORANDUM header, standard memo sections. |
| Federal appellate brief | PDF and Word. Cover, tables of contents and authorities, certificates. |
| Missouri appellate brief | PDF and Word. Cover, tables, points relied on, certificates. |
| Email | HTML and plain text. Copy to the clipboard with formatting. |

> **Caution:** The brief templates follow the court rules as the author understood them. Rules change.
> Compare each brief with the current rules of the court before you file it.

## 2. Requirements

| Item | Requirement |
|---|---|
| Computer | Mac with Apple Silicon (M1 or newer). Intel Macs and Windows are not supported. |
| Operating system | macOS 12 or newer. |
| Disk space | Approximately 450 MB for the application, plus your work. |
| To build the application | Xcode Command Line Tools (`xcode-select --install`) and an internet connection, one time. |
| GitHub backup (optional) | `git` and the GitHub command-line tool `gh`, with a GitHub sign-in. |

## 3. Install ReWord

There are two methods to install ReWord.

### 3.1 Download the application (recommended)

Download the zip file from the [distro](distro/) folder. Then do the steps in
[distro/README.md](distro/README.md).

### 3.2 Build the application from the source code

Build the application one time from this folder.

1. Open Terminal.
2. Go to this folder.
3. Type this command and push Return:

   ```bash
   python3 scripts/make_app.py
   ```

4. Wait until the command shows `Built …/ReWord.app`. The first build downloads Python, Pandoc and a
   TeX engine, and takes some minutes.

The command makes this folder in your home folder:

```
ReWord/
  ReWord.app          the application
  READ ME FIRST.txt
```

Your work is kept in `~/Library/Application Support/ReWord`: documents, notes, sources, attached
PDFs and finished files, all in one folder. **View → Show Data Folder in Finder** (or **File → Open Data
Folder**) opens it in Finder. ReWord 1.1.2 copies the folder that earlier versions used
(`ReWord Data`) to this location the first time it starts. It does not delete the old folder; it
leaves a note in it that says where your work went.

To copy existing work from this folder into the new data folder, add `--import-data .` to the command.
The command copies files. It does not move or delete them.

## 4. Start and stop ReWord

- To start ReWord, double-click `ReWord.app`.
- To stop ReWord, push ⌘Q. ReWord saves your work before it closes.

ReWord saves automatically approximately 1.5 seconds after you stop typing. To save immediately, push ⌘S.

## 5. The three work areas

The window has three parts:

- **The sidebar** on the left: Writing, Research and Citations, the project menu, and the list for
  the current work area (documents, notes or sources). ⌥⌘S hides or shows it.
- **The toolbar** at the top: Save, formatting, Cite, Footnote, and the layout (Editor, Split,
  Preview). In Research and Citations it also has that area's commands.
- **The inspector** on the right (⌥⌘I, or the button at the right end of the toolbar): the open
  document's template, project, version and word count, Final draft, Details, the finished files,
  and a **Files** tab with the data folder, GitHub and backups.

Use the sidebar to change the work area.

| Tab | Shortcut | Contents |
|---|---|---|
| Writing | ⌘1 | Your documents. Each document has sections. |
| Research | ⌘2 | Your notes. Each note can link to a source. |
| Citations | ⌘3 | Your source library, with attached PDFs and highlights. |

The Mac menu bar has everything else: **Insert** (citation, footnote, section, new document, note
or citation), **Format** (bold, italic, small caps, lists, block quote) and **View** (layout, rich
text or Markdown, Files, **Appearance**: Light, Dark, or Dark with a white page). ⌘K searches every
command, and ⌘/ lists the keyboard shortcuts.

## 6. Projects

A project groups the documents, notes and sources for one item of work, for example a paper, a case
or a class.

### 6.1 Make a project

1. Click the project menu in the sidebar, then **New project…**.
2. Type a name.
3. Select a color.
4. (Optional) Type a description.
5. (Optional) Select a default template and a citation style.
6. (Optional) Name your highlight colors (see section 8.4).
7. Click **Create project**.

### 6.2 Select a project

Use the project menu in the sidebar.

| Selection | Result |
|---|---|
| A project | Each tab shows only the items in that project. New items go into that project. |
| All projects | Each tab shows all items, in groups below the project names. |
| No project | Each tab shows only the items that are not in a project. |

### 6.3 Project rules

- A document or a note is in one project, or in no project.
- A source can be in more than one project.
- When you cite a source in a document or note that is in a project, ReWord adds the source to that
  project. ReWord marks this addition "auto".
- ReWord does not remove a source from a project automatically. To remove it, click × on the project
  in the source form.
- To move a document or note, drag it to a project name in the All projects view. You can also use
  its **Project** menu.
- When you delete a project, its documents, notes and sources stay. They are then in no project.

## 7. Documents

### 7.1 Make a document

1. Click **+ New document**.
2. Select a template.
3. Type a title.
4. Click **Create**.

The new document contains sample sections. Replace the sample text with your text.
The **Details** section contains the title page or header data, for example the court and the parties.

### 7.1.1 Change a document's template

Open **Details** and choose another **Template**, for example to turn a law review article into an APA
assignment. ReWord converts the document:

- Citations take the new template's style. Where the new style puts them somewhere else, they move:
  footnotes that hold only citations become in-text citations (APA, Chicago author-date) or citation
  sentences (memos, briefs), and in-text citations become footnotes (law review, Chicago notes).
  Footnotes that also say something stay footnotes.
- The References or Bibliography section is renamed, added or removed to fit the new template.
- The details are rebuilt from the new template, with the title, authors and abstract carried over.
  The old details stay below them as comments.
- A copy of the files as they were goes to the document's `_trash` folder.

When the new template uses Chicago style, ReWord lists any sources that are missing details Chicago
uses (for example a book's publisher). They still format; add the details in **Citations** when you can.
An annotated bibliography can't switch templates.

### 7.2 Write

| Task | Command |
|---|---|
| Italic, bold, small caps | ⌘I, ⌘B, ⇧⌘K |
| Heading 1 to 4 | ⌥⌘1 to ⌥⌘4 |
| Body text | ⇧⌘N |
| Bulleted list, numbered list | ⇧⌘L, ⇧⌘7 |
| Block quote | ⌥⌘Q |
| Footnote | ⌥⌘F |
| Citation | ⌃⌘C |
| Edit the Markdown text | View → Markdown (⌃⌘M) |
| Editor and preview side by side | View → Editor and Preview (⌃⌘2) |

### 7.3 Make the finished files

1. Click **Save** (⌘S). Save also builds the document, copies its finished files into `outputs/`, and
   syncs with GitHub.
2. Wait until the Preview tab shows the PDF.
3. Use the links above the preview to download the PDF or Word file.

### 7.4 Make a final draft

The draft shows each citation in full. A final draft uses short citation forms.

1. Click **Final draft** (⌥⌘D). The button stays on for this document.
2. Click **Save** (⌘S).
3. In the Preview tab, select **Final** in the **Viewing** menu.

### 7.5 Compare versions

1. Click **Tag version** (⇧⌘T) when you send a draft to another person.
2. Continue to write.
3. Click **Save** (⌘S). ReWord makes a redline against the last version: a Word file with tracked changes and
   a PDF with blue insertions and red deletions.

## 8. Sources and citations

### 8.1 Add a source

1. Go to the Citations tab.
2. Click **+ New citation**.
3. Do one of these steps:
   - Paste a DOI, an ISBN or a web address into **Look up**, then click **Look up**. ReWord fills in
     the fields.
   - Select the type of source, then type the data in the fields.
4. Examine the formatted citations in **How it will look**. Correct the fields if necessary.
5. Click **Create citation**.

> **Note:** Data from **Look up** can be incomplete. Always examine it.

ReWord shows each source in four forms: Bluebook in law review typeface, Bluebook for briefs and
memos, the Bluebook short form, and APA 7. The rules come from *The Indigo Book* (2nd ed., 2023
revision). The file `docs/citation-rules.md` lists the source types and rules that ReWord supports.
For a source that the rules do not format correctly, type the citation in **Exceptions**.

### 8.2 Cite a source

1. Put the cursor where the citation goes.
2. Push ⌃⌘C (Cite…).
3. Select the source and click **Insert** (or **In-text** or **Narrative** for APA).

The citation shows as a tinted "chip". To add a pin cite, a signal or a parenthetical, click the chip.
If you change a source in the library, all chips for that source change.

- In a law review article, a citation in the main text goes into a new footnote.
- In a brief, ReWord adds each authority to the table of authorities.
- In an APA document, ReWord adds each source to the References page.

### 8.3 Attach and annotate a PDF

1. Select a source in the Citations tab.
2. Do one of these steps:
   - Click **Attach PDF**, or drag a PDF onto the reader.
   - Click **Snapshot** to save the source's web page as a PDF.
3. Select text in the reader.
4. Click a color to highlight the text.
5. To add a comment, click the highlight.

ReWord keeps highlights in a separate file next to the PDF. It does not change the PDF. To make a copy of
the PDF with the highlights in it, click **Export annotated**.

### 8.4 Highlight colors and labels

There are twelve highlight colors. You can give each color a label, for example *Holding*, *Dicta*
or *Quote to use*:

1. Open the project menu in the sidebar and click **Manage projects…** (or make a new project).
2. Under **Highlight labels**, type a label next to each color you use.
3. Click **Save**.

The labels are shared by all your projects and are kept in `library/highlights.json`, so they sync
with your library. The color bar in the reader and the highlight list show the labels.

## 9. Research notes

1. Go to the Research tab.
2. Click **+ New note**.
3. Type a title and a topic.
4. Select the source: a new source, an existing source, or no source.
5. Click **Create note**.

The page view at the right shows the note as it will print. To save the note as a file, click
**Export PDF** or **Export Word**.

## 10. Finished files and GitHub

All your work is one folder and one GitHub repository, which must be private: documents, notes,
sources, attached PDFs, highlights, and the finished PDF and Word files in
`outputs/<project>/<document>/`. One button does everything: **Save** (⌘S) saves, builds
the open document, copies its finished files into `outputs/`, and syncs with GitHub (outside
Writing, it saves and syncs). A small panel under Save shows each step as it happens. **View →
Files** in the menu bar opens the data folder (the folder that is your GitHub repository), the
repository on GitHub, and the backup folder.

ReWord also syncs by itself when it starts, every 10 minutes while it is open, and when you quit. Each sync saves a commit, takes GitHub's changes, then pushes. Files that changed on
only one side are simply combined, and a file deleted on one side but changed on the other is kept.

If the same file changed both on this computer and on GitHub, this computer's version stays in
place and ReWord asks what to keep for each file: **Keep this Mac's**, **Keep GitHub's**, or **Keep
both** (GitHub's version is added as a copy whose name ends in `-github`). **Decide later** keeps
GitHub's version aside until the next start. The same applies when the two histories have no common
start (for example, after the data folder was set up again).

### 10.2 Backups

After every successful sync, ReWord copies new and changed files into a backup folder beside the
data folder: `~/Library/Application Support/ReWord Backup`. The backup is not a git repository and
is never uploaded. Files deleted from your data folder stay in the backup. The inspector's **Files**
tab shows where the backup is and when it was last updated; **Backups** (or **View → Show Backups in
Finder**) opens it.

Data folders from before 1.1.2 kept the finished files in a separate git repository inside
`outputs/`. On the first start, ReWord merges that history into your work repository and keeps the
old repository in `.git/reword-outputs-repo`. If you chose your own output folder (**Change…**), it
stays a separate repository with its own **Connect…** button.

If Claude or another person edits your work from a clone, they should work on a branch and open a
pull request instead of changing `main` or the data folder directly. ReWord pulls the merged
result on its next sync.

### 10.1 Set up GitHub (one time)

1. Open Terminal.
2. Type `brew install gh` and push Return.
3. Type `gh auth login` and push Return.
4. Select **GitHub.com** and **HTTPS**, then follow the instructions.
5. In ReWord, open the inspector's **Files** tab and click **Connect…**.

ReWord does not ask for or keep passwords or tokens. It uses the sign-in that `gh` keeps on the Mac.

### 10.2 Sync

When the work folder connects to GitHub, ReWord syncs it automatically:

- when ReWord starts,
- after each Run,
- when ReWord stops.

If the same lines changed on two computers, ReWord keeps the version on this computer. The other version
stays in the GitHub history.

> **Warning:** GitHub keeps copies of all files that you sync. Do not sync client material unless your
> professional duties and policies permit it.

## 11. Keyboard shortcuts

- Push ⌘/ to see all shortcuts.
- Push ⌘K to search all commands, documents, notes and sources.
- Right-click anything for the commands that fit it. In your text: spelling suggestions, Cut, Copy,
  Paste, italic, bold, small caps, paragraph styles, and Insert citation or footnote. On a live
  citation: edit, open, copy or remove it. On a document, section, note or source in a side bar: open,
  rename, move to a project, move up or down, copy a citation in any style, or delete. In the PDF
  reader: highlight the selected text in a color, comment, or copy it as a quote. Hold ⌥ Option while
  you right-click to get the standard Mac menu instead.

Most text shortcuts are the same as in Microsoft Word for Mac.

## 12. Use ReWord from a USB drive

1. Copy the full `ReWord` folder to the drive.
2. On the other Mac, double-click `ReWord.app` on the drive.
3. If macOS asks for permission to use files on the drive, click **Allow**.

When ReWord runs from a drive (anything under `/Volumes`), your work stays in `ReWord Data` next
to the app on the drive instead of in Application Support.

- Before you remove the drive, stop ReWord (⌘Q). Then eject the drive in Finder.
- The drive can contain the only copy of your work. Make a backup regularly.
- Use the APFS or Mac OS Extended format for the drive if possible. exFAT also operates correctly.

## 13. Troubleshooting

| Problem | Cause | Action |
|---|---|---|
| macOS says it cannot verify the application. | The application came from a download or AirDrop. | Right-click `ReWord.app`. Click **Open**. Click **Open** again. |
| **Save** says the build failed. | An error in the document or template. | Open the **Run log** tab. Read the last lines. |
| A citation shows `[missing citation: …]`. | The source is not in the library. | Add the source, or remove the citation. |
| **Sync** says "offline". | The Mac has no `git`, no GitHub sign-in, or no internet connection. | Work continues. Sync again on a Mac that is set up for GitHub. |
| **Look up** fails. | The site does not permit automatic access. | Type the data in the fields. |
| Other problems | | Click **File → Show Log**. The log is `~/Library/Logs/ReWord.log`. |

## 14. For developers

### 14.1 Structure

```
app/                 server (Python standard library) and user interface (HTML, CSS, JavaScript)
app/mac/             native Mac window and PDF helper (Swift)
app/citeformat.py    Bluebook and APA formatter
app/cites.py         resolves live citations (draft and final forms)
templates/<id>/      one folder for each template (LaTeX, Word styles, sample sections)
filters/             Pandoc Lua filters
scripts/             application build, redline, editor import, table of authorities
docs/                citation-rules.md
tests/               automated tests
docker/              pinned build image (Pandoc 3.9.0.2 with LaTeX)
distro/              the downloadable application (zip) and its instructions
documents/           documents (one folder each; not committed)
research/            research notes (not committed)
library/             citations and attached files (not committed)
projects/            projects (not committed)
```

This repository contains the program only. Git ignores the data folders (`documents/`, `research/`,
`library/`, `projects/`) in the source folder, so personal work is not published with the code.
Keep your work in the application's data folder (`~/Library/Application Support/ReWord`).

### 14.2 Run from the source folder

```bash
python3 app/server.py
```

This command opens ReWord in a web browser. Builds then use Docker (`make`) unless Pandoc and Tectonic
are available. Use `--root DIR` to use a copy of the data.

### 14.3 Tests

```bash
python3 tests/test_citeformat.py
python3 tests/test_cites.py
python3 tests/test_projects.py
```

`tests/test_cites.py` needs Pandoc. It uses the Pandoc in the application build cache if it is present.

### 14.4 Command-line builds

| Command | Result |
|---|---|
| `make DOC=documents/<name>` | Build the document. |
| `make DOC=documents/<name> FINAL=1` | Build the final-draft forms. |
| `make redline DOC=documents/<name>` | Make a redline against the last version. |
| `make import-edits DOC=… FILE=edits/marked.docx` | Report the tracked changes and comments in an editor's Word file. |
| `make mac-app` | Build the stand-alone application in `~/ReWord`. |
| `make dist` | Build the download for other people (`distro/ReWord-<version>-mac-arm64.zip`). The zip has an empty data folder. It never contains your work. |

## 15. Limits

- Citation forms were compared with the examples in *The Indigo Book*, not with *The Bluebook* or the
  APA manual. Examine unusual sources.
- The Word versions of the templates were not examined in Microsoft Word.
- A table of authorities is in the PDF only. The Word brief has a table of contents only.
- **Snapshot** saves the page that a signed-out browser sees. For a page behind a login or a paywall,
  attach a PDF instead.
- ReWord cannot import editors' Word changes from inside a citation, because ReWord builds each citation
  from the library.
- A paragraph that is both rewritten and moved can show as a deletion and an insertion in a redline.

## 16. License

- Software: MIT License.
- Documentation: Creative Commons Attribution 4.0 International (CC BY 4.0).
- Third-party components (PDF.js, Indigo Book tables, and the tools in the application build) keep
  their own licenses. The download in `distro/` contains `THIRD-PARTY NOTICES.txt`, with the location
  of the source code of each bundled program.

See [LICENSE](LICENSE) for the full text.
