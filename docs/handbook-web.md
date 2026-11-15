<!--
Mojt Linux
Copyright (C) 2026 Jonas Persson
SPDX-License-Identifier: GPL-2.0-only
-->

# Building the handbook website

The handbook is built with **mdBook 0.5.4**, using the existing Markdown under
`doc/handbook/`. `book.toml` supplies the title/output settings; `SUMMARY.md`
defines the sidebar and reading order. No custom theme or preprocessor is needed.

## Build and preview

Install mdBook from its [upstream releases](https://github.com/rust-lang/mdBook/releases/tag/v0.5.4).
The handbook CI pins the Linux x86-64 archive and its SHA256. That checksum fixes
which downloaded bytes CI uses; it is not an independent publisher signature.
Python 3.11+ runs the local-link checker. From the repository root:

```sh
mdbook build doc/handbook
python3 tools/check-handbook-html.py build/handbook
mdbook serve doc/handbook --hostname 127.0.0.1 --port 3000
```

Open `http://127.0.0.1:3000/`. The development server rebuilds on edits.
The generated site is under `build/handbook/` and is ignored by Git.
The checker verifies local HTML destinations, fragment IDs and referenced assets;
it does not fetch external links or execute browser JavaScript.

Existing chapters already include numbers, so automatic numeric section labels
are disabled. Keep both the book's contents page and `SUMMARY.md` current when
adding chapters. Missing summary files fail the build instead of being created.
mdBook supplies search, previous/next navigation and an HTML print view.
Small HTML redirects preserve source-style `README.md` links because mdBook
renders those chapters as `index.html`.

The handbook's chapters link to each other within the generated site. References
to technical `docs/` documents and roff manual sources explicitly link to GitHub's
`main` branch; those references are not generated as part of this book. They
are supplementary source links, not dependencies needed to serve the handbook.

## Hosting target: handbook.mojt.org

The site is configured for the root URL `https://handbook.mojt.org/`, rather than
a `/handbook/` subdirectory. The generated `CNAME` records that intended hostname;
it does not configure DNS, provisioning or HTTPS.

The `Handbook` GitHub Actions workflow builds/checks the site and retains a
`mojt-handbook-html` artifact on relevant PRs, main pushes and manual runs.
It does not deploy or change DNS. Download/extract that artifact to obtain the
same static site, including its locally served fonts, scripts and search index.

Once a host is chosen, publish the **contents** of `build/handbook/` as the web
root, point `handbook.mojt.org` at the host using its required DNS records and
enable HTTPS there. Preserve paths and serve `index.html` for directory requests.
Any ordinary static host can serve the output; Rust, mdBook, Python and a database
are not required on the serving host. Automatic upload/deployment can be added
once a hosting destination has been selected.
