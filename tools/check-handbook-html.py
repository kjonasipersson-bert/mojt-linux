#!/usr/bin/env python3
# Mojt Linux
# Copyright (C) 2026 Jonas Persson
# SPDX-License-Identifier: GPL-2.0-only
"""Check local links, anchors and assets in a generated mdBook website."""
import argparse
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.ids = set()
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.add(attrs['id'])
        for key in ('href', 'src'):
            if attrs.get(key):
                self.links.append(attrs[key])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    root = parser.parse_args().directory.resolve()
    pages = {p.resolve(): Page(p.read_text()) for p in root.rglob('*.html')}
    if root / 'index.html' not in pages:
        parser.error('missing generated index.html')
    errors = []
    count = 0
    for source, page in pages.items():
        for link in page.links:
            url = urlsplit(link)
            if url.scheme or url.netloc:
                continue
            path = unquote(url.path)
            target = ((root / path.lstrip('/')) if path.startswith('/') else
                      (source.parent / path) if path else source).resolve()
            if target.is_dir():
                target /= 'index.html'
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(f'{source.relative_to(root)}: missing local target {link}')
            elif url.fragment and target in pages and unquote(url.fragment) not in pages[target].ids:
                errors.append(f'{source.relative_to(root)}: missing anchor {link}')
            count += 1
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(pages)} HTML pages, {count} local links/assets/anchors; external URLs not fetched')


if __name__ == '__main__':
    main()
