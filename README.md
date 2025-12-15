# Anki Memo Timeline

AnkiWeb: https://ankiweb.net/shared/by-author/2117859718

A lightweight memo timeline panel for your current card, optimized for daily studying. Attach short free-text memos to each note (stored as JSON in a dedicated _MemoLog field) and review them later in a global, date-grouped timeline.

## Features
- Attach short memos to notes; memos stored in `_MemoLog` field as JSON
- Global timeline view grouped by date
- Fast, keyboard-friendly UI for quick note taking during reviews
- Designed to be used alongside the reviewer

## Installation
1. Tools → Add-ons → Open Add-ons Folder.
2. Place the add-on folder in your add-ons directory.
3. Restart Anki.
4. Ensure your note types have a `_MemoLog` text field (create one if missing).

## Usage
- While reviewing a card, open the Memo panel (toolbar or shortcut).
- Add or edit memos; use the timeline view from Tools → Memo Timeline.

## Configuration
`config.json` options:
- max_memo_length
- date format
- default field name for storing memos (default `_MemoLog`)

## Development
- Memos are saved as JSON inside the `_MemoLog` field: [{ "date": "...", "text": "..." }, ...].
- Take care when editing `_MemoLog` outside the add-on.

## Issues & Support
Report issues with Anki version and example `_MemoLog` contents.

## License
See LICENSE.
