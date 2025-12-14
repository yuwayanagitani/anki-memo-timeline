# Memo Timeline Panel — Lightweight memo timeline for the current card

A lightweight memo timeline panel for your current card, optimized for daily studying.  
This add-on lets you attach short free-text memos to each note (stored as JSON in a dedicated `_MemoLog` field) and review them later in a global, date-grouped timeline. It is designed to be used side-by-side with Anki's reviewer.

---

## Key features

- Attach short memos to the current note/card and keep multiple memos in time order.
- Memos stored in each note's `_MemoLog` field as JSON.
- Global timeline view grouped by date (YYYY-MM-DD), making it easy to review recent notes and trends.
- Lightweight UI intended not to interfere with review flow.
- Data format is simple and extensible for future search/filter features.

---

## Supported environment

- Designed for Anki 2.1.x (Python 3). Behavior may vary with different Anki versions or API changes.
- This repository is implemented in Python.

---

## Installation

1. Close Anki.
2. Open Anki → Tools → Add-ons → Browse add-ons folder.
3. Download this repository (ZIP) and extract the folder into your Anki add-ons directory. Name the folder as you like (example: `memo_timeline_panel`).
4. Restart Anki.

Note: Future releases may provide an official installation ID or packaging for the Anki add-on manager.

---

## Quick usage

- When reviewing, a timeline panel appears next to the reviewer (toggleable in settings).
- Add a memo for the current note using the panel's input. Each memo is saved into the note's `_MemoLog` field.
- Open the timeline view to see memos grouped by date and browse your memo history across notes.

Refer to the add-on settings for toggles, display options, and any keyboard shortcuts (if provided).

---

## Data format — `_MemoLog` field (JSON)

The add-on stores an array of memo objects as a JSON string inside the `_MemoLog` field of each note. Example:

```json
[
  {
    "id": "20251214T091523_1",
    "created_at": "2025-12-14T09:15:23Z",
    "author": "yuwayanagitani",
    "text": "This term is tricky — review pronunciation.",
    "tags": ["pronunciation","review"]
  },
  {
    "id": "20251130T203000_1",
    "created_at": "2025-11-30T20:30:00Z",
    "author": "yuwayanagitani",
    "text": "Pay attention to the example sentence.",
    "tags": []
  }
]
```

Field descriptions:
- id: unique memo identifier (e.g., timestamp + counter).
- created_at: ISO 8601 UTC timestamp.
- author: optional username or identifier of the memo author.
- text: short free-text memo body.
- tags: optional array of tags for categorization or filtering.

Notes:
- If a note does not have `_MemoLog`, the add-on can detect and create/initialize the field (behavior depends on settings).
- Back up your collection before making large changes to note fields.

---

## Settings (example / configurable options)

(Actual available settings depend on implementation. The following are typical configurable items.)
- Toggle timeline panel visibility.
- Maximum memo length.
- Date format for display.
- Automatic JSON backup frequency for `_MemoLog` data.
- Option to create `_MemoLog` field automatically if missing.

You can find and change settings from Anki → Tools → Add-ons → (select this add-on) → Configure.

---

## Developer notes

Development / debugging:
1. Clone the repository.
2. Place the repo folder into Anki's add-ons directory (or create a symlink for live development).
3. Start Anki and test behavior in the reviewer.
4. Use logging and Anki's debug console to troubleshoot.

Testing:
- There are no automated tests included by default. Consider adding pytest-based unit tests for JSON read/write and UI behavior.

Coding style:
- Follow PEP8 and idiomatic Python. Keep UI code and data handling separate where possible.

---

## Troubleshooting

- Panel does not appear:
  - Restart Anki.
  - Ensure the add-on folder is placed correctly in the add-ons directory.
- Memos are missing or JSON parse errors:
  - Inspect the `_MemoLog` field for malformed JSON. Restore from backup if needed.
  - The add-on will avoid overwriting malformed data; correct the field manually if required.
- If you encounter errors, please include error messages or console logs when reporting an issue.

Data recovery:
- If `_MemoLog` JSON is corrupted, edit the field to fix the JSON structure or restore from your collection backup.

---

## Contributing

Contributions, bug reports, and feature requests are welcome. Please open an issue before submitting larger pull requests.

Guidelines:
- Use descriptive titles and commit messages.
- Keep changes small and focused.
- Include screenshots and reproduction steps when relevant.

---

## License

Specify the license for this project (e.g., MIT). Please include a LICENSE file in the repository.

Example:
MIT License — see LICENSE file for details.

---

## Author / Contact

- Author: yuwayanagitani  
- Repository: https://github.com/yuwayanagitani/2117859718

---

If you want, I can:
- Add screenshots and example UI mockups,
- Include detailed keyboard shortcuts and exact setting keys,
- Provide a CHANGELOG or release notes template,
- Translate back into Japanese or other languages.

Tell me which additions you prefer and I’ll update the README accordingly.
