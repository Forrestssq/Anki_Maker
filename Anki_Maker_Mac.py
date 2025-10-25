'''
2.3新功能
- 支持Command/Control+Enter在"释义"和"助记"框换行.
- 增加了"教程".
- 修复了音标的自动补齐的功能


2.2新功能:
- 增加了剪贴板的监听功能.
- 当打开此功能的时候,将会开始监听剪贴板.
- 当识别到"单个"的"英文单词"的时候,将会保存下来,并且自动填充音标/词性/释义.
- 之后在Mac上会发送优雅的AppleScript通知,不打扰我们的阅读.



'''

#!/usr/bin/env python3
# anki_vocab_app_enhanced.py

import os
import sys
import json
import csv
import subprocess
import threading
import time
from datetime import datetime
import re
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import genanki
from plyer import notification


# optional genanki for apkg export
try:
    import genanki
except Exception:
    genanki = None


EXPORT_FOLDER = "exports"
DATA_FILE = "draft.json"
DEFAULT_DICT = "dict.json"
AUTOSAVE_INTERVAL = 5  # seconds

CJK_RE = re.compile(r'[\u4e00-\u9fff]')
POS_PREFIX_RE = re.compile(r'^\s*([a-zA-Z]{1,6})\.\s*')


TUTORIAL_CONTENTS = [
    {
        "title": "基本介绍",
        "content": "Anki Maker 是一款帮助你快速制作英语单词卡的工具，支持自动补全单词信息、导出多种格式（包括Anki支持的APKG）。\n\n主要功能：\n- 手动添加单词及释义\n- 从剪贴板自动捕获英文单词\n- 自动补全单词音标和释义\n- 导出为CSV/JSON/APKG/Markdown"
    },
    {
        "title": "手动添加单词",
        "content": "1. 在上方输入框依次填写：单词、词性、释义和助记.ps:当我们填完一个框框之后,按下'Enter'键,便可以跳转到下一个框框.这是我喜欢的.\n2. 点击「➕ 添加词条」按钮或按回车完成添加\n3. 添加的单词会显示在下方列表中\n4. 比较贴心的是我们不需要填写音标.程序会调用本地词典自动补入\5如果要换行,则按下'Command或Control + Enter回车'"
    },
    {
        "title": "自动补全功能",
        "content": "1. 输入单词的英文后，点击「🔁 自动补全」按钮（或按Ctrl+E/Cmd+E）\n2. 系统会从本地词典(dict.json)自动填充音标、词性和释义,随后跳转到'助记'这个框框.\n3. 你可以在自动填充后手动修改内容"
    },
    {
        "title": "剪贴板监听",
        "content": "1. 点击「📋 开始/结束监听剪贴板」按钮开启功能\n2. 当复制单个英文单词时，程序会自动：\n   - 识别单词并填充到输入框\n   - 自动补全单词信息\n   - 自动添加到列表\n3. 再次点击按钮可关闭监听"
    },
    {
        "title": "导出功能",
        "content": "1. 完成单词添加后，可选择多种导出格式：\n   - CSV：适合导入Excel或其他工具\n   - JSON：用于备份或后续导入\n   - APKG：可直接导入Anki的卡组文件\n   - Markdown：适合阅读和分享\n2. 导出文件会保存在exports文件夹中"
    },
    {
        "title": "草稿功能",
        "content": "1. 程序会每5秒自动保存当前单词列表\n2. 可点击「🧾 暂存草稿」手动保存\n3. 点击「📂 导入草稿」可加载之前保存的JSON文件\n4. 关闭程序时会自动保存当前内容"
    }
]


vocab_model = genanki.Model(
    1607392319,
    'Vocabulary Model',
    fields=[
        {'name': 'Word'},
        {'name': 'Phonetic'},
        {'name': 'PartOfSpeech'},
        {'name': 'Meaning'},
        {'name': 'Mnemonic'},
    ],
    templates=[
        {
            'name': 'Card 1',
            'qfmt': '''
            <div class="word">{{Word}}</div>
            <div class="phonetic">{{Phonetic}}</div>
            <div class="pos">{{PartOfSpeech}}</div>
            ''',
            'afmt': '''
            {{FrontSide}}
            <div class="meaning">{{Meaning}}</div>
            <div class="mnemonic">{{Mnemonic}}</div>
            ''',
        },
    ],
    css='''
    .card{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Arial; font-size:20px; text-align:center; padding:14px; }
    .word{ font-weight:bold; font-size:32px; color:#111; }
    .phonetic{ font-style:italic; color:#666; margin-top:6px; font-size:18px; }
    .pos{ margin-top:6px; color:#444; font-size:18px; }
    .meaning{ margin-top:12px; font-size:20px; color:#1a7f1a; }
    .mnemonic{ margin-top:8px; font-size:16px; color:#6b4fbf; }
    '''
)



# ---------------- Utility Functions ----------------
def contains_cjk(s):
    return bool(s and CJK_RE.search(s))


def detect_pos_from_defs(defs):
    if not defs:
        return ""

    for d in defs:
        if not d:
            continue
        m = POS_PREFIX_RE.match(d)
        if m:
            return m.group(1)

    for d in defs:
        low = d.lower()
        for tag in ("noun", "verb", "adj", "adv", "prep", "conj", "pron", "det"):
            if low.startswith(tag) or f" {tag} " in low:
                return tag

    return ""


def extract_chinese_translations(defs):
    if not defs:
        return []
    return [d.strip() for d in defs if d and contains_cjk(d)]


def open_folder(path):
    try:
        if sys.platform == "darwin":
            subprocess.call(["open", path])
        elif sys.platform.startswith("win"):
            subprocess.call(["explorer", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception:
        pass


def ensure_export_folder():
    os.makedirs(EXPORT_FOLDER, exist_ok=True)

#=========教程的窗口===========
class TutorialWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Anki Maker 使用教程")
        self.geometry("600x400")
        self.current_page = 0
        self.total_pages = len(TUTORIAL_CONTENTS)
        
        # 确保窗口在父窗口中央
        self.transient(parent)
        self.grab_set()
        
        self._create_widgets()
        self._update_content()
        
    def _create_widgets(self):
        # 标题标签
        self.title_label = ttk.Label(
            self, 
            text="", 
            font=("Arial", 14, "bold")
        )
        self.title_label.pack(pady=(15, 10), padx=20, anchor="w")
        
        # 内容文本框
        self.content_text = tk.Text(
            self, 
            wrap=tk.WORD, 
            width=70, 
            height=12,
            font=("Arial", 10),
            relief=tk.FLAT,
            bg=self.cget("bg")
        )
        self.content_text.pack(padx=20, fill="both", expand=True)
        self.content_text.config(state=tk.DISABLED)
        
        # 导航按钮区域
        nav_frame = ttk.Frame(self)
        nav_frame.pack(pady=15, fill="x", padx=20)
        
        self.prev_btn = ttk.Button(
            nav_frame, 
            text="上一页", 
            command=self.prev_page
        )
        self.prev_btn.pack(side="left")
        
        self.page_label = ttk.Label(nav_frame, text="")
        self.page_label.pack(side="left", padx=20, expand=True)
        
        self.next_btn = ttk.Button(
            nav_frame, 
            text="下一页", 
            command=self.next_page
        )
        self.next_btn.pack(side="right")
        
        self.close_btn = ttk.Button(
            nav_frame, 
            text="关闭", 
            command=self.destroy
        )
        self.close_btn.pack(side="right", padx=10)
        
    def _update_content(self):
        # 更新当前页内容
        page = TUTORIAL_CONTENTS[self.current_page]
        self.title_label.config(text=page["title"])
        
        self.content_text.config(state=tk.NORMAL)
        self.content_text.delete("1.0", tk.END)
        self.content_text.insert("1.0", page["content"])
        self.content_text.config(state=tk.DISABLED)
        
        # 更新页码显示
        self.page_label.config(text=f"{self.current_page + 1}/{self.total_pages}")
        
        # 控制按钮状态
        self.prev_btn.config(state=tk.NORMAL if self.current_page > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if self.current_page < self.total_pages - 1 else tk.DISABLED)
        
    def prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self._update_content()
            
    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.current_page += 1
            self._update_content()






# ---------------- DictLookup ----------------
class DictLookup:
    def __init__(self, json_path=None):
        self.words = []  # 存储所有单词
        self.path = json_path or DEFAULT_DICT
        self.data = {}
        self.load(self.path)

    def load(self, path):
        self.path = path
        self.data = {}
        if not path or not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            for k, v in raw.items():
                if k:
                    self.data[k.strip().lower()] = v
        except Exception:
            self.data = {}

    def lookup(self, word):
        if not word:
            return None

        key = word.strip().lower()
        if key in self.data:
            return self._to_result(key, self.data[key])

        alt = key.strip("'\"")
        if alt in self.data:
            return self._to_result(alt, self.data[alt])

        for k in self.data:
            if k.endswith(key):
                return self._to_result(k, self.data[k])

        return None

    def _to_result(self, key, entry):
        phonetic = entry.get("phonetic", "") or ""
        defs = entry.get("definitions", []) or []
        pos = detect_pos_from_defs(defs)
        translations = extract_chinese_translations(defs)
        return {
            "word": key,
            "phonetic": phonetic,
            "pos": pos,
            "translations": translations,
            "definitions": defs,
            "exchange": entry.get("exchange", {}) or {}
        }


# ---------------- Main App ----------------
class AnkiMakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Anki Maker Version 2.3")
        self.data = []
        self.clipboard_listening = False  # 监听状态
        self.last_clipboard_content = ""  # 上次剪贴板内容缓存
        self.dict_lookup = DictLookup()
        self.autosave_running = True
        self._build_ui()
        self._load_draft()
        self._start_autosave()

        # load local dict.json
        dict_path = os.path.join(os.path.dirname(__file__), DEFAULT_DICT)
        self.local_dict = {}
        if os.path.exists(dict_path):
            try:
                with open(dict_path, "r", encoding="utf-8") as f:
                    self.local_dict = json.load(f)
                print(f"✅ 已加载本地词典，共 {len(self.local_dict)} 个词条")
            except Exception as e:
                print("⚠️ dict.json 加载失败:", e)
        else:
            print("❌ 未找到 dict.json")

        # 检查是否首次启动
        if not os.path.exists("first_run_flag"):
            # 标记为已启动过
            with open("first_run_flag", "w") as f:
                f.write("1")
            # 显示教程
            self.show_tutorial()

    # ---------------- UI Construction ----------------
    def _build_ui(self):
        frm = ttk.Frame(self.root, padding=10)
        frm.pack(fill="both", expand=True)
        row = 0

        # Input fields
        ttk.Label(frm, text="Word").grid(row=row, column=0, sticky="e")
        self.word_entry = ttk.Entry(frm, width=40)
        self.word_entry.grid(row=row, column=1, sticky="w")
        self.word_entry.focus_set()

        row += 1
        ttk.Label(frm, text="音标").grid(row=row, column=0, sticky="e")
        self.phonetic_entry = ttk.Entry(frm, width=40)
        self.phonetic_entry.grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(frm, text="词性").grid(row=row, column=0, sticky="e")
        self.pos_entry = ttk.Entry(frm, width=40)
        self.pos_entry.grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(frm, text="释义").grid(row=row, column=0, sticky="ne")
        self.definition_text = tk.Text(frm, width=50, height=4)
        self.definition_text.grid(row=row, column=1, sticky="w")

        row += 1
        ttk.Label(frm, text="助记").grid(row=row, column=0, sticky="ne")
        self.example_text = tk.Text(frm, width=50, height=3)
        self.example_text.grid(row=row, column=1, sticky="w")

        # Search box
        row += 1
        ttk.Label(frm, text="搜索:").grid(row=row, column=0, sticky="e")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(frm, textvariable=self.search_var)
        search_entry.grid(row=row, column=1, sticky="we")
        search_entry.bind("<KeyRelease>", self.filter_tree)

        # Buttons
        row += 1
        btn_frame = ttk.Frame(frm)
        btn_frame.grid(row=row, column=1, sticky="w", pady=(8, 0))
        ttk.Button(btn_frame, text="➕ 添加词条", command=self.add_word).grid(row=0, column=0, padx=6)
        ttk.Button(btn_frame, text="🧾 暂存草稿", command=self.save_draft).grid(row=0, column=1, padx=6)
        ttk.Button(btn_frame, text="📂 导入草稿", command=self.import_json_draft).grid(row=0, column=2, padx=6)
        ttk.Button(btn_frame, text="🔁 自动补全 (Cmd/Ctrl+E)", command=self.autofill_from_dict).grid(row=0, column=3, padx=6)
        ttk.Button(btn_frame, text="📤 导出 CSV", command=self.export_csv).grid(row=1, column=0, padx=6)
        ttk.Button(btn_frame, text="📤 导出 JSON", command=self.export_json).grid(row=1, column=1, padx=6)
        ttk.Button(btn_frame, text="📤 导出 APKG", command=self.export_apkg).grid(row=1, column=2, padx=6)
        ttk.Button(btn_frame, text="📤 导出 MD", command=self.export_md).grid(row=1, column=3, padx=6)
        ttk.Button(btn_frame, text="🗑 删除选中", command=self.delete_selected_item).grid(row=2, column=0, padx=6)
        ttk.Button(btn_frame, text="🧹 清空所有", command=self.clear_all_items).grid(row=2, column=2, padx=6)
        ttk.Button(btn_frame, text="📋 开始/结束监听剪贴板", command=self.toggle_clipboard_listen, style="TButton").grid(row=1, column=4, padx=6)
        ttk.Button(btn_frame, text="📖 使用教程", command=self.show_tutorial).grid(row=2, column=1, padx=6)

        # Treeview for added words
        row += 1
        list_frame = ttk.LabelFrame(frm, text="已添加词条", padding=(6, 6))
        list_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0), sticky="nsew")
        frm.rowconfigure(row, weight=1)
        frm.columnconfigure(1, weight=1)

        columns = ("word", "phonetic", "pos", "definition")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=12)
        for c in columns:
            self.tree.heading(c, text=c)
        self.tree.column("word", width=150)
        self.tree.column("phonetic", width=120)
        self.tree.column("pos", width=80)
        self.tree.column("definition", width=360)
        self.tree.pack(side="left", fill="both", expand=True)

        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<Double-1>", self.on_tree_double)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(side="bottom", fill="x")

        # Key bindings
        self.word_entry.bind("<Return>", lambda e: self.pos_entry.focus_set())
        self.pos_entry.bind("<Return>", lambda e: self.definition_text.focus_set())
        self.definition_text.bind("<Return>", lambda e: self.example_text.focus_set())
        self.example_text.bind("<Return>", lambda e: self.add_word())
        self.root.bind_all("<Control-e>", lambda e: self.autofill_from_dict())
        self.root.bind_all("<Command-e>", lambda e: self.autofill_from_dict())
        self.root.bind_all("<Control-s>", lambda e: self.save_draft())
        self.root.bind_all("<Command-s>", lambda e: self.save_draft())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind("<Control-Return>", lambda e: self.add_word())  # Windows/Linux
        self.root.bind("<Command-Return>", lambda e: self.add_word())   # macOS
        self.definition_text.bind("<Control-Return>", self.handle_definition_newline)  # Windows/Linux
        self.definition_text.bind("<Command-Return>", self.handle_definition_newline)   # macOS

        # try auto-load dict.json
        script_dir = os.path.dirname(os.path.abspath(__file__))
        default_path = os.path.join(script_dir, DEFAULT_DICT)
        if os.path.exists(default_path):
            self.dict_lookup.load(default_path)
        # 在 _build_ui 方法末尾，现有绑定语句后面添加：
        self.tree.bind("<Delete>", self.delete_selected_item)
        # 助记框：按 Command+Enter/Ctrl+Enter 换行，普通 Enter 触发添加词条
        self.example_text.bind("<Control-Return>", self.handle_example_newline)  # Windows
        self.example_text.bind("<Command-Return>", self.handle_example_newline)   # macOS
        self.example_text.bind("<Return>", lambda e: self.add_word())  # 普通Enter添加词条
    

    # ---------------- UI Helpers ----------------
    def status(self, txt):
        """安全地更新状态栏（确保在主线程执行）"""
        def update_status():
            self.status_var.set(txt)
        # 使用after将操作提交到主线程
        self.root.after(0, update_status)
    def clear_inputs(self):
        self.word_entry.delete(0, tk.END)
        self.phonetic_entry.delete(0, tk.END)
        self.pos_entry.delete(0, tk.END)
        self.definition_text.delete("1.0", tk.END)
        self.example_text.delete("1.0", tk.END)
        self.word_entry.focus_set()

    # ---------------- Dictionary Functions ----------------
    def load_dict_file(self):
        p = filedialog.askopenfilename(title="Choose dict.json",
                                       filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if p:
            self.dict_lookup.load(p)
            self.status(f"Loaded dict: {p}")

    def autofill_from_dict(self):
        w = self.word_entry.get().strip()
        if not w:
            messagebox.showinfo("提示", "请输入单词后再自动补全")
            return

        res = self.dict_lookup.lookup(w)
        if not res:
            if phon:
                self.phonetic_entry.delete(0, tk.END)
                self.phonetic_entry.insert(0, phon)
            self.status(f"未在本地词典中找到：{w}")
            return

        # 强制从 JSON 词典提取音标，即使输入框已有内容也覆盖
        self.phonetic_entry.delete(0, tk.END)
        if res and res.get("phonetic"):
            # 从 dict.json 中提取音标并填充
            self.phonetic_entry.insert(0, res["phonetic"])
        else:
            # 词典中无音标时，保持空（不自动生成）
            pass

        if res.get("pos"):
            p = res["pos"]
            if len(p) <= 3 and not p.endswith("."):
                p += "."
            self.pos_entry.delete(0, tk.END)
            self.pos_entry.insert(0, p)

        trans = res.get("translations", []) or []
        txt = "\n".join(trans) if trans else "\n".join(d for d in res.get("definitions", []) or [])
        self.definition_text.delete("1.0", tk.END)
        self.definition_text.insert("1.0", txt)

        self.status(f"已从本地词典补全：{w}")
        # 自动跳到 example 框
        self.example_text.focus_set()


            # ---------------- Add / Edit ----------------
    def add_word(self, is_auto=False):  # 添加is_auto参数标识是否自动添加
        word = self.word_entry.get().strip()
        if not word:
            return

        phon = self.phonetic_entry.get().strip()

        if not phon:
            res = self.dict_lookup.lookup(word)
            if res and res.get("phonetic"):
                phon = res["phonetic"]

        pos = self.pos_entry.get().strip()
        definition = self.definition_text.get("1.0", tk.END).strip()
        example = self.example_text.get("1.0", tk.END).strip()

        if not definition:
            messagebox.showwarning("输入错误", "释义不能为空")
            return

        item = {
            "word": word,
            "phonetic": phon,
            "pos": pos,
            "definition": definition,
            "example": example
        }

        self.data.append(item)
        self._tree_insert(item)
        self.clear_inputs()
        self.status(f"已添加 {len(self.data)} 条词条")

        # 只有自动添加（剪贴板监听）时才显示通知
        if is_auto:
            # 显示单词和释义（取前30个字符防止通知过长）
            short_def = definition[:30] + "..." if len(definition) > 30 else definition
            self.show_temp_notification(f"已添加: {word}\n释义: {short_def}")


    # 放在 add_word / on_tree_double 之后
    def delete_selected_item(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return

        indices_to_delete = [self.tree.index(item_id) for item_id in sel]
        indices_to_delete.sort(reverse=True)
        for idx in indices_to_delete:
            del self.data[idx]
        for item_id in sel:
            self.tree.delete(item_id)

        self.status(f"已删除 {len(indices_to_delete)} 条词条。剩余 {len(self.data)} 条。")



    def _tree_insert(self, item):
        definition = item.get("definition", "").replace("\n", " | ")
        self.tree.insert("", "end", values=(item["word"],
                                            item.get("phonetic", ""),
                                            item.get("pos", ""),
                                            definition))

    def on_tree_double(self, event):
        sel = self.tree.selection()
        if not sel:
            return

        it = sel[0]
        idx = self.tree.index(it)
        item = self.data[idx]

        self.word_entry.delete(0, tk.END)
        self.word_entry.insert(0, item["word"])

        self.phonetic_entry.delete(0, tk.END)
        self.phonetic_entry.insert(0, item.get("phonetic", ""))

        self.pos_entry.delete(0, tk.END)
        self.pos_entry.insert(0, item.get("pos", ""))

        self.definition_text.delete("1.0", tk.END)
        self.definition_text.insert("1.0", item.get("definition", ""))

        self.example_text.delete("1.0", tk.END)
        self.example_text.insert("1.0", item.get("example", ""))

        del self.data[idx]
        self.tree.delete(it)
        self.status("编辑模式：修改后回车 添加词条 保存更改")


    def handle_definition_newline(self, event):
        """处理释义框的 Ctrl+Enter/Command+Enter 快捷键，插入换行"""
        # 在当前光标位置插入换行
        self.definition_text.insert(tk.INSERT, "\n")
        # 返回"break"阻止事件继续传播（避免触发其他全局绑定）
        return "break"


    # 新增助记框换行处理方法
    def handle_example_newline(self, event):
        """处理助记框的 Command+Enter/Ctrl+Enter 快捷键，插入换行"""
        self.example_text.insert(tk.INSERT, "\n")
        return "break"

    def on_tree_double(self, event):
        sel = self.tree.selection()
        if not sel: return
        it = sel[0]
        idx = self.tree.index(it)
        item = self.data[idx]
        # populate inputs for edit
        self.word_entry.delete(0, tk.END); self.word_entry.insert(0, item["word"])
        self.phonetic_entry.delete(0, tk.END); self.phonetic_entry.insert(0, item.get("phonetic",""))
        self.pos_entry.delete(0, tk.END); self.pos_entry.insert(0, item.get("pos",""))
        self.definition_text.delete("1.0", tk.END); self.definition_text.insert("1.0", item.get("definition",""))
        self.example_text.delete("1.0", tk.END); self.example_text.insert("1.0", item.get("example",""))
        # remove existing so user can re-add after editing
        del self.data[idx]
        self.tree.delete(it)
        self.status("编辑模式：修改后点击 添加词条 保存更改")



    # 修改show_temp_notification方法，添加Windows系统支持和监听状态判断
    def show_temp_notification(self, message):
        """仅在剪贴板监听时显示通知，根据系统选择合适的通知方式"""
        # 只有在剪贴板监听状态下才显示通知
        if not self.clipboard_listening:
            return

        if sys.platform == "darwin":
            # macOS使用AppleScript通知
            script = f'''
            display notification "{message}" with title "Anki Maker" sound name "default"
            '''
            try:
                subprocess.run(
                    ["osascript", "-e", script],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
            except Exception:
                self.status(message)
        elif sys.platform.startswith("win"):
            # Windows使用toast通知
            try:
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(
                    "Anki Maker",
                    message,
                    duration=3,  # 显示3秒
                    icon_path=None,  # 可添加自定义图标路径
                    threaded=True
                )
            except ImportError:
                # 若未安装win10toast，使用消息框
                tk.messagebox.showinfo("Anki Maker", message)
            except Exception as e:
                self.status(f"通知失败: {message}")
        else:
            # 其他系统使用状态栏提示
            self.status(message)

    # ---- 新增的删除方法 ----
    def delete_selected_item(self, event=None):
        sel = self.tree.selection()
        if not sel:
            return

        # 从 data 列表和 tree 视图中同时删除
        # 必须倒序删除，防止索引变化
        indices_to_delete = []
        items_to_delete_from_tree = []

        for item_id in sel:
            idx = self.tree.index(item_id)
            indices_to_delete.append(idx)
            items_to_delete_from_tree.append(item_id)

        # 倒序删除 data 列表
        indices_to_delete.sort(reverse=True)
        for idx in indices_to_delete:
            del self.data[idx]

        # 删除 Treeview 项
        for item_id in items_to_delete_from_tree:
            self.tree.delete(item_id)

        self.status(f"已删除 {len(indices_to_delete)} 条词条。剩余 {len(self.data)} 条。")


    # ---- 新增的清空方法 ----
    def clear_all_items(self):
        if not self.data:
            return
        if messagebox.askyesno("⚠️ 确认清空", f"确定要清空所有 {len(self.data)} 条词条吗？\n此操作不可撤销！"):
            self.data = []
            self.tree.delete(*self.tree.get_children())
            self.status("已清空所有词条")
            self.save_draft()  # 清空后立即保存


    # ---------------- Search ----------------
    def filter_tree(self, event=None):
        q = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for it in self.data:
            if not q or q in it.get("word", "").lower() or q in it.get("definition", "").lower():
                self._tree_insert(it)

    # ---------------- Export ----------------
    def export_csv(self):
        if not self.data:
            messagebox.showwarning("提示", "请先添加词条")
            return

        ensure_export_folder()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(EXPORT_FOLDER, f"anki_vocab_{ts}.csv")

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["word", "phonetic", "pos", "definition", "example"])
            writer.writeheader()
            for it in self.data:
                writer.writerow(it)

        open_folder(os.path.abspath(EXPORT_FOLDER))
        self.status(f"已导出 CSV：{os.path.basename(path)}")

    def export_json(self):
        if not self.data:
            messagebox.showwarning("提示", "请先添加词条")
            return

        ensure_export_folder()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(EXPORT_FOLDER, f"anki_vocab_{ts}.json")

        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

        open_folder(os.path.abspath(EXPORT_FOLDER))
        self.status(f"已导出 JSON：{os.path.basename(path)}")



    def export_apkg(self):
        if not self.data:
            messagebox.showwarning("警告", "没有单词可导出！")
            return

        ensure_export_folder()
        deck = genanki.Deck(1984567890, "My Vocabulary")

        for it in self.data:  # ✅ 这里用 self.data 而不是 self.words
            note = genanki.Note(
                model=vocab_model,  # 你自己定义的 model
                fields=[
                    it['word'],
                    it.get('phonetic',''),
                    it.get('pos',''),
                    it.get('definition',''),
                    it.get('example','')
                ]
            )
            deck.add_note(note)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_path = os.path.join(EXPORT_FOLDER, f"anki_vocab_{ts}.apkg")

        try:
            genanki.Package(deck).write_to_file(file_path)
            self.status(f"已导出 APKG: {file_path}")
            open_folder(os.path.abspath(EXPORT_FOLDER))
            messagebox.showinfo("成功", f"卡组已保存到：\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败：{e}")


    def export_md(self):
        if not self.data:
            messagebox.showwarning("提示", "请先添加词条")
            return

        ensure_export_folder()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(EXPORT_FOLDER, f"anki_vocab_{ts}.md")

        with open(path, "w", encoding="utf-8") as f:
            for it in self.data:
                f.write(f"### {it['word']}\n")
                if it.get("phonetic"):
                    f.write(f"*Phonetic*: {it['phonetic']}\n")
                if it.get("pos"):
                    f.write(f"*POS*: {it['pos']}\n")
                f.write(f"*Definition*: {it['definition']}\n")
                if it.get("example"):
                    f.write(f"*Example*: {it['example']}\n")
                f.write("\n---\n\n")

        open_folder(os.path.abspath(EXPORT_FOLDER))
        self.status(f"已导出 MD：{os.path.basename(path)}")

    def toggle_clipboard_listen(self):
        """切换剪贴板监听状态"""
        if self.clipboard_listening:
            self.clipboard_listening = False
            self.status("已关闭剪贴板监听")
        else:
            self.clipboard_listening = True
            self.status("已开启剪贴板监听...")
            # 启动监听线程
            threading.Thread(target=self.clipboard_listen_loop, daemon=True).start()

    def clipboard_listen_loop(self):
        """剪贴板监听循环"""
        while self.clipboard_listening:
            try:
                # 获取剪贴板内容
                current = self.root.clipboard_get().strip()
                
                # 检查是否为新内容且是单个英文单词
                if current and current != self.last_clipboard_content and self.is_single_english_word(current):
                    self.last_clipboard_content = current
                    
                    # 在主线程中执行UI操作
                    self.root.after(0, self.process_clipboard_word, current)
                
                # 短暂休眠减少CPU占用
                time.sleep(1)
            except Exception as e:
                # 忽略剪贴板访问错误（比如剪贴板内容不是文本）
                time.sleep(1)

    def is_single_english_word(self, text):
        """判断是否为单个英文单词"""
        # 仅包含字母，可能包含撇号（如don't）或连字符（如mother-in-law）
        return bool(re.fullmatch(r"[a-zA-Z'-]+", text))

    def process_clipboard_word(self, word):
        """处理剪贴板获取的单词"""
        # 填充单词到输入框
        self.word_entry.delete(0, tk.END)
        self.word_entry.insert(0, word)
        
        # 自动补全单词信息
        self.autofill_from_dict()
        
        # 自动添加到列表，标记为自动添加
        self.add_word(is_auto=True)
        
        self.status(f"从剪贴板添加单词: {word}")
    # ---------------- Draft / Autosave ----------------
    def save_draft(self):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        self.status(f"已暂存草稿 ({len(self.data)} 条)")

    def _load_draft(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                for it in self.data:
                    self._tree_insert(it)
                self.status(f"已加载草稿 ({len(self.data)} 条)")
            except Exception:
                self.data = []

    def import_json_draft(self):
        p = filedialog.askopenfilename(title="选择 JSON 草稿", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if p:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                self.tree.delete(*self.tree.get_children())
                for it in self.data:
                    self._tree_insert(it)
                self.status(f"已导入 JSON 草稿 ({len(self.data)} 条)")
            except Exception as e:
                messagebox.showerror("错误", f"加载失败: {e}")

    def _autosave_loop(self):
        while self.autosave_running:
            time.sleep(AUTOSAVE_INTERVAL)
            if self.data:
                self.save_draft()

    def _start_autosave(self):
        t = threading.Thread(target=self._autosave_loop, daemon=True)
        t.start()


    # ---------------- Search ----------------
    def filter_tree(self, event=None):
        q = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for it in self.data:
            if not q or q in it.get("word", "").lower() or q in it.get("definition", "").lower():
                self._tree_insert(it)

    # ---------------- tutorial ----------------
    def show_tutorial(self):
        """显示使用教程窗口"""
        tutorial_window = TutorialWindow(self.root)
        self.root.wait_window(tutorial_window)


    # ---------------- Close ----------------
    def on_close(self):
        self.autosave_running = False
        self.save_draft()
        self.root.destroy()


# ---------------- Main ----------------
def main():
    root = tk.Tk()
    app = AnkiMakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
