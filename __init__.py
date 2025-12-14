# -*- coding: utf-8 -*-
#
# Card Memo Panel
#
# 機能概要：
# - 各ノートの _MemoLog フィールドに JSON 形式でメモを保存
# - すべてのカードのメモを「グローバルタイムライン」としてリスト表示
# - 日付フィルタ（All / Today / Last 7 days / Last 30 days）
# - タイムラインは日付ごとにヘッダ行を挿入（時間は表示しない）
# - メモ行クリックでブラウザを開く
# - メモ行を右クリック or Deleteキーで削除可能
# - 下部入力欄から「現在のカード」にメモを追加（学習画面と並行運用）
#

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import List, Dict, Any, Optional
from aqt.operations import QueryOp

from anki.notes import Note

from aqt import mw, gui_hooks, dialogs
from aqt.qt import (
    QAction,
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QMessageBox,
    Qt,
    QShortcut,
    QKeySequence,
    QListWidget,
    QListWidgetItem,
    QComboBox,
    QMenu,
    QColor,
    QWheelEvent,
    QFileDialog,
    QSize,
    QDateEdit,
    QDate,
    QInputDialog,
)

import html

def _addon_id() -> str:
    # __name__ から「アドオンID（フォルダ名）」を確実に取る
    try:
        return mw.addonManager.addonFromModule(__name__)
    except Exception:
        # 予備：万一取れない環境でも落とさない
        return __name__

def _get_cfg() -> dict:
    aid = _addon_id()
    try:
        return mw.addonManager.getConfig(aid) or {}
    except Exception:
        return {}


# ===== 設定 =====

MEMO_FIELD_NAME = "_MemoLog"


# ===== config 読み込み（max_display_memos） =====

def _load_max_display_memos() -> int:
    """config.json の max_display_memos を読む（なければ 500）"""
    try:
        cfg = _get_cfg()
        if isinstance(cfg, dict):
            return int(cfg.get("max_display_memos", 500))
    except Exception:
        pass
    return 500


# ===== ユーティリティ =====

def _note_has_memo_field(note: Note) -> bool:
    model = note.model()
    fields = mw.col.models.field_names(model)
    return MEMO_FIELD_NAME in fields


def _ensure_memo_field_or_warn(note: Note) -> bool:
    if _note_has_memo_field(note):
        return True

    model = note.model()
    mname = model.get("name", "Unknown")
    QMessageBox.warning(
        mw,
        "Card Memo Panel",
        f"このノートタイプには {MEMO_FIELD_NAME} フィールドがありません。\n\n"
        f"ノートタイプ '{mname}' の編集画面から、Text フィールド名 '{MEMO_FIELD_NAME}' を追加してください。",
    )
    return False


def _load_memo_log(note: Note) -> List[Dict[str, Any]]:
    """Note の _MemoLog フィールドからメモログ(JSON)を読み取る"""
    if not _note_has_memo_field(note):
        return []

    raw = note[MEMO_FIELD_NAME].strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            cleaned = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                ts = int(item.get("ts", int(time.time())))
                text = str(item.get("text", "")).strip()
                if text:
                    cleaned.append({"ts": ts, "text": text})
            return cleaned
    except Exception:
        # 壊れていたら空として扱う
        return []
    return []


def _save_memo_log(note: Note, entries: List[Dict[str, Any]]) -> None:
    """メモログ(JSON)を _MemoLog フィールドに保存"""
    if not _note_has_memo_field(note):
        return
    if not entries:
        note[MEMO_FIELD_NAME] = ""
    else:
        note[MEMO_FIELD_NAME] = json.dumps(entries, ensure_ascii=False, indent=2)
    note.flush()


# ===== 全ノートからメモを集める =====

@dataclass
class GlobalMemoEntry:
    ts: int
    text: str
    nid: int
    deck_name: str
    front_snip: str


def _collect_all_memo_entries(col) -> List[GlobalMemoEntry]:
    """コレクション内のすべての _MemoLog からメモを時系列で集める"""
    entries: List[GlobalMemoEntry] = []
    if not col:
        return entries

    try:
        nids = col.find_notes(f"{MEMO_FIELD_NAME}:*")
    except Exception:
        return entries

    import re

    for nid in nids:
        note = col.get_note(nid)
        if note is None or not _note_has_memo_field(note):
            continue

        logs = _load_memo_log(note)
        if not logs:
            continue

        # カード & デッキ情報
        cards = list(note.cards())
        if cards:
            card = cards[0]
            deck_name = col.decks.name(card.did)
        else:
            deck_name = "(no deck)"

        # Front 抜粋
        model = note.model()
        fnames = col.models.field_names(model)
        if fnames:
            front_raw = note[fnames[0]]
            front_snip = re.sub(r"<[^>]+>", "", front_raw)
            if len(front_snip) > 50:
                front_snip = front_snip[:50] + "..."
        else:
            front_snip = ""

        for item in logs:
            ts = int(item.get("ts", int(time.time())))
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            entries.append(
                GlobalMemoEntry(
                    ts=ts,
                    text=text,
                    nid=nid,
                    deck_name=deck_name,
                    front_snip=front_snip,
                )
            )

    # 古い順（上から古い→下に新しい）に並べる
    entries.sort(key=lambda e: e.ts)
    return entries



# ===== ブラウザでノートを開く =====

def open_note_in_browser(nid: int) -> None:
    """指定ノートIDでブラウザを開く"""
    b = dialogs.open("Browser", mw)
    b.search_for(f"nid:{nid}")


# ===== メモパネル本体 =====

class CardMemoPanel(QDialog):
    """
    すべてのカードのメモログを時系列リストで表示し、
    下の入力欄で「現在のカード」にメモを追加するパネル。
    日付フィルタ＋クリックでブラウザジャンプ＋メモ削除に対応。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("Card Memo Panel")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowMaximizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setObjectName("CardMemoPanel")   # ★追加

        # フォントサイズ管理用
        base = self.font().pointSize()
        if base <= 0:
            base = 14  # デフォルト
        self.base_font_size = base
        self.current_font_size = base


        # 現在フォーカスしているノートIDと、その表示情報
        self.current_nid: Optional[int] = None
        self.current_deck_name: str = ""
        self.current_front_snip: str = ""

        # 全メモタイムラインのキャッシュ（全件）
        self.entries: List[GlobalMemoEntry] = []

        # 表示件数の上限（configから読み込み）
        self.max_display_memos: int = _load_max_display_memos()

        # 現在のフィルタ種別: "all", "today", "7", "30", "custom"
        self.current_filter: str = "all"

        # ===== レイアウト構築 =====
        layout = QVBoxLayout(self)

        # 上部：現在カード情報
        self.info_label = QLabel("No card")
        self.info_label.setWordWrap(True)
        self.info_label.setObjectName("InfoLabel")   # ★追加
        layout.addWidget(self.info_label)

        # フィルタバー
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))

        self.filter_combo = QComboBox()
        self.filter_combo.setObjectName("FilterCombo")
        self.filter_combo.addItem("All", "all")
        self.filter_combo.addItem("Today", "today")
        self.filter_combo.addItem("Last 7 days", "7")
        self.filter_combo.addItem("Last 30 days", "30")
        self.filter_combo.addItem("Custom range", "custom")  # ★追加

        self.filter_combo.currentIndexChanged.connect(self.on_filter_changed)
        filter_layout.addWidget(self.filter_combo)

        # ★ カスタム日付範囲用の DateEdit
        self.from_label = QLabel("From:")
        self.from_date_edit = QDateEdit()
        self.from_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.from_date_edit.setCalendarPopup(True)

        self.to_label = QLabel("To:")
        self.to_date_edit = QDateEdit()
        self.to_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.to_date_edit.setCalendarPopup(True)

        # 初期値：今日を「To」、7日前を「From」にしておく
        today_q = QDate.currentDate()
        self.to_date_edit.setDate(today_q)
        self.from_date_edit.setDate(today_q.addDays(-6))

        # 日付が変わったら再描画
        self.from_date_edit.dateChanged.connect(self.on_custom_date_changed)
        self.to_date_edit.dateChanged.connect(self.on_custom_date_changed)

        # Custom 以外のときは非表示にしておく
        for w in (self.from_label, self.from_date_edit,
                  self.to_label, self.to_date_edit):
            w.setVisible(False)
            filter_layout.addWidget(w)


        # ★ Export TXT / HTML ボタンを追加
        self.export_button = QPushButton("Export TXT")
        self.export_button.setObjectName("GhostButton")
        self.export_button.clicked.connect(self.on_export_txt)

        self.export_html_button = QPushButton("Export HTML")   # ★追加
        self.export_html_button.setObjectName("GhostButton")   # ★追加
        self.export_html_button.clicked.connect(self.on_export_html)  # ★追加

        filter_layout.addStretch()
        filter_layout.addWidget(self.export_button)
        filter_layout.addWidget(self.export_html_button)  # ★追加

        layout.addLayout(filter_layout)


        # タイムライン本体：リスト表示
        self.list_widget = QListWidget()
        self.list_widget.setWordWrap(True)  # ★ 長い文章を折り返し表示
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )  # ★ 横スクロール禁止        
        self.list_widget.setObjectName("MemoList")   # ★追加
        layout.addWidget(self.list_widget)

        # クリックでブラウザへジャンプ
        self.list_widget.itemDoubleClicked.connect(self.on_item_clicked)

        # コンテキストメニュー（右クリック）
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.on_list_context_menu)

        # Deleteキーでメモ削除
        self._shortcut_delete = QShortcut(QKeySequence("Delete"), self.list_widget)
        self._shortcut_delete.activated.connect(self.delete_selected_memo)

        # 下部：新規メモ入力
        layout.addWidget(QLabel("New memo for CURRENT card:"))

        self.input_edit = QPlainTextEdit()
        self.input_edit.setObjectName("InputEdit")   # ★追加
        self.input_edit.setPlaceholderText(
            ""
        )
        self.input_edit.setFixedHeight(100)
        layout.addWidget(self.input_edit)

        btn_layout = QHBoxLayout()
        self.add_button = QPushButton("Add memo")
        self.add_button.setObjectName("PrimaryButton")   # ★追加
        self.clear_button = QPushButton("Clear")
        self.clear_button.setObjectName("GhostButton")   # ★追加
        btn_layout.addStretch()
        btn_layout.addWidget(self.add_button)
        btn_layout.addWidget(self.clear_button)
        layout.addLayout(btn_layout)

        self.add_button.clicked.connect(self.on_add_memo)
        self.clear_button.clicked.connect(self.on_clear_input)

        # Ctrl+Enter でメモ追加
        self._shortcut_add = QShortcut(QKeySequence("Ctrl+Return"), self)
        self._shortcut_add2 = QShortcut(QKeySequence("Ctrl+Enter"), self)
        self._shortcut_add.activated.connect(self.on_add_memo)
        self._shortcut_add2.activated.connect(self.on_add_memo)

        # 初期サイズ
        self.resize(600, 700)

        # メッセージアプリ風のスタイル
        self.setStyleSheet("""
        #CardMemoPanel {
            background-color: #f5f7fb;
        }

        /* 共通ラベル */
        QLabel {
            font-size: 11px;
            color: #6b7280;
        }

        /* 上部のカード情報エリア */
        #InfoLabel {
            background-color: #ffffff;
            border-radius: 10px;
            padding: 6px 10px;
            font-size: 11px;
            color: #4b5563;
            border: 1px solid #e0e4f0;
        }

        /* フィルタのコンボボックス */
        #FilterCombo {
            border-radius: 12px;
            padding: 2px 10px;
            border: 1px solid #d1d5db;
            background-color: #ffffff;
            font-size: 11px;
        }

        /* メモリスト本体 */
        #MemoList {
            background-color: #ffffff;
            border-radius: 12px;
            border: 1px solid #e0e4f0;
            padding: 6px;
        }

        /* メモ行の見た目（バルーンっぽく） */
        #MemoList::item {
            padding: 6px 10px;
            margin: 3px 0;
        }

        /* 選択時・ホバー時 */
        #MemoList::item:selected {
            background-color: #e5f0ff;
            color: #111827;
        }
        #MemoList::item:hover {
            background-color: #f3f4ff;
        }

        /* 入力欄（テキストボックス） */
        #InputEdit {
            background-color: #ffffff;
            border-radius: 10px;
            border: 1px solid #e0e4f0;
            padding: 6px;
            font-size: 11px;
        }

        /* メインボタン（Add memo） */
        #PrimaryButton {
            background-color: #2563eb;
            color: #ffffff;
            border-radius: 16px;
            padding: 4px 16px;
            border: none;
            font-size: 11px;
        }
        #PrimaryButton:hover {
            background-color: #1d4ed8;
        }

        /* サブボタン（Clear） */
        #GhostButton {
            background-color: transparent;
            color: #6b7280;
            border-radius: 16px;
            padding: 4px 14px;
            border: 1px solid #d1d5db;
            font-size: 11px;
        }
        #GhostButton:hover {
            background-color: #e5e7eb;
        }
                """)

        # トラックパッド / ホイール + Ctrl でフォントサイズ変更を有効に
        self.list_widget.installEventFilter(self)
        self.input_edit.installEventFilter(self)

        # 現在のフォントサイズを適用
        self._apply_font_size()

        # 最初だけ全メモを読み込む（重いのはこの1回）
        self.reload_all_memos()

        # まだカードがない間は入力無効
        self.input_edit.setEnabled(False)
        self.add_button.setEnabled(False)

    # ===== ウィンドウを閉じるとき：実際には隠すだけ =====
    def closeEvent(self, evt) -> None:
        evt.ignore()
        self.hide()


    def _apply_font_size(self) -> None:
        """現在のフォントサイズを各ウィジェットに適用"""
        # メモリスト
        f_list = self.list_widget.font()
        f_list.setPointSize(self.current_font_size)
        self.list_widget.setFont(f_list)

        # 入力欄
        f_input = self.input_edit.font()
        f_input.setPointSize(self.current_font_size)
        self.input_edit.setFont(f_input)

        # ★これを追加：入力欄内部(document)のフォントにも適用
        self.input_edit.document().setDefaultFont(f_input)        

        # 上部の情報ラベルは少し小さめ
        f_info = self.info_label.font()
        f_info.setPointSize(max(8, self.current_font_size - 1))
        self.info_label.setFont(f_info)

        # ★ 日付ヘッダーのフォントサイズも更新
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            data = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, tuple) and data[0] == "header":
                font = it.font()
                font.setBold(True)
                font.setPointSize(max(8, self.current_font_size + 1))
                it.setFont(font)
        


    def _change_font_size(self, delta: int) -> None:
        """フォントサイズを +1 / -1 などで変更"""
        new_size = max(8, min(24, self.current_font_size + delta))
        if new_size == self.current_font_size:
            return
        self.current_font_size = new_size
        self._apply_font_size()


    # ===== 全メモ再読み込み（初回 & 明示リロード用） =====

    def reload_all_memos(self) -> None:
        """QueryOp を使って全メモを再読み込み（進捗ウィンドウ付き）"""

        # 一旦「Loading...」表示にしておく
        self.list_widget.clear()
        loading_item = QListWidgetItem("(Loading memos...)")
        loading_item.setFlags(Qt.ItemFlag.NoItemFlags)
        self.list_widget.addItem(loading_item)

        def _op(col):
            # バックグラウンドスレッド側で走る処理（GUI操作禁止）
            return _collect_all_memo_entries(col)

        def _on_success(entries: List[GlobalMemoEntry]) -> None:
            # メインスレッドに戻ってくる
            self.entries = entries
            self._rebuild_list()

        QueryOp(
            parent=mw,
            op=_op,
            success=_on_success,
        ).with_progress(label="Collecting card memos...").run_in_background()


    # ===== フィルタ変更 =====

    def on_filter_changed(self, _index: int) -> None:
        data = self.filter_combo.currentData()
        if isinstance(data, str):
            self.current_filter = data
        else:
            self.current_filter = "all"

        # Custom range のときだけ日付入力を表示
        is_custom = (self.current_filter == "custom")
        for w in (self.from_label, self.from_date_edit,
                  self.to_label, self.to_date_edit):
            w.setVisible(is_custom)

        self._rebuild_list()

    def on_custom_date_changed(self, _qdate) -> None:
        """カスタム日付が変更されたとき、Custom選択中ならリストを更新"""
        if self.current_filter == "custom":
            self._rebuild_list()


    def on_export_txt(self) -> None:
        """現在のフィルタ条件で表示されるメモを TXT に書き出す"""
        entries = self._filtered_entries()
        if not entries:
            QMessageBox.information(
                self,
                "Export memo timeline",
                "このフィルタ条件に該当するメモがありません。",
            )
            return

        # 保存先パスを選択
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export memo timeline",
            "memo_timeline.txt",
            "Text files (*.txt);;All files (*)",
        )
        if not path:
            return

        # 日付ごとにまとめてプレーンテキストを作成
        lines: list[str] = []
        last_date_str: Optional[str] = None

        for e in entries:
            d = date.fromtimestamp(e.ts)
            date_str = d.isoformat()

            if date_str != last_date_str:
                # 日付が変わるタイミングで空行 + 日付見出し
                if lines:
                    lines.append("")
                lines.append(date_str)
                last_date_str = date_str

            # タイムライン表示と同じく、時間は出さずテキストだけ
            lines.append(f"  - {e.text}")

        text = "\n".join(lines)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Export memo timeline",
                f"書き出し中にエラーが発生しました:\n{e}",
            )
            return

        QMessageBox.information(
            self,
            "Export memo timeline",
            "メモのタイムラインをテキストファイルに書き出しました。",
        )

    def on_export_html(self) -> None:
        """現在のフィルタ条件で表示されるメモを HTML に書き出す"""
        entries = self._filtered_entries()
        if not entries:
            QMessageBox.information(
                self,
                "Export memo timeline",
                "このフィルタ条件に該当するメモがありません。",
            )
            return

        # 保存先パスを選択
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export memo timeline (HTML)",
            "memo_timeline.html",
            "HTML files (*.html);;All files (*)",
        )
        if not path:
            return

        # HTML本文を構築
        lines: list[str] = []

        lines.append("<!DOCTYPE html>")
        lines.append("<html lang='en'>")
        lines.append("<head>")
        lines.append("<meta charset='utf-8'>")
        lines.append("<title>Memo Timeline</title>")
        # シンプルなCSS（タイムラインの見た目をAnki内と近づける）
        lines.append("""
<style>
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background-color: #f5f7fb;
    padding: 16px;
}
.memo-date {
    background-color: #e8efff;
    color: #1e3a8a;
    padding: 4px 10px;
    border-radius: 8px;
    margin-top: 16px;
    margin-bottom: 4px;
    display: inline-block;
    font-weight: bold;
}
.memo-list {
    list-style-type: disc;
    margin: 4px 0 0 24px;
    padding: 0;
}
.memo-item {
    margin: 2px 0;
    line-height: 1.4;
}
</style>
""")
        lines.append("</head>")
        lines.append("<body>")

        last_date_str: Optional[str] = None
        opened_ul = False

        for e in entries:
            d = date.fromtimestamp(e.ts)
            date_str = d.isoformat()

            # 日付が切り替わるたびにヘッダ + 新しい <ul>
            if date_str != last_date_str:
                # 前の日付の<ul>を閉じる
                if opened_ul:
                    lines.append("</ul>")
                    opened_ul = False

                lines.append(
                    f"<div class='memo-date'>{html.escape(date_str)}</div>"
                )
                lines.append("<ul class='memo-list'>")
                opened_ul = True
                last_date_str = date_str

            # メモ本文（HTMLエスケープ）
            text_html = html.escape(e.text)
            lines.append(f"<li class='memo-item'>{text_html}</li>")

        if opened_ul:
            lines.append("</ul>")

        lines.append("</body>")
        lines.append("</html>")

        html_text = "\n".join(lines)

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_text)
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Export memo timeline",
                f"HTML書き出し中にエラーが発生しました:\n{exc}",
            )
            return

        QMessageBox.information(
            self,
            "Export memo timeline",
            "メモのタイムラインをHTMLファイルに書き出しました。",
        )




    # ===== エントリをフィルタしてリストを組み立て =====

    def _filtered_entries(self) -> List[GlobalMemoEntry]:
        if not self.entries:
            return []

        today = date.today()

        def in_filter(e: GlobalMemoEntry) -> bool:
            d = date.fromtimestamp(e.ts)

            if self.current_filter == "today":
                return d == today
            elif self.current_filter == "7":
                return d >= (today - timedelta(days=6))  # 今日含め7日間
            elif self.current_filter == "30":
                return d >= (today - timedelta(days=29))  # 今日含め30日間
            elif self.current_filter == "custom":
                try:
                    from_d = self.from_date_edit.date().toPyDate()
                    to_d = self.to_date_edit.date().toPyDate()
                except Exception:
                    # 万が一ウィジェットにアクセスできない場合はフィルタ無し扱い
                    return True

                if from_d and to_d:
                    # うっかり From > To にしても動くようにスワップ
                    if from_d > to_d:
                        from_d, to_d = to_d, from_d
                    return from_d <= d <= to_d

                return True
            else:
                return True

        filtered = [e for e in self.entries if in_filter(e)]

        # 表示件数の上限を適用（新しい方を優先）
        if self.max_display_memos and len(filtered) > self.max_display_memos:
            filtered = filtered[-self.max_display_memos :]

        return filtered

    def _rebuild_list(self) -> None:
        """self.entries + current_filter からリスト表示を作り直す"""
        self.list_widget.clear()

        entries = self._filtered_entries()
        if not entries:
            empty_item = QListWidgetItem("(No memo recorded for this filter.)")
            empty_item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list_widget.addItem(empty_item)
            return

        last_date_str: Optional[str] = None

        for e in entries:
            d = date.fromtimestamp(e.ts)
            date_str = d.isoformat()

            # 日付が変わったタイミングだけ、日付ヘッダを挿入
            if date_str != last_date_str:
                # ★ 直前にも日付があった場合だけ「空白行」を入れる
                if last_date_str is not None:
                    spacer = QListWidgetItem("")
                    spacer.setFlags(Qt.ItemFlag.NoItemFlags)
                    spacer.setSizeHint(QSize(spacer.sizeHint().width(), 8))  # 高さだけ少し
                    self.list_widget.addItem(spacer)

                header_item = QListWidgetItem(date_str)
                header_item.setData(Qt.ItemDataRole.UserRole, ("header", None, None))
                header_item.setFlags(Qt.ItemFlag.NoItemFlags)

                font = header_item.font()
                font.setBold(True)
                font.setPointSize(max(8, self.current_font_size + 1))  # 本文より少し大きめ
                header_item.setFont(font)
                header_item.setBackground(QColor("#e8efff"))
                header_item.setForeground(QColor("#1e3a8a"))
                header_item.setText("  " + date_str + "  ")

                self.list_widget.addItem(header_item)
                last_date_str = date_str

            # メモ本体：時間は表示せずテキストだけ
            display_text = "• " + e.text
            memo_item = QListWidgetItem(display_text)

            # kind, nid, ts の3タプルで保存
            memo_item.setData(Qt.ItemDataRole.UserRole, ("memo", e.nid, e.ts))
            self.list_widget.addItem(memo_item)

        self.list_widget.scrollToBottom()

    # ===== 1件追加（メモ追加時） =====

    def _entry_in_current_filter(self, e: GlobalMemoEntry) -> bool:
        """1件が現在のフィルタ条件に入るか判定"""
        today = date.today()
        d = date.fromtimestamp(e.ts)

        if self.current_filter == "today":
            return d == today
        elif self.current_filter == "7":
            return d >= (today - timedelta(days=6))
        elif self.current_filter == "30":
            return d >= (today - timedelta(days=29))
        elif self.current_filter == "custom":
            try:
                from_d = self.from_date_edit.date().toPyDate()
                to_d = self.to_date_edit.date().toPyDate()
            except Exception:
                return True

            if from_d and to_d:
                if from_d > to_d:
                    from_d, to_d = to_d, from_d
                return from_d <= d <= to_d
            return True

        return True

    def _append_entry(self, e: GlobalMemoEntry) -> None:
        """
        新しい1件のメモを self.entries に追加し、
        現在のフィルタに合うならリスト末尾に反映。
        """
        self.entries.append(e)

        # フィルタに引っかからない場合は、内部キャッシュだけ更新して終了
        if not self._entry_in_current_filter(e):
            return

        # 上限を超えた場合は素直に全再描画（簡単＆そこそこ高速）
        current_filtered = self._filtered_entries()
        if self.max_display_memos and len(current_filtered) >= self.max_display_memos:
            self._rebuild_list()
            return

        # 直近の日付ヘッダを確認して、必要なら新たに挿入
        d = date.fromtimestamp(e.ts)
        date_str = d.isoformat()

        last_header_date: Optional[str] = None
        for i in range(self.list_widget.count() - 1, -1, -1):
            it = self.list_widget.item(i)
            data = it.data(Qt.ItemDataRole.UserRole)
            if isinstance(data, tuple) and data[0] == "header":
                # テキスト前後の空白を削って純粋な日付だけ比較する
                last_header_date = it.text().strip()
                break

        if last_header_date != date_str:
            # ★ すでにヘッダーがある（＝2日目以降）なら、その前に空白行
            if last_header_date is not None:
                spacer = QListWidgetItem("")
                spacer.setFlags(Qt.ItemFlag.NoItemFlags)
                spacer.setSizeHint(QSize(spacer.sizeHint().width(), 8))
                self.list_widget.addItem(spacer)

            header_item = QListWidgetItem(date_str)
            header_item.setData(Qt.ItemDataRole.UserRole, ("header", None, None))
            header_item.setFlags(Qt.ItemFlag.NoItemFlags)

            font = header_item.font()
            font.setBold(True)
            font.setPointSize(max(8, self.current_font_size + 1))
            header_item.setFont(font)
            header_item.setBackground(QColor("#e8efff"))
            header_item.setForeground(QColor("#1e3a8a"))
            header_item.setText("  " + date_str + "  ")

            self.list_widget.addItem(header_item)


        display_text = "• " + e.text
        memo_item = QListWidgetItem(display_text)
        memo_item.setData(Qt.ItemDataRole.UserRole, ("memo", e.nid, e.ts))
        self.list_widget.addItem(memo_item)

        self.list_widget.scrollToBottom()

    # ===== 現在カードの情報更新（タイムラインは変えない）=====

    def set_card(self, card) -> None:
        """現在の Reviewer.card が変わったときに呼ばれる（入力先カードの更新用）"""
        if card is None:
            self.current_nid = None
            self.current_deck_name = ""
            self.current_front_snip = ""
            self.info_label.setText("No card")
            self.input_edit.setEnabled(False)
            self.add_button.setEnabled(False)
            return

        note = card.note()
        self.current_nid = note.id

        deck_name = mw.col.decks.name(card.did)
        self.current_deck_name = deck_name

        model = note.model()
        fnames = mw.col.models.field_names(model)
        front_snip = ""
        if fnames:
            front_raw = note[fnames[0]]
            import re
            front_snip = re.sub(r"<[^>]+>", "", front_raw)
            if len(front_snip) > 50:
                front_snip = front_snip[:50] + "..."
        self.current_front_snip = front_snip

        self.info_label.setText(
            f"CURRENT CARD\n"
            f"Deck: {deck_name}\n"
            f"Note ID: {note.id}\n"
            f"Front: {front_snip}"
        )

        # メモ用フィールドがなければ入力を無効化
        if not _note_has_memo_field(note):
            self.input_edit.setEnabled(False)
            self.add_button.setEnabled(False)
            return

        self.input_edit.setEnabled(True)
        self.add_button.setEnabled(True)

    # ===== 入力関連 =====

    def on_clear_input(self) -> None:
        self.input_edit.clear()

    def on_add_memo(self) -> None:
        """新しいメモを現在のノートに追加し、タイムラインに1件だけ反映"""
        text = self.input_edit.toPlainText().strip()
        if not text:
            return

        if self.current_nid is None:
            QMessageBox.information(
                self,
                "Card Memo Panel",
                "メモを追加するには、まず学習画面でカードを表示してください。",
            )
            return

        # まず Reviewer が持っている Note を優先的に使う
        note = None
        reviewer = getattr(mw, "reviewer", None)
        if reviewer is not None and getattr(reviewer, "card", None):
            r_note = reviewer.card.note()
            if r_note.id == self.current_nid:
                note = r_note

        # 念のため fallback として col からも取得
        if note is None:
            note = mw.col.get_note(self.current_nid)

        if note is None:
            return

        if not _ensure_memo_field_or_warn(note):
            return

        # 既存ログを読み込み
        existing = _load_memo_log(note)
        ts = int(time.time())
        new_entry_dict = {"ts": ts, "text": text}
        existing.append(new_entry_dict)
        _save_memo_log(note, existing)

        # 全体タイムライン用のエントリを組み立てて末尾に追加
        new_global = GlobalMemoEntry(
            ts=ts,
            text=text,
            nid=note.id,
            deck_name=self.current_deck_name,
            front_snip=self.current_front_snip,
        )
        self._append_entry(new_global)

        # 入力欄クリア
        self.input_edit.clear()
        self.input_edit.setFocus()

    # ===== リスト item クリック：ブラウザを開く =====

    def on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        kind, nid, ts = data
        if kind != "memo" or not nid:
            return
        open_note_in_browser(int(nid))

    # ===== コンテキストメニュー（右クリック） =====

    def on_list_context_menu(self, pos) -> None:
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        kind, nid, ts = data
        if kind != "memo" or not nid:
            return

        menu = QMenu(self)
        act_edit = menu.addAction("Edit this memo")      # ★追加
        act_del = menu.addAction("Delete this memo")
        chosen = menu.exec(self.list_widget.mapToGlobal(pos))
        if chosen == act_edit:
            self._edit_memo_item(item)                   # ★追加
        elif chosen == act_del:
            self._delete_memo_item(item)

    def _edit_memo_item(self, item: QListWidgetItem) -> None:
        """1件のメモ内容を編集する（フォントサイズ連動の専用ダイアログ版）"""
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        kind, nid, ts = data
        if kind != "memo" or not nid:
            return

        # 現在表示しているテキストから "• " を除去して本文だけ取り出す
        display_text = item.text()
        if display_text.startswith("• "):
            current_text = display_text[2:]
        else:
            current_text = display_text

        # ===== 専用の編集ダイアログを定義 =====
        class _MemoEditDialog(QDialog):
            def __init__(self, parent, text: str, font_size: int) -> None:
                super().__init__(parent)
                self.setWindowTitle("Edit memo")

                layout = QVBoxLayout(self)

                label = QLabel("Memo:")
                layout.addWidget(label)

                self.text_edit = QPlainTextEdit()
                self.text_edit.setPlainText(text)

                # ★ここでフォントサイズをパネルと揃える
                f = self.text_edit.font()
                f.setPointSize(font_size)
                self.text_edit.setFont(f)
                self.text_edit.document().setDefaultFont(f)

                layout.addWidget(self.text_edit)

                # ボタン行
                btn_layout = QHBoxLayout()
                btn_layout.addStretch()
                ok_btn = QPushButton("OK")
                cancel_btn = QPushButton("Cancel")
                ok_btn.clicked.connect(self.accept)
                cancel_btn.clicked.connect(self.reject)
                btn_layout.addWidget(ok_btn)
                btn_layout.addWidget(cancel_btn)
                layout.addLayout(btn_layout)

                self.resize(420, 260)

            def get_text(self) -> str:
                return self.text_edit.toPlainText()

        # ===== ダイアログを開く =====
        dlg = _MemoEditDialog(self, current_text, self.current_font_size)
        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            return

        new_text = dlg.get_text().strip()
        # 空文字 or 変更なしなら何もしない（削除は「Delete this memo」で行う）
        if not new_text or new_text == current_text:
            return

        # ノート取得
        note = mw.col.get_note(int(nid))
        if note is None:
            QMessageBox.warning(
                self,
                "Edit memo",
                "元のノートが見つかりませんでした。",
            )
            return

        if not _ensure_memo_field_or_warn(note):
            return

        # _MemoLog(JSON) を書き換え
        logs = _load_memo_log(note)
        changed = False
        for ent in logs:
            ets = int(ent.get("ts", 0))
            if ets == int(ts):
                ent["text"] = new_text
                changed = True
                break

        if not changed:
            QMessageBox.warning(
                self,
                "Edit memo",
                "メモログ内に該当エントリが見つかりませんでした。",
            )
            return

        _save_memo_log(note, logs)

        # グローバルキャッシュ側のテキストも更新
        for e in self.entries:
            if e.nid == int(nid) and e.ts == int(ts):
                e.text = new_text
                break

        # リスト上の表示テキストも更新
        item.setText("• " + new_text)


    def delete_selected_memo(self) -> None:
        item = self.list_widget.currentItem()
        if not item:
            return
        self._delete_memo_item(item)

    def _delete_memo_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(data, tuple):
            return
        kind, nid, ts = data
        if kind != "memo" or not nid:
            return

        # 確認ダイアログ
        ret = QMessageBox.question(
            self,
            "Delete memo",
            "このメモを削除しますか？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return

        # 表示用テキスト ("• xxx") から実際のメモ本文だけを取り出す
        target_text_display = item.text()
        target_text = (
            target_text_display[2:]
            if target_text_display.startswith("• ")
            else target_text_display
        )

        note = mw.col.get_note(int(nid))
        if note is None:
            self.entries = [
                e for e in self.entries
                if not (e.nid == int(nid) and e.ts == int(ts) and e.text == target_text)
            ]
            self._rebuild_list()
            return

        # Note側: _MemoLog から該当エントリを1件だけ削除
        logs = _load_memo_log(note)

        # 表示用テキスト ("• xxx") から実際のメモ本文だけを取り出す
        target_text_display = item.text()
        target_text = target_text_display[2:] if target_text_display.startswith("• ") else target_text_display
        new_logs: List[Dict[str, Any]] = []
        removed = False
        for ent in logs:
            ets = int(ent.get("ts", 0))
            etext = str(ent.get("text", "")).strip()
            if (not removed) and ets == int(ts) and etext == target_text:
                removed = True
                continue
            new_logs.append(ent)

        _save_memo_log(note, new_logs)

        # グローバルキャッシュからも削除
        self.entries = [
            e
            for e in self.entries
            if not (e.nid == int(nid) and e.ts == int(ts) and e.text == target_text)
        ]

        # リスト再構築（ヘッダも含めてキレイに）
        self._rebuild_list()

    def eventFilter(self, obj, event):
        # トラックパッドの二本指スクロール / マウスホイール + Ctrl(Win/Linux) or ⌘(macOS) で拡大縮小
        if isinstance(event, QWheelEvent):
            mods = event.modifiers()
            # Ctrl または Command が押されているときにズーム扱い
            if mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier):
                delta = event.angleDelta().y()
                if delta > 0:
                    self._change_font_size(+1)
                elif delta < 0:
                    self._change_font_size(-1)
                return True  # 通常のスクロールはキャンセル
        return super().eventFilter(obj, event)


# ===== メモパネルを開く関数 =====

def open_memo_panel() -> None:
    """Tools メニューやショートカットから呼ばれる"""
    panel: Optional[CardMemoPanel] = getattr(mw, "_card_memo_panel", None)
    if panel is None or not panel.isVisible():
        panel = CardMemoPanel(parent=None)
        mw._card_memo_panel = panel

    panel.show()
    panel.raise_()
    panel.activateWindow()

    # もし今レビュー中なら、現在カードで info を更新
    reviewer = getattr(mw, "reviewer", None)
    if reviewer and getattr(reviewer, "card", None):
        panel.set_card(reviewer.card)


# ===== フック：メインウィンドウ初期化 =====

def on_main_window_did_init(*args, **kwargs) -> None:
    # Tools メニューに項目追加
    act = QAction("Open Card Memo Panel", mw)
    act.triggered.connect(open_memo_panel)
    mw.form.menuTools.addAction(act)

    # ショートカット（Ctrl+Shift+M）でパネルを開く
    sc = QShortcut(QKeySequence("Ctrl+Shift+M"), mw)
    sc.activated.connect(open_memo_panel)
    mw._card_memo_panel_shortcut = sc


# ===== フック：カードが表示されるたびに「現在カード情報」だけ更新 =====

def on_reviewer_did_show_question(*args, **kwargs) -> None:
    panel: Optional[CardMemoPanel] = getattr(mw, "_card_memo_panel", None)
    if panel is None or not panel.isVisible():
        return

    reviewer = getattr(mw, "reviewer", None)
    if reviewer is None or not getattr(reviewer, "card", None):
        return

    panel.set_card(reviewer.card)


# ===== フック登録 =====

gui_hooks.main_window_did_init.append(on_main_window_did_init)
gui_hooks.reviewer_did_show_question.append(on_reviewer_did_show_question)
