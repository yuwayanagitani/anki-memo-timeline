# 📝🕒✨ Card Memo Panel (Anki Add-on)

**Card Memo Panel** lets you attach quick memos to your cards while you study—then view **all memos across your entire collection** in a clean, scrollable **global timeline**.

It’s designed to run *alongside* normal reviews: keep studying, jot notes fast, and find them later.

---

## 🌟 Key Features

### ✅ Save memos per note (stored inside the note)
- Memos are saved as JSON into a dedicated field:
  - **`_MemoLog`**
- Each memo entry stores:
  - timestamp (`ts`)
  - text (`text`)

### 🧭 Global Memo Timeline (all notes)
- Displays **every memo from every note** in one timeline list
- Inserts a **date header** for each day (date only; no time)
- Double-click a memo → opens **Browser** and jumps to the note

### 🔎 Filters
Filter timeline by:
- **All**
- **Today**
- **Last 7 days**
- **Last 30 days**
- **Custom range (From / To)**

### ✍️ Add memos while reviewing
- Bottom input area adds a memo to the **current Reviewer card**
- Shortcut:
  - **Ctrl+Enter** / **Ctrl+Return** → add memo

### 🗑️ Edit / Delete memos
- Right-click a memo entry:
  - **Edit this memo**
  - **Delete this memo**
- Or select a memo and press:
  - **Delete** key → delete memo

### 📤 Export
Export the currently-filtered timeline:
- **Export TXT**
- **Export HTML**

### 🔍 Zoom (font size)
In the memo list or input box:
- **Ctrl + mouse wheel** (or **⌘ + wheel** on macOS) to change font size
- Range: 8–24 pt

---

## 🚀 How to Use

### 1) Add the required field to your note type
This add-on requires your note type to have a text field named:

- **`_MemoLog`**

If it’s missing, you’ll see a warning telling you to add it.

**How to add it:**
1. Open Anki
2. Go to **Tools → Manage Note Types**
3. Select your note type
4. Click **Fields…**
5. Add a new field named exactly: **`_MemoLog`**
6. Save

> The add-on won’t create the field automatically—this is intentional for safety.

---

### 2) Open the panel
Menu:
- **Tools → Open Card Memo Panel**

Shortcut:
- **Ctrl+Shift+M**

The panel is a standalone window. Closing it hides it (so it opens quickly next time).

---

### 3) Add a memo during review
1. Review normally
2. Open the panel (Ctrl+Shift+M)
3. Type a memo in the bottom box
4. Click **Add memo** (or press **Ctrl+Enter**)

The memo is stored inside the current note’s `_MemoLog` field.

---

## 🧠 How the data is stored

### Per-note storage
Each note’s `_MemoLog` contains a JSON list, like:

```json
[
  {"ts": 1765800000, "text": "remember: K+ increases with acidosis"},
  {"ts": 1765801200, "text": "CT finding: hyperdense MCA sign"}
]
```

### Global timeline
On load, the add-on searches for notes that contain `_MemoLog:*` and collects all entries into one list.

To keep the UI responsive, it loads using **QueryOp** (background task + progress dialog).

---

## ⚙️ Configuration

### `max_display_memos`
The add-on supports a simple config key:

- `max_display_memos` (default: `500`)

If the filtered list is longer than this, it only shows the most recent items (newer memos prioritized).

Open:
- **Tools → Add-ons → Card Memo Panel → Config**

Example:
```json
{
  "max_display_memos": 500
}
```

---

## 🎨 UI Notes

This add-on uses a “messaging app” style UI:
- soft background
- rounded memo list
- colored date headers
- primary/ghost buttons

It also disables horizontal scrolling for cleaner reading.

---

## 🛠️ Troubleshooting

### “This note type does not have _MemoLog field”
Add `_MemoLog` to the note type fields (see Quick Start).

### Panel shows “No card”
You opened the panel while not reviewing a card.  
Start a review, then open the panel again.

### Export says there are no memos
Your current filter has no matches. Switch filter to **All** or widen the date range.

### Performance feels slow on first open
The first open loads memo data from the whole collection. After that, it stays cached while the panel is open.

---

## 🔒 Privacy

- No AI
- No network calls
- All memos stay inside your Anki collection

---

## 📜 License

See `LICENSE` in this repository.
