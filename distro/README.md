# Download ReWord

This folder contains the ready-to-use ReWord program for Mac.

| File | Description |
|---|---|
| `ReWord-1.1.4-mac-arm64.zip` | The program. Download this file. |
| `ReWord-1.1.4-mac-arm64.zip.sha256` | The checksum of the zip file (optional check). |

## What's new in 1.1.4

- **One button.** **Save** (⌘S) now saves, builds the open document, copies its finished files into
  `outputs/`, and syncs with GitHub. The separate Run, Publish and Sync buttons and the Publish tab
  are gone.
- **View → Files** opens the data folder (the folder that is your GitHub repository), the
  repository on GitHub, and the backup folder.

## What's new in 1.1.3

- **You choose when a file changed in two places.** ReWord gets GitHub's changes when it starts and
  keeps everything. If the same file was changed on this Mac and on GitHub, ReWord asks you to keep
  this Mac's version, GitHub's, or both.
- **Automatic backups.** After every successful sync, ReWord copies your work into
  `~/Library/Application Support/ReWord Backup`, a plain folder that is not on GitHub. The Publish
  tab shows where it is; **Show backups** opens it in Finder (in 1.1.4: **View → Files**).

## What's new in 1.1.2

- **Your work is in one place.** ReWord keeps your documents, research, sources and finished files
  in `~/Library/Application Support/ReWord`, in one folder and one git repository. The first time
  1.1.2 starts, it copies your existing `ReWord Data` folder there and leaves the original
  untouched. **Publish → Show data folder** opens it in Finder.
- **Safer syncing.** ReWord syncs with GitHub every 10 minutes while it is open (as well as on
  open, after Run and on quit). It recovers from an interrupted sync, and it joins histories that
  don't share a start instead of refusing, so changes made on GitHub are never left behind.

## What's new in 1.1.1

- **Attach PDF… works in the Mac app.** The **Attach PDF…** button in Citations now opens a file
  chooser so you can pick the PDF.
- **A right-click menu that fits what you click.** Text, citations, footnotes, the document tree,
  research notes, the citation library and the PDF reader each have their own menu. Hold Option
  while you right-click to see the standard Mac menu.

## What's new in 1.1

- **Change a document's template.** Open **Details** and choose another template, for example to
  turn a law review article into an APA assignment. Citations convert to the new style automatically.
  See section 7.1.1 of the [main README](../README.md).
- **Journal submission templates** in APA 7th, Chicago notes and bibliography, and Chicago author-date.
- **Chicago style** for every source in your library, also available in the annotated bibliography
  and as a project's citation style.

## Requirements

- A Mac with Apple Silicon (M1 or newer). To check: Apple menu > About This Mac. "Chip" must
  show "Apple M…". ReWord does not run on Intel Macs, Windows or Linux.
- macOS 12 (Monterey) or newer.
- About 400 MB of free space.

You do not need other software. ReWord contains its own copies of Python, Pandoc and a TeX engine.

## Install

1. Click `ReWord-1.1.4-mac-arm64.zip` in the file list above.
2. Click **View raw** or the **Download raw file** button (the arrow icon, top right of the
   file view). The download starts. The file is about 90 MB.
3. Open your Downloads folder. Double-click the zip file. A folder named `ReWord` appears.
4. Move `ReWord.app` to your Applications folder, or the whole `ReWord` folder to a USB drive.
5. Double-click `ReWord.app`.

### If macOS says it cannot verify the app

ReWord is not signed with a paid Apple Developer certificate. Thus, macOS shows a warning the
first time you open it.

1. Click **Done** (or **Cancel**) in the warning.
2. Open **System Settings > Privacy & Security**.
3. Scroll to the message about ReWord. Click **Open Anyway**.
4. Enter your Mac password if macOS asks for it. Click **Open**.

On macOS 14 and older, you can also right-click `ReWord.app`, select **Open**, then click **Open**.

You do this one time only.

## Check the download (optional)

Open Terminal, go to the folder that contains the zip file, and run:

```bash
shasum -a 256 -c ReWord-1.1.4-mac-arm64.zip.sha256
```

The result must be `ReWord-1.1.4-mac-arm64.zip: OK`. If the result is different, delete the file
and download it again.

## Your data

ReWord saves your documents, notes, sources and finished files in
`~/Library/Application Support/ReWord`. **View → Files → Data folder** opens it. When ReWord runs
from a USB drive, it uses a `ReWord Data` folder next to the app instead. ReWord does not send your
work to the internet unless you connect GitHub (see section 10 of the
[main README](../README.md)).

To update ReWord, replace only `ReWord.app`. Your data folder is not touched.

## Licenses

ReWord is MIT-licensed (code) and CC BY 4.0 (documentation). See [LICENSE](../LICENSE).
The program bundles third-party software under its own licenses, including Pandoc (GNU GPL).
The file `THIRD-PARTY NOTICES.txt` in the download lists each program, its version, its license
and the location of its source code.

## For maintainers: make a new download

1. Change `VERSION` in `scripts/make_app.py`.
2. Run `make dist` on an Apple Silicon Mac with the Xcode command line tools.
3. Delete the old zip and checksum files from this folder. Commit the new ones.

The zip must stay smaller than 100 MB. GitHub refuses larger files in a repository. If the zip
becomes larger, attach it to a GitHub Release instead.
