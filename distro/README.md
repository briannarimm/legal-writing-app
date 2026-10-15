# Download ReWord

This folder contains the ready-to-use ReWord program for Mac.

| File | Description |
|---|---|
| `ReWord-1.1.0-mac-arm64.zip` | The program. Download this file. |
| `ReWord-1.1.0-mac-arm64.zip.sha256` | The checksum of the zip file (optional check). |

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

1. Click `ReWord-1.1.0-mac-arm64.zip` in the file list above.
2. Click **View raw** or the **Download raw file** button (the arrow icon, top right of the
   file view). The download starts. The file is about 90 MB.
3. Open your Downloads folder. Double-click the zip file. A folder named `ReWord` appears.
4. Move the `ReWord` folder to the location you want: your Documents folder, Applications, or a
   USB drive. Keep `ReWord.app` and `ReWord Data` together in that folder.
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
shasum -a 256 -c ReWord-1.1.0-mac-arm64.zip.sha256
```

The result must be `ReWord-1.1.0-mac-arm64.zip: OK`. If the result is different, delete the file
and download it again.

## Your data

The download contains an empty `ReWord Data` folder. ReWord saves your documents, notes and
sources in that folder. ReWord does not send your work to the internet unless you connect GitHub
(see section 10 of the [main README](../README.md)).

To update ReWord, replace only `ReWord.app`. Do not replace or delete `ReWord Data`.

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
