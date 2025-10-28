'''
3.1新功能
- 对于提取文件的生词的功能:增加了对txt,PDF,word的支持

3.0新功能
- 增加了一个全新的功能:自动提取一个md文件里面的生词(生词指的是,牛津3000词以外,高考英语3500以外,以及一些基础的词汇),然后制作为词条
- 解决了每次打开软件都要求导入词典的问题
- 解决了一个小BUG

2.4新功能
- 加快了软件的启动速度
- 增加了"导入词典"的功能,防止词典没找到
- 优化了按钮的排布
- 美化了"使用教程"

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
import nltk
from nltk.tokenize import word_tokenize
from nltk.stem import WordNetLemmatizer
from nltk.corpus import wordnet
import re
import tkinter.scrolledtext as scrolledtext  # 添加这行导入
import chardet  # 需要安装：pip install chardet


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
        "content": "1.在上方输入框依次填写：单词、词性、释义和助记.\n ps:当我们填完一个框框之后,按下'Enter'键,便可以跳转到下一个框框.这是我喜欢的.\n\n2.点击「➕ 添加词条」按钮或按回车完成添加\n\n3.添加的单词会显示在下方列表中\n\n4.比较贴心的是我们不需要填写音标.程序会调用本地词典自动补入\5如果要换行,则按下'Command或Control + Enter回车'"
    },
    {
        "title": "自动补全功能",
        "content": "1.输入单词的英文后，点击「🔁自动补全」按钮（或按Ctrl+E/Cmd+E）\n\n2.系统会从本地词典(dict.json)自动填充音标、词性和释义,随后跳转到'助记'这个框框.\n\n3.你可以在自动填充后手动修改内容"
    },
    {
        "title": "剪贴板监听",
        "content": "1.点击「📋 开始/结束监听剪贴板」按钮开启功能\n\n2.当复制单个英文单词时，程序会自动：\n   - 识别单词并填充到输入框\n   - 自动补全单词信息\n   - 自动添加到列表\n\n3.再次点击按钮可关闭监听"
    },
    {
        "title": "导出功能",
        "content": "1.完成单词添加后，可选择多种导出格式：\n   - CSV：适合导入Excel或其他工具\n   - JSON：用于备份或后续导入\n   - APKG：可直接导入Anki的卡组文件\n   - Markdown：适合阅读和分享\n\n2. 导出文件会保存在exports文件夹中"
    },
    {
        "title": "草稿功能",
        "content": "1.程序会每5秒自动保存当前单词列表\n\n2.可点击「🧾 暂存草稿」手动保存\n\n3.点击「📂 导入草稿」可加载之前保存的JSON文件\n\n4. 关闭程序时会自动保存当前内容"
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

#---------提取文件的词汇-------------
# 从 1.py 移植的词性映射和词形还原函数
def get_wordnet_pos(word):
    tag = nltk.pos_tag([word])[0][1][0].upper()
    mapping = {'J': wordnet.ADJ, 'N': wordnet.NOUN, 'V': wordnet.VERB, 'R': wordnet.ADV}
    return mapping.get(tag, wordnet.NOUN)

def lemmatize_word(word, lemmatizer):
    return lemmatizer.lemmatize(word.lower(), get_wordnet_pos(word))

# 处理 MD 文件的函数（修改为返回过滤后的单词列表，适应 Anki_Maker 的 UI）
def process_md_file(md_file):
    lemmatizer = WordNetLemmatizer()
    try:
        with open(md_file, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        return None, f"读取文件失败：{str(e)}"

    # 提取英文单词并词形还原
    words = re.findall(r"[a-zA-Z']+", text)
    lemmatized = set(lemmatize_word(w, lemmatizer) for w in words)

    # 读取停用词
    script_dir = os.path.dirname(os.path.abspath(__file__))
    oxford_file = os.path.join(script_dir, "stopwords.txt")
    if not os.path.exists(oxford_file):
        return None, f"找不到 stopwords.txt 文件\n路径：{oxford_file}"

    with open(oxford_file, "r", encoding="utf-8") as f:
        oxford_words = set(line.strip().lower() for line in f)

    # 过滤停用词
    extra_stopwords = {"ve", "ll", "d", "m", "re", "s", "t", "isn", "wouldn"}
    filtered = sorted(lemmatized - oxford_words - extra_stopwords)
    return filtered, None

def detect_file_encoding(file_path):
    """检测文件编码格式"""
    with open(file_path, 'rb') as f:
        # 读取前10000字节用于检测（平衡准确性和性能）
        raw_data = f.read(10000)
    
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    confidence = result['confidence']
    
    # 处理检测失败的情况，提供常见备选编码
    if not encoding or confidence < 0.7:
        return ['utf-8', 'gbk', 'gb2312', 'utf-16', 'latin-1']
    return [encoding, 'utf-8', 'gbk']  # 优先使用检测到的编码，再尝试备选

def process_txt_file(txt_file):
    """处理TXT文件并返回过滤后的单词列表（增强编码支持）"""
    lemmatizer = WordNetLemmatizer()
    text = None
    
    # 检测文件编码并尝试多种编码读取
    encodings = detect_file_encoding(txt_file)
    for encoding in encodings:
        try:
            with open(txt_file, "r", encoding=encoding) as f:
                text = f.read()
            break  # 读取成功则退出编码尝试
        except UnicodeDecodeError:
            continue  # 尝试下一种编码
        except Exception as e:
            return None, f"读取TXT文件失败：{str(e)}"
    
    if text is None:
        return None, (
            "无法读取文件，可能原因：\n"
            "1. 文件编码格式不识别\n"
            "2. 文件损坏或不是文本文件"
        )
    
    # 提取英文单词并词形还原（后续逻辑不变）
    words = re.findall(r"[a-zA-Z']+", text)
    lemmatized = set(lemmatize_word(w, lemmatizer) for w in words)
    return filter_stopwords(lemmatized)

def process_pdf_file(pdf_file):
    """处理PDF文件并返回过滤后的单词列表（增强版）"""
    lemmatizer = WordNetLemmatizer()
    text = ""
    
    # 检查文件是否存在
    if not os.path.exists(pdf_file):
        return None, f"文件不存在: {pdf_file}"
    
    # 检查文件是否为空
    if os.path.getsize(pdf_file) == 0:
        return None, "PDF文件为空"
    
    # 尝试多种PDF提取方案
    extraction_methods = [
        ("PyPDF2", extract_with_pypdf2),
        ("textract", extract_with_textract),
        ("pdfplumber", extract_with_pdfplumber)  # 增加pdfplumber作为备选
    ]
    
    for method_name, extract_func in extraction_methods:
        try:
            text = extract_func(pdf_file)
            if text and len(text.strip()) > 0:
                break  # 提取成功则停止尝试其他方法
        except Exception as e:
            print(f"使用{method_name}提取失败: {str(e)}")  # 仅在控制台打印，不中断
    
    if not text or len(text.strip()) == 0:
        return None, (
            "无法从PDF中提取文本内容。可能原因：\n"
            "1. PDF是扫描件（图片格式）\n"
            "2. PDF被加密保护\n"
            "3. 格式损坏或不规范"
        )
    
    # 提取英文单词并词形还原
    words = re.findall(r"[a-zA-Z']+", text)
    lemmatized = set(lemmatize_word(w, lemmatizer) for w in words)
    
    # 过滤停用词
    return filter_stopwords(lemmatized)

# 辅助提取函数
def extract_with_pypdf2(pdf_file):
    """使用PyPDF2提取文本"""
    text = ""
    with open(pdf_file, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        # 检查是否加密
        if reader.is_encrypted:
            try:
                # 尝试空密码解密（部分PDF仅限制编辑，不限制阅读）
                reader.decrypt("")
            except Exception:
                raise Exception("PDF已加密，需要密码才能提取内容")
        
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text

def extract_with_textract(pdf_file):
    """使用textract提取文本（增强编码容错）"""
    try:
        # 先尝试默认编码
        raw_data = textract.process(pdf_file)
        return raw_data.decode('utf-8', errors='replace')  # 无法解码的字符用�替代
    except UnicodeDecodeError:
        # 尝试GBK编码
        try:
            return raw_data.decode('gbk', errors='replace')
        except:
            # 最后尝试latin-1（几乎能解码所有字节，但可能乱码）
            return raw_data.decode('latin-1')
def extract_with_pdfplumber(pdf_file):
    """使用pdfplumber提取文本（需要额外安装pdfplumber）"""
    text = ""
    try:
        import pdfplumber  # 延迟导入，避免未安装时出错
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except ImportError:
        raise Exception("pdfplumber未安装，无法使用此提取方法")
    except Exception as e:
        raise Exception(f"pdfplumber提取失败: {str(e)}")
def process_word_file(word_file):
    """处理Word文件(.docx)并返回过滤后的单词列表（增强编码支持）"""
    lemmatizer = WordNetLemmatizer()
    try:
        raw_data = textract.process(word_file)
        # 尝试多种编码解码
        encodings = ['utf-8', 'gbk', 'gb2312']
        text = None
        for encoding in encodings:
            try:
                text = raw_data.decode(encoding, errors='ignore')
                if text.strip():  # 确保解码结果非空
                    break
            except:
                continue
        if not text:
            return None, "无法解码Word文档内容"
    except Exception as e:
        return None, f"读取Word文件失败：{str(e)}"
    
    # 后续处理逻辑不变
    words = re.findall(r"[a-zA-Z']+", text)
    lemmatized = set(lemmatize_word(w, lemmatizer) for w in words)
    return filter_stopwords(lemmatized)


def filter_stopwords(word_set):
    """过滤停用词并返回处理结果"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    oxford_file = os.path.join(script_dir, "stopwords.txt")
    
    if not os.path.exists(oxford_file):
        return None, f"找不到 stopwords.txt 文件\n路径：{oxford_file}"
    
    with open(oxford_file, "r", encoding="utf-8") as f:
        oxford_words = set(line.strip().lower() for line in f)
    
    # 过滤停用词
    extra_stopwords = {"ve", "ll", "d", "m", "re", "s", "t", "isn", "wouldn"}
    filtered = sorted(word_set - oxford_words - extra_stopwords)
    return filtered, None


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
        nltk.download('punkt', quiet=True)
        nltk.download('averaged_perceptron_tagger', quiet=True)
        nltk.download('wordnet', quiet=True)
            # 剪贴板监听相关
        self.clipboard_listening = False
        self.last_clipboard_content = ""
        self.clipboard_thread = None
        self.stop_clipboard_event = threading.Event()  # 用于优雅停止线程

    def _create_widgets(self):
        # 标题标签
        self.title_label = ttk.Label(
            self, 
            text="", 
            font=("Arial", 30, "bold")
        )
        self.title_label.pack(pady=(15, 10), padx=20, anchor="w")
        
        # 内容文本框
        self.content_text = tk.Text(
            self, 
            wrap=tk.WORD, 
            width=70, 
            height=12,
            font=("Arial", 20),
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
        self.root.title("Anki Maker Version 3.0")
        self.data = []
        self.clipboard_listening = False  # 监听状态
        self.last_clipboard_content = ""  # 上次剪贴板内容缓存
        self.dict_lookup = DictLookup()
        self.autosave_running = True
        self._build_ui()
        self._load_draft()
        self._start_autosave()

        # load local dict.json
        # 初始化空词典，后续通过线程加载
        self.dict_lookup = DictLookup()  # 先初始化空词典
        self.default_dict_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), DEFAULT_DICT)
        self.status("程序启动中...")
        # 延迟0.5秒再启动词典加载线程，优先保证窗口显示
        self.root.after(500, lambda: threading.Thread(
            target=self._load_dict_in_background, daemon=True
        ).start())

    def _check_and_load_default_dict(self):
        """检查并加载默认词典"""
        if os.path.exists(self.default_dict_path):
            self.dict_lookup.load(self.default_dict_path)
            self.status(f"已加载默认词典，共 {len(self.dict_lookup.data)} 个词条")
        else:
            self.status(f"未找到默认词典: {self.default_dict_path}")

    def check_first_run(self):
        if not os.path.exists("first_run_flag"):
            with open("first_run_flag", "w") as f:
                f.write("1")
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
        # 替换原来的按钮创建代码
        def create_extra_buttons():
            ttk.Button(btn_frame, text="📤 导出 CSV", command=self.export_csv).grid(row=1, column=0, padx=6)
            ttk.Button(btn_frame, text="📤 导出 JSON", command=self.export_json).grid(row=1, column=1, padx=6)
            ttk.Button(btn_frame, text="📤 导出 APKG", command=self.export_apkg).grid(row=1, column=2, padx=6)
            ttk.Button(btn_frame, text="📤 导出 MD", command=self.export_md).grid(row=1, column=3, padx=6)
            ttk.Button(btn_frame, text="🗑 删除选中", command=self.delete_selected_item).grid(row=2, column=0, padx=6)
            ttk.Button(btn_frame, text="🧹 清空所有", command=self.clear_all_items).grid(row=2, column=2, padx=6)
            ttk.Button(btn_frame, text="📋 开始/结束监听剪贴板", command=self.toggle_clipboard_listen).grid(row=3, column=2, padx=6)
            ttk.Button(btn_frame, text="📖 使用教程", command=self.show_tutorial).grid(row=2, column=1, padx=6)
            ttk.Button(btn_frame, text="📂 导入词典(记得先把zip解压)", command=self.load_dict_file).grid(row=2, column=3, padx=6)
            ttk.Button(btn_frame, text="📄 批量导入 TXT", command=self.import_txt_file).grid(row=3, column=0, padx=6)
            ttk.Button(btn_frame, text="📄 从MD/PDF/WORD/TXT提取单词", command=self.select_md_file).grid(row=3, column=1, padx=6)

        # 主按钮先创建
        ttk.Button(btn_frame, text="➕ 添加词条", command=self.add_word).grid(row=0, column=0, padx=6)
        ttk.Button(btn_frame, text="🧾 暂存草稿", command=self.save_draft).grid(row=0, column=1, padx=6)
        ttk.Button(btn_frame, text="📂 导入草稿", command=self.import_json_draft).grid(row=0, column=2, padx=6)
        ttk.Button(btn_frame, text="🔁 自动补全 (Cmd/Ctrl+E)", command=self.autofill_from_dict).grid(row=0, column=3, padx=6)

        # 延迟创建其他按钮
        self.root.after(300, create_extra_buttons)
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
        # 先显示主窗口
        self.root.update_idletasks()
        self.root.deiconify()

        # 延迟创建导出按钮等非核心组件
        def create_extra_buttons():
            # 这里放原来的导出按钮、监听按钮等代码
            ttk.Button(btn_frame, text="📤 导出 CSV", command=self.export_csv).grid(row=1, column=0, padx=6)
            ttk.Button(btn_frame, text="📤 导出 JSON", command=self.export_json).grid(row=1, column=1, padx=6)
            # ... 其他按钮 ...

        # 替换原来的按钮创建代码，改为延迟创建

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
        p = filedialog.askopenfilename(title="选择词典文件",
                                    filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if p:
            self.dict_lookup.load(p)
            self.status(f"已加载词典：{p}，共 {len(self.dict_lookup.data)} 个词条")
                
    def refresh_treeview(self):
        """刷新树状视图，显示最新的单词列表"""
        # 先清空现有内容
        self.tree.delete(*self.tree.get_children())
        # 重新添加所有数据
        for item in self.data:
            self._tree_insert(item)


    def autofill_from_dict(self):
        """从词典自动填充单词的音标、词性和释义"""
        word = self.word_entry.get().strip()
        if not word:
            self.status("请先输入单词")
            return

        # 显示加载状态
        self.status(f"正在查询 {word} 的信息...")
        
        # 从词典查询单词
        result = self.dict_lookup.lookup(word)
        if not result:
            self.status(f"未在词典中找到 {word} 的信息")
            return

        # 填充音标（修复变量名拼写错误：phon → phonetic）
        phonetic = result.get("phonetic", "")
        if phonetic:
            self.phonetic_entry.delete(0, tk.END)
            self.phonetic_entry.insert(0, phonetic)

        # 填充词性
        pos = result.get("pos", "")
        if pos:
            self.pos_entry.delete(0, tk.END)
            self.pos_entry.insert(0, pos)

        # 填充释义
        translations = result.get("translations", [])
        if translations:
            self.definition_text.delete("1.0", tk.END)
            self.definition_text.insert("1.0", "\n".join(translations))

        # 自动聚焦到助记框，方便用户输入
        self.example_text.focus_set()
        
        self.status(f"已自动补全 {word} 的信息")


    # 添加剪贴板监听控制方法
    def toggle_clipboard_listening(self):
        """切换剪贴板监听状态"""
        if self.clipboard_listening:
            # 停止监听
            self.clipboard_listening = False
            self.stop_clipboard_event.set()
            self.status("已停止监听剪贴板")
            self.clipboard_btn.config(text="📋 开始监听剪贴板")
        else:
            # 开始监听
            self.clipboard_listening = True
            self.stop_clipboard_event.clear()
            self.clipboard_thread = threading.Thread(
                target=self._clipboard_listener,
                daemon=True
            )
            self.clipboard_thread.start()
            self.status("已开始监听剪贴板...")
            self.clipboard_btn.config(text="📋 停止监听剪贴板")

    # 添加核心监听逻辑
    def _clipboard_listener(self):
        """剪贴板监听线程"""
        while self.clipboard_listening and not self.stop_clipboard_event.is_set():
            try:
                # 获取剪贴板内容
                current_content = self.root.clipboard_get().strip()
                
                # 检查内容是否变化且是单个英文单词
                if (current_content and 
                    current_content != self.last_clipboard_content and 
                    self._is_single_english_word(current_content)):
                    
                    self.last_clipboard_content = current_content
                    self._process_clipboard_word(current_content)
                    
            except Exception as e:
                # 忽略剪贴板访问错误（如无内容时）
                pass
                
            # 短暂休眠减少CPU占用
            time.sleep(0.5)

    # 添加辅助方法
    def _is_single_english_word(self, text):
        """判断是否为单个英文单词"""
        # 仅包含字母和可能的撇号（如don't）
        return bool(re.fullmatch(r"[a-zA-Z']+", text))

    def _process_clipboard_word(self, word):
        """处理剪贴板获取的单词"""
        # 在主线程中更新UI
        self.root.after(0, lambda: self._handle_clipboard_word_ui(word))
        
        # 发送系统通知
        try:
            notification_title = "Anki Maker"
            notification_message = f"已捕获单词: {word}"
            notification.notify(
                title=notification_title,
                message=notification_message,
                timeout=2
            )
            
            # MacOS额外的AppleScript通知（更优雅）
            if sys.platform == "darwin":
                applescript = f'''
                display notification "{notification_message}" with title "{notification_title}" sound name "default"
                '''
                subprocess.run(["osascript", "-e", applescript])
        except Exception:
            pass

    def _handle_clipboard_word_ui(self, word):
        """在UI线程中处理单词（自动补全并添加）"""
        # 填充单词输入框
        self.word_entry.delete(0, tk.END)
        self.word_entry.insert(0, word)
        
        # 自动补全单词信息
        self.auto_complete()
        
        # 自动添加到列表
        self.add_entry()



                    # ---------------- Add / Edit ----------------
    def add_word(self, is_auto=False, skip_validation=False):  # 增加skip_validation参数
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

        # 只有非跳过验证模式且释义为空时才显示警告
        if not skip_validation and not definition:
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


    def clear_inputs(self):
        """清空所有输入框"""
        self.word_entry.delete(0, tk.END)
        self.phonetic_entry.delete(0, tk.END)
        self.pos_entry.delete(0, tk.END)
        self.definition_text.delete("1.0", tk.END)
        self.example_text.delete("1.0", tk.END)


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


    def select_file_for_word_extraction(self):
        """选择文件并提取生词"""
        file_path = filedialog.askopenfilename(
            title="选择文件提取生词",
            filetypes=[
                ("所有支持的文件", "*.txt *.pdf *.docx *.md"),
                ("文本文件", "*.txt"),
                ("PDF文件", "*.pdf"),
                ("Word文件", "*.docx"),
                ("Markdown文件", "*.md"),
                ("所有文件", "*.*")
            ]
        )
        
        if not file_path:
            return
        
        self.status(f"正在处理文件: {os.path.basename(file_path)}...")
        
        # 根据文件扩展名选择相应的处理函数
        try:
            if file_path.endswith(".md"):
                words, error = process_md_file(file_path)
            elif file_path.endswith(".txt"):
                words, error = process_txt_file(file_path)
            elif file_path.endswith(".pdf"):
                words, error = process_pdf_file(file_path)
            elif file_path.endswith(".docx"):
                words, error = process_word_file(file_path)
            else:
                messagebox.showerror("错误", "不支持的文件格式")
                return
                
            if error:
                messagebox.showerror("处理失败", error)
                self.status("文件处理失败")
                return
                
            if not words:
                messagebox.showinfo("结果", "未找到符合条件的生词")
                self.status("文件处理完成，未发现生词")
                return
                
            # 显示提取的生词并询问是否添加
            self.show_extracted_words(words)
            
        except Exception as e:
            messagebox.showerror("错误", f"处理文件时出错: {str(e)}")
            self.status("文件处理出错")

    def show_extracted_words(self, words):
        """显示提取的生词并提供添加选项"""
        # 创建弹窗显示提取的单词
        dialog = tk.Toplevel(self.root)
        dialog.title(f"提取到 {len(words)} 个生词")
        dialog.geometry("600x400")
        dialog.transient(self.root)
        dialog.grab_set()
        
        # 添加滚动文本框
        text = scrolledtext.ScrolledText(dialog, wrap=tk.WORD)
        text.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        text.insert(tk.END, "\n".join(words))
        text.config(state=tk.DISABLED)
        
        # 添加按钮
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        
        def add_all():
            """添加所有单词"""
            added_count = 0
            for word in words:
                # 检查是否已存在该单词
                exists = any(item["word"].lower() == word.lower() for item in self.data)
                if not exists:
                    # 自动填充单词信息
                    self.word_entry.delete(0, tk.END)
                    self.word_entry.insert(0, word)
                    self.autofill_from_dict()
                    
                    # 获取自动填充的信息
                    phon = self.phonetic_entry.get().strip()
                    pos = self.pos_entry.get().strip()
                    definition = self.definition_text.get("1.0", tk.END).strip()
                    
                    # 添加到列表
                    self.data.append({
                        "word": word,
                        "phonetic": phon,
                        "pos": pos,
                        "definition": definition,
                        "example": ""
                    })
                    added_count += 1
            
            self.refresh_treeview()
            self.clear_inputs()
            self.status(f"已添加 {added_count} 个生词")
            dialog.destroy()
        
        ttk.Button(btn_frame, text="全部添加", command=add_all).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)



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

        #后台加载词典
    def _load_dict_in_background(self):
        """后台加载词典，不阻塞UI启动"""
        if os.path.exists(self.default_dict_path):
            try:
                self.dict_lookup.load(self.default_dict_path)
                # 加载完成后更新状态栏（通过主线程）
                self.root.after(0, lambda: self.status(
                    f"✅ 已加载本地词典，共 {len(self.dict_lookup.data)} 个词条"
                ))
            except Exception as e:
                self.root.after(0, lambda: self.status(
                    f"⚠️ 词典加载失败: {str(e)}"
                ))
        else:
            # 未找到词典时更新状态栏
            self.root.after(0, lambda: self.status(
                "⚠️ 未找到本地词典，可通过'导入词典'按钮加载"
            ))
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

        # 在fieldnames中添加'mnemonic'字段
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["word", "phonetic", "pos", "definition", "example", "mnemonic"])
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

        # 定义转义函数，给 [ 和 ] 前添加反斜杠
        def escape_brackets(text):
            if not text:
                return ""
            return text.replace("[", "\\[").replace("]", "\\]")

        with open(path, "w", encoding="utf-8") as f:
            for it in self.data:
                # 对所有可能包含[]的字段进行转义处理
                word = escape_brackets(it['word'])
                phonetic = escape_brackets(it.get('phonetic', ''))
                pos = escape_brackets(it.get('pos', ''))
                definition = escape_brackets(it.get('definition', ''))
                example = escape_brackets(it.get('example', ''))

                f.write(f"### =={word}==\n")
                if phonetic:
                    f.write(f"**音标**: {phonetic}\n")
                if pos:
                    f.write(f"**词性**: {pos}\n")
                f.write(f"**释义**: {definition}\n")
                if example:
                    f.write(f"**助记**: {example}\n")
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

    def start_clipboard_listen(self):
        self.clipboard_listening = True
        self.last_clipboard_content = ""
        self._poll_clipboard()


    def import_txt_file(self):
        """导入TXT文件，每行一个单词（优化版：批量处理，不显示中间过程）"""
        file_path = filedialog.askopenfilename(
            title="选择TXT文件",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")]
        )
        if not file_path:
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                words = [line.strip() for line in f if line.strip() and line.strip().isalpha()]
            
            if not words:
                messagebox.showinfo("提示", "文件中没有有效的英文单词")
                return

            self.status(f"开始导入 {len(words)} 个单词...")
            
            # 批量处理单词（不更新UI，只处理数据）
            success = 0
            fail = 0
            new_items = []
            
            for word in words:
                # 查找词典
                res = self.dict_lookup.lookup(word)
                
                # 构建词条数据
                phon = ""
                pos = ""
                definition = ""
                
                if res:
                    phon = res.get("phonetic", "")
                    pos = res.get("pos", "")
                    trans = res.get("translations", []) or []
                    definition = "\n".join(trans) if trans else "\n".join(d for d in res.get("definitions", []) or [])
                    success += 1
                else:
                    fail += 1
                
                # 添加到临时列表
                new_items.append({
                    "word": word,
                    "phonetic": phon,
                    "pos": pos,
                    "definition": definition,
                    "example": ""
                })
            
            # 一次性更新数据和UI
            self.data.extend(new_items)
            
            # 清空现有树状视图并批量插入新数据
            self.tree.delete(*self.tree.get_children())
            for item in self.data:
                self._tree_insert(item)
            
            # 保存草稿
            self.save_draft()
            
            self.status(f"导入完成！成功: {success}, 失败: {fail} (共 {len(words)} 个单词)")
            messagebox.showinfo("导入结果", 
                            f"共处理 {len(words)} 个单词\n"
                            f"成功获取信息: {success}个\n"
                            f"未在词典中找到: {fail}个")

        except Exception as e:
            messagebox.showerror("错误", f"导入失败: {str(e)}")
    def _parse_and_add_from_txt(self, path):
        """后台读取 txt，每行一个单词，自动补全并添加到 data 列表"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception as e:
            # 回主线程弹窗/状态更新
            self.root.after(0, lambda: messagebox.showerror("错误", f"打开文件失败: {e}"))
            self.root.after(0, lambda: self.status("TXT 导入失败"))
            return

        # 预处理：逐行清理并去重（保留原顺序）
        seen = set()
        words = []
        for ln in lines:
            w = ln.strip()
            if not w:
                continue
            # 只考虑单个英文单词（可包含撇号或连字符）
            if not self.is_single_english_word(w):
                continue
            key = w.lower()
            if key in seen:
                continue
            seen.add(key)
            words.append(w)

        if not words:
            self.root.after(0, lambda: messagebox.showinfo("提示", "未检测到有效单词"))
            self.root.after(0, lambda: self.status("未检测到有效单词"))
            return

        added = 0
        # 对每个单词在主线程中填充并添加（因为涉及 UI 操作）
        for i, w in enumerate(words, start=1):
            def do_one(word=w):
                # 填入输入框
                self.word_entry.delete(0, tk.END)
                self.word_entry.insert(0, word)
                # 尝试用本地词典自动补全（会覆盖音标与释义）
                try:
                    self.autofill_from_dict()
                except Exception:
                    pass
                # 添加到数据（标记为自动添加且跳过验证）
                try:
                    self.add_word(is_auto=True, skip_validation=True)  # 增加参数
                except Exception:
                    # 若某条添加失败，忽略继续
                    pass
            # 在主线程做 UI 操作
            self.root.after(0, do_one)
            added += 1
            # 微小延迟以避免 UI 刷新压力（非阻塞）
            time.sleep(0.05)

        # 完成后通知用户（主线程）
        self.root.after(0, lambda: messagebox.showinfo("完成", f"已导入 {added} 个单词并生成卡片"))
        self.root.after(0, lambda: self.status(f"已从 TXT 导入 {added} 个单词"))







    def _poll_clipboard(self):
        if not self.clipboard_listening:
            return
        try:
            current = self.root.clipboard_get().strip()
            if current and current != self.last_clipboard_content and self.is_single_english_word(current):
                self.last_clipboard_content = current
                self.process_clipboard_word(current)
        except Exception:
            pass
        # 每500ms检查一次，比sleep更响应UI
        self.root.after(500, self._poll_clipboard)

    def toggle_clipboard_listen(self):
        if self.clipboard_listening:
            self.clipboard_listening = False
            self.status("已关闭剪贴板监听")
        else:
            self.start_clipboard_listen()
            self.status("已开启剪贴板监听...")

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
        def load_in_thread():
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # 回到主线程更新UI
                    self.root.after(0, lambda: self._update_draft_ui(data))
                except Exception:
                    pass

        threading.Thread(target=load_in_thread, daemon=True).start()

    def _update_draft_ui(self, data):
        self.data = data
        for it in self.data:
            self._tree_insert(it)
        self.status(f"已加载草稿 ({len(self.data)} 条)")


    def select_md_file(self):
        """选择并处理 MD 文件"""
        path = filedialog.askopenfilename(filetypes=[("Markdown files", "*.md"), ("All files", "*.*")])
        if not path:
            return

        self.status("正在处理 MD 文件...")
        # 用线程处理，避免 UI 卡顿
        threading.Thread(target=self._process_md_thread, args=(path,), daemon=True).start()

    def _process_md_thread(self, md_path):
        """后台线程处理 MD 文件"""
        filtered_words, error = process_md_file(md_path)
        if error:
            self.root.after(0, lambda: messagebox.showerror("错误", error))
            self.root.after(0, lambda: self.status("处理失败"))
            return

        # 处理完成后显示结果
        self.root.after(0, lambda: self.show_md_result(filtered_words, md_path))
        self.root.after(0, lambda: self.status(f"处理完成，共提取 {len(filtered_words)} 个单词"))

    def show_md_result(self, filtered_words, md_path):
        """显示 MD 处理结果的窗口"""
        win = tk.Toplevel(self.root)  # 保存窗口引用
        win.title(f"MD 提取结果 - {os.path.basename(md_path)}")
        win.geometry("600x400")
        win.transient(self.root)  # 置于主窗口之上

        # 结果文本区
        text_area = scrolledtext.ScrolledText(win, wrap=tk.WORD)
        text_area.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)
        text_area.insert(tk.END, "\n".join(filtered_words))
        text_area.configure(state='disabled')

        # 添加"批量导入单词"按钮
        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        
        # 修改按钮回调，添加关闭窗口的逻辑
        def batch_import_and_close():
            self.batch_add_from_md(filtered_words)  # 执行导入
            win.destroy()  # 关闭窗口
        
        ttk.Button(
            btn_frame,
            text="批量导入到单词列表",
            command=batch_import_and_close  # 使用新的回调函数
        ).pack()


    def batch_add_from_md(self, words):
        """将提取的单词批量添加到 Anki 列表（自动补全信息）"""
        for word in words:
            # 自动补全单词信息（复用现有自动补全逻辑）
            self.word_entry.delete(0, tk.END)
            self.word_entry.insert(0, word)
            self.autofill_from_dict()  # 调用现有自动补全方法
            # 添加到列表（简化版，可根据需要调整）
            word = self.word_entry.get().strip()
            phonetic = self.phonetic_entry.get().strip()
            pos = self.pos_entry.get().strip()
            definition = self.definition_text.get("1.0", tk.END).strip()
            mnemonic = self.example_text.get("1.0", tk.END).strip()
            if word:  # 只添加非空单词
                self.data.append({
                    "word": word,
                    "phonetic": phonetic,
                    "pos": pos,
                    "definition": definition,
                    "mnemonic": mnemonic
                })
        # 刷新列表显示
        self.refresh_treeview()
        # 简化提示信息，避免重复弹窗
        self.status(f"已导入 {len(words)} 个单词（空值已过滤）")



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
