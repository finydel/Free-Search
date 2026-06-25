import os
import sys
import json
import random
import time
import threading
import requests
import urllib.parse
import hashlib
import re
import base64
from datetime import datetime
from bs4 import BeautifulSoup

from PyQt6.QtCore import Qt, QUrl, QThread, pyqtSignal, QTimer, QPoint, QRect
from PyQt6.QtGui import QAction, QFont, QIcon, QColor, QPalette, QBrush, QRadialGradient
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLineEdit, QStatusBar, QTabWidget, QMenu, QTextEdit,
    QLabel, QSpinBox, QMessageBox, QComboBox, QRadioButton, QDialog,
    QSlider, QCheckBox, QFrame, QInputDialog, QFileDialog, QGroupBox,
    QScrollArea
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import (
    QWebEngineProfile,
    QWebEngineUrlRequestInterceptor,
    QWebEnginePage,
    QWebEngineScript
)
from PyQt6.QtNetwork import QNetworkProxy

# Отключаем прокси
QNetworkProxy.setApplicationProxy(QNetworkProxy(QNetworkProxy.ProxyType.NoProxy))

# Flask + зависимости
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from deep_translator import GoogleTranslator
from ddgs import DDGS

# ---------- resource_path ----------
def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# ---------- ПУТИ ----------
if getattr(sys, 'frozen', False):
    CURRENT_DIR = os.path.dirname(sys.executable)
else:
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------- ПАПКА ДАННЫХ В AppData ----------
def get_data_dir():
    if sys.platform == 'win32':
        appdata = os.environ.get('APPDATA', os.path.expanduser('~'))
        data_dir = os.path.join(appdata, 'FreeSearch')
    else:
        # Для Linux/macOS используем ~/.config/FreeSearch
        config_home = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
        data_dir = os.path.join(config_home, 'FreeSearch')
    os.makedirs(data_dir, exist_ok=True)
    return data_dir

DATA_DIR = get_data_dir()
# ---- ВСЕ ДАННЫЕ СОХРАНЯЮТСЯ В ПАПКУ "save" ----
SAVE_DIR = os.path.join(DATA_DIR, "save")
os.makedirs(SAVE_DIR, exist_ok=True)

# ---------- Файлы данных (внутри save) ----------
SETTINGS_FILE = os.path.join(SAVE_DIR, "settings.json")
PASSWORD_FILE = os.path.join(SAVE_DIR, "passwords.json")
BACKGROUNDS_FILE = os.path.join(SAVE_DIR, "backgrounds.json")
WIDGETS_FILE = os.path.join(SAVE_DIR, "widgets.json")
TABS_FILE = os.path.join(SAVE_DIR, "tabs.json")
PROFILE_DIR = os.path.join(SAVE_DIR, "profiles")
os.makedirs(PROFILE_DIR, exist_ok=True)

# ---------- Статические файлы (из папки с .exe или из исходников) ----------
STATIC_DIR = resource_path('.')
PORT = 5000
HOME_URL = f"http://127.0.0.1:{PORT}/index.html"
PROFILE_URL = f"http://127.0.0.1:{PORT}/profile.html"

# ---------- НАСТРОЙКИ ----------
DEFAULT_SETTINGS = {"theme": "dark", "language": "ru"}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)

# ---------- ADBLOCK ----------
ADBLOCK_LIST = []

def is_ad_url(url):
    if not url:
        return False
    url_lower = url.lower()
    return any(domain in url_lower for domain in ADBLOCK_LIST)

class AdBlockInterceptor(QWebEngineUrlRequestInterceptor):
    def interceptRequest(self, info):
        url = info.requestUrl().toString()
        if is_ad_url(url):
            info.block(True)

# ---------- FLASK ----------
app = Flask(__name__, static_folder=STATIC_DIR, template_folder=STATIC_DIR)
CORS(app)

# Профили (используем PROFILE_DIR внутри save)
@app.route('/api/profile/create', methods=['POST'])
def create_profile():
    user_id = ''.join(str(random.randint(0, 9)) for _ in range(16))
    profile = {
        "id": user_id,
        "nickname": f"User_{user_id[:4]}",
        "avatar": "",
        "created_at": datetime.now().isoformat(),
        "settings": {"language": "ru"}
    }
    with open(os.path.join(PROFILE_DIR, f"{user_id}.json"), 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True, "profile": profile})

@app.route('/api/profile/get', methods=['POST'])
def get_profile():
    data = request.get_json()
    user_id = data.get('id')
    if not user_id:
        return jsonify({"success": False, "error": "No id"}), 400
    filepath = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Profile not found"}), 404
    with open(filepath, 'r', encoding='utf-8') as f:
        profile = json.load(f)
    return jsonify({"success": True, "profile": profile})

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    data = request.get_json()
    user_id = data.get('id')
    updates = data.get('updates', {})
    if not user_id:
        return jsonify({"success": False, "error": "No id"}), 400
    filepath = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if not os.path.exists(filepath):
        return jsonify({"success": False, "error": "Profile not found"}), 404
    with open(filepath, 'r', encoding='utf-8') as f:
        profile = json.load(f)
    if 'nickname' in updates:
        profile['nickname'] = updates['nickname'][:30]
    if 'avatar' in updates:
        profile['avatar'] = updates['avatar']
    if 'settings' in updates and isinstance(updates['settings'], dict):
        profile['settings'].update(updates['settings'])
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True, "profile": profile})

@app.route('/api/profile/delete', methods=['POST'])
def delete_profile():
    data = request.get_json()
    user_id = data.get('id')
    if not user_id:
        return jsonify({"success": False, "error": "No id"}), 400
    filepath = os.path.join(PROFILE_DIR, f"{user_id}.json")
    if os.path.exists(filepath):
        os.remove(filepath)
    return jsonify({"success": True})

# Пароли
def load_passwords():
    if os.path.exists(PASSWORD_FILE):
        with open(PASSWORD_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_passwords(data):
    with open(PASSWORD_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/api/passwords/get', methods=['POST'])
def get_passwords():
    return jsonify(load_passwords())

@app.route('/api/passwords/save', methods=['POST'])
def save_password():
    data = request.get_json()
    domain = data.get('domain')
    username = data.get('username')
    password = data.get('password')
    if not domain or not username or not password:
        return jsonify({"success": False, "error": "Missing fields"}), 400
    store = load_passwords()
    if domain not in store:
        store[domain] = []
    for entry in store[domain]:
        if entry['username'] == username:
            entry['password'] = password
            break
    else:
        store[domain].append({"username": username, "password": password})
    save_passwords(store)
    return jsonify({"success": True})

@app.route('/api/passwords/delete', methods=['POST'])
def delete_password():
    data = request.get_json()
    domain = data.get('domain')
    username = data.get('username')
    if not domain or not username:
        return jsonify({"success": False, "error": "Missing fields"}), 400
    store = load_passwords()
    if domain in store:
        store[domain] = [e for e in store[domain] if e['username'] != username]
        if not store[domain]:
            del store[domain]
        save_passwords(store)
    return jsonify({"success": True})

# ---------- Фон и виджеты (API) ----------
def load_backgrounds():
    if os.path.exists(BACKGROUNDS_FILE):
        with open(BACKGROUNDS_FILE, 'r') as f:
            return json.load(f)
    return {"type": "color", "value": "#0a0f14"}

def save_backgrounds(data):
    with open(BACKGROUNDS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def load_widgets():
    if os.path.exists(WIDGETS_FILE):
        with open(WIDGETS_FILE, 'r') as f:
            return json.load(f)
    return [
        {"name": "Gmail", "url": "https://mail.google.com", "icon": "📧"},
        {"name": "YouTube", "url": "https://youtube.com", "icon": "🎬"},
        {"name": "ВК", "url": "https://vk.com", "icon": "💬"}
    ]

def save_widgets(data):
    with open(WIDGETS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

@app.route('/api/backgrounds/get', methods=['GET'])
def get_backgrounds():
    return jsonify(load_backgrounds())

@app.route('/api/backgrounds/set', methods=['POST'])
def set_backgrounds():
    data = request.get_json()
    if 'type' not in data or 'value' not in data:
        return jsonify({"error": "Invalid data"}), 400
    save_backgrounds({"type": data['type'], "value": data['value']})
    return jsonify({"success": True})

@app.route('/api/widgets/get', methods=['GET'])
def get_widgets():
    return jsonify(load_widgets())

@app.route('/api/widgets/set', methods=['POST'])
def set_widgets():
    widgets = request.get_json()
    if not isinstance(widgets, list):
        return jsonify({"error": "Invalid data"}), 400
    save_widgets(widgets)
    return jsonify({"success": True})

# ---------- НОВЫЕ API для настроек и вкладок ----------
@app.route('/api/settings/get', methods=['GET'])
def get_settings():
    return jsonify(load_settings())

@app.route('/api/settings/set', methods=['POST'])
def set_settings():
    data = request.get_json()
    settings = load_settings()
    if 'theme' in data:
        settings['theme'] = data['theme']
    if 'language' in data:
        settings['language'] = data['language']
    save_settings(settings)
    return jsonify({"success": True, "settings": settings})

@app.route('/api/tabs/get', methods=['GET'])
def get_tabs():
    if os.path.exists(TABS_FILE):
        with open(TABS_FILE, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify({"tabs": [], "current_index": 0})

@app.route('/api/tabs/save', methods=['POST'])
def save_tabs():
    data = request.get_json()
    with open(TABS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return jsonify({"success": True})

# ---------- ПОИСК ----------
def search_ddgs(query, max_results=14):
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
            formatted = []
            for r in results:
                formatted.append({
                    'title': r.get('title', ''),
                    'url': r.get('href', '#'),
                    'snippet': r.get('body', '')
                })
            return formatted
    except Exception as e:
        print(f"Ошибка DDGS: {e}")
        return []

CACHE = {}
CACHE_TTL = 300

def get_cached(query):
    if query in CACHE:
        data, timestamp = CACHE[query]
        if time.time() - timestamp < CACHE_TTL:
            return data
        else:
            del CACHE[query]
    return None

def set_cache(query, data):
    CACHE[query] = (data, time.time())

@app.route('/api/combined', methods=['POST'])
def combined():
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({'search_results': [], 'ai_answer': None})

    cached = get_cached(query)
    if cached is not None:
        if isinstance(cached, tuple) and len(cached) == 2:
            return jsonify({'search_results': cached[0], 'ai_answer': cached[1]})
        else:
            return jsonify({'search_results': cached, 'ai_answer': None})

    results = search_ddgs(query, max_results=14)

    if not results:
        lower = query.lower()
        keywords = ['кыргызстан', 'бишкек', 'манас', 'ош', 'иссык-куль', 'кыргыз']
        for word in keywords:
            if word in lower:
                results.append({
                    'title': '🇰🇬 Интересный факт о Кыргызстане',
                    'url': 'https://ru.wikipedia.org/wiki/Кыргызстан',
                    'snippet': 'Кыргызстан – страна гор, озёр и древних традиций.'
                })
                break

    ai_answer = None
    set_cache(query, (results, ai_answer))
    return jsonify({'search_results': results, 'ai_answer': ai_answer})

@app.route('/api/translate', methods=['POST'])
def translate_text():
    data = request.get_json()
    text = data.get('text', '')
    source = data.get('source', 'auto')
    target = data.get('target', 'ru')
    if not text:
        return jsonify({'translated': ''})
    try:
        translator = GoogleTranslator(source=source, target=target)
        translated = translator.translate(text)
        return jsonify({'translated': translated})
    except Exception as e:
        return jsonify({'translated': 'Ошибка перевода'}), 500

# ---------- СТАТИЧЕСКИЕ СТРАНИЦЫ ----------
@app.route('/')
@app.route('/index.html')
def index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/profile.html')
def profile():
    return send_from_directory(STATIC_DIR, 'profile.html')

# ---------- ЗАПУСК FLASK ----------
def run_flask():
    try:
        print(f"Запуск Flask на порту {PORT}...")
        app.run(host='127.0.0.1', port=PORT, debug=False, use_reloader=False)
    except Exception as e:
        print(f"Ошибка Flask: {e}")

flask_thread = threading.Thread(target=run_flask, daemon=True)

# ---------- МОНИТОР ----------
class MonitorWorker(QThread):
    update_signal = pyqtSignal(str, str)

    def __init__(self, url, interval_minutes, parent=None):
        super().__init__(parent)
        self.url = url
        self.interval = interval_minutes * 60
        self.running = True
        self.last_hash = None

    def run(self):
        while self.running:
            try:
                resp = requests.get(self.url, timeout=15)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for script in soup(["script", "style"]):
                        script.decompose()
                    text = soup.get_text(separator=' ', strip=True)
                    current_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
                    if self.last_hash is None:
                        self.last_hash = current_hash
                    elif self.last_hash != current_hash:
                        self.update_signal.emit(self.url, "Содержимое страницы изменилось!")
                        self.last_hash = current_hash
                else:
                    self.update_signal.emit(self.url, f"Ошибка доступа: {resp.status_code}")
            except Exception as e:
                self.update_signal.emit(self.url, f"Ошибка проверки: {str(e)}")
            for _ in range(self.interval):
                if not self.running:
                    break
                time.sleep(1)

    def stop(self):
        self.running = False

class MonitorManager:
    def __init__(self):
        self.monitors = {}

    def add_monitor(self, url, interval, callback):
        if url in self.monitors:
            return False, "Мониторинг для этого URL уже запущен"
        thread = MonitorWorker(url, interval)
        thread.update_signal.connect(callback)
        thread.start()
        self.monitors[url] = (thread, interval)
        return True, "Мониторинг запущен"

    def remove_monitor(self, url):
        if url in self.monitors:
            thread, _ = self.monitors[url]
            thread.stop()
            thread.wait()
            del self.monitors[url]
            return True, "Мониторинг остановлен"
        return False, "Мониторинг для этого URL не найден"

# ---------- ВИДЖЕТ ИНСТРУМЕНТОВ ----------
class ToolsWidget(QWidget):
    def __init__(self, parent=None, browser_window=None):
        super().__init__(parent)
        self.browser_window = browser_window
        self.monitor_manager = MonitorManager()
        self.current_monitor_url = None

        layout = QVBoxLayout(self)

        self.output_area = QTextEdit()
        self.output_area.setReadOnly(True)
        self.output_area.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.output_area)

        btn_layout = QHBoxLayout()
        self.btn_monitor = QPushButton("🔔 Следить")
        self.btn_monitor.clicked.connect(self.start_monitor)
        btn_layout.addWidget(self.btn_monitor)

        self.btn_stop_monitor = QPushButton("🚫 Остановить слежку")
        self.btn_stop_monitor.clicked.connect(self.stop_monitor)
        self.btn_stop_monitor.setEnabled(False)
        btn_layout.addWidget(self.btn_stop_monitor)

        layout.addLayout(btn_layout)

        self.append_message("📢", "Мониторинг страниц. Нажмите «Следить» для текущей вкладки.")

    def append_message(self, sender, msg):
        color = "#6effaa" if sender == "📢" else "#ffffff"
        self.output_area.append(f'<b style="color:{color}">{sender}</b>: {msg}')

    def start_monitor(self):
        if not self.browser_window:
            self.append_message("⚠️", "Нет активного окна браузера")
            return
        web_view = self.browser_window.get_current_web_view()
        if not web_view:
            return
        url = web_view.url().toString()
        if not url or url == "about:blank":
            self.append_message("⚠️", "Нет URL для мониторинга.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Настройка мониторинга")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Следить за:\n{url}"))
        hbox = QHBoxLayout()
        hbox.addWidget(QLabel("Интервал (минуты):"))
        spin = QSpinBox()
        spin.setRange(5, 1440)
        spin.setValue(60)
        hbox.addWidget(spin)
        layout.addLayout(hbox)
        btn_ok = QPushButton("Запустить")
        btn_ok.clicked.connect(dialog.accept)
        btn_cancel = QPushButton("Отмена")
        btn_cancel.clicked.connect(dialog.reject)
        hbox_btns = QHBoxLayout()
        hbox_btns.addWidget(btn_ok)
        hbox_btns.addWidget(btn_cancel)
        layout.addLayout(hbox_btns)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        interval = spin.value()

        def on_update(url, message):
            if self.browser_window:
                self.browser_window.statusBar().showMessage(f"🔔 {url} – {message}")
            self.append_message("🔔", f"{url} – {message}")

        success, msg = self.monitor_manager.add_monitor(url, interval, on_update)
        self.append_message("🔔", msg)
        if success:
            self.current_monitor_url = url
            self.btn_stop_monitor.setEnabled(True)

    def stop_monitor(self):
        if self.current_monitor_url:
            success, msg = self.monitor_manager.remove_monitor(self.current_monitor_url)
            self.append_message("🔔", msg)
            if success:
                self.current_monitor_url = None
                self.btn_stop_monitor.setEnabled(False)

# ---------- ВИДЖЕТ ПРОФИЛЯ (с расширенными настройками) ----------
class ProfileWidget(QWidget):
    def __init__(self, parent=None, browser_window=None):
        super().__init__(parent)
        self.browser_window = browser_window
        self.settings = load_settings()

        layout = QVBoxLayout(self)

        self.tabs = QTabWidget(self)
        self.tab_profile = QWidget()
        self.tab_tools = ToolsWidget(self, browser_window)
        self.tab_settings = QWidget()
        self.tabs.addTab(self.tab_profile, "Профиль")
        self.tabs.addTab(self.tab_tools, "Инструменты")
        self.tabs.addTab(self.tab_settings, "Настройки")

        # Вкладка профиля
        profile_layout = QVBoxLayout(self.tab_profile)
        self.profile_view = QWebEngineView()
        self.profile_view.setUrl(QUrl(PROFILE_URL))
        profile_layout.addWidget(self.profile_view)

        # ---------- Вкладка НАСТРОЙКИ ----------
        settings_layout = QVBoxLayout(self.tab_settings)
        settings_layout.setSpacing(15)

        # Тема и язык
        theme_group = QGroupBox("Оформление")
        theme_layout = QVBoxLayout(theme_group)
        theme_layout.addWidget(QLabel("Тема:"))
        self.theme_dark = QRadioButton("Тёмная")
        self.theme_light = QRadioButton("Светлая")
        self.theme_system = QRadioButton("Системная")
        if self.settings.get("theme") == "dark":
            self.theme_dark.setChecked(True)
        elif self.settings.get("theme") == "light":
            self.theme_light.setChecked(True)
        else:
            self.theme_system.setChecked(True)
        theme_layout.addWidget(self.theme_dark)
        theme_layout.addWidget(self.theme_light)
        theme_layout.addWidget(self.theme_system)
        settings_layout.addWidget(theme_group)

        lang_group = QGroupBox("Язык")
        lang_layout = QVBoxLayout(lang_group)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["Русский", "English", "Кыргызча"])
        lang_map = {"ru": "Русский", "en": "English", "ky": "Кыргызча"}
        current_lang = self.settings.get("language", "ru")
        self.lang_combo.setCurrentText(lang_map.get(current_lang, "Русский"))
        lang_layout.addWidget(self.lang_combo)
        settings_layout.addWidget(lang_group)

        # ---------- Настройка фона ----------
        bg_group = QGroupBox("Фон главной страницы")
        bg_layout = QVBoxLayout(bg_group)

        # Палитра цветов
        color_layout = QHBoxLayout()
        color_layout.addWidget(QLabel("Цвета:"))
        colors = ["#0a0f14", "#1a2a3a", "#2d3748", "#f0f4f8", "#6effaa", "#ff6b6b"]
        self.color_buttons = []
        for c in colors:
            btn = QPushButton()
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(f"background-color: {c}; border-radius: 20px; border: 2px solid transparent;")
            btn.clicked.connect(lambda checked, col=c: self.set_bg_color(col))
            color_layout.addWidget(btn)
            self.color_buttons.append(btn)
        color_layout.addStretch()
        bg_layout.addLayout(color_layout)

        # Загрузка изображения
        image_layout = QHBoxLayout()
        image_layout.addWidget(QLabel("Изображение:"))
        self.bg_file_btn = QPushButton("Выбрать файл...")
        self.bg_file_btn.clicked.connect(self.choose_bg_image)
        image_layout.addWidget(self.bg_file_btn)
        self.bg_clear_btn = QPushButton("Сбросить фон")
        self.bg_clear_btn.clicked.connect(self.clear_bg)
        image_layout.addWidget(self.bg_clear_btn)
        image_layout.addStretch()
        bg_layout.addLayout(image_layout)
        settings_layout.addWidget(bg_group)

        # ---------- Управление виджетами ----------
        widget_group = QGroupBox("Виджеты быстрого доступа")
        widget_layout = QVBoxLayout(widget_group)

        # Список виджетов (в виде текста)
        self.widget_list = QTextEdit()
        self.widget_list.setReadOnly(True)
        self.widget_list.setMaximumHeight(100)
        widget_layout.addWidget(QLabel("Текущие виджеты (имя, URL):"))
        widget_layout.addWidget(self.widget_list)

        # Кнопки управления
        btn_widget_layout = QHBoxLayout()
        self.add_widget_btn = QPushButton("➕ Добавить виджет")
        self.add_widget_btn.clicked.connect(self.add_widget_dialog)
        self.remove_widget_btn = QPushButton("✖ Удалить виджет (по номеру)")
        self.remove_widget_btn.clicked.connect(self.remove_widget_dialog)
        btn_widget_layout.addWidget(self.add_widget_btn)
        btn_widget_layout.addWidget(self.remove_widget_btn)
        widget_layout.addLayout(btn_widget_layout)
        settings_layout.addWidget(widget_group)

        # Кнопка сохранения всех настроек
        btn_save_settings = QPushButton("Сохранить все настройки")
        btn_save_settings.clicked.connect(self.save_all_settings)
        settings_layout.addWidget(btn_save_settings)

        settings_layout.addStretch()

        layout.addWidget(self.tabs)

        # Загружаем виджеты
        self.refresh_widget_list()

    # ---------- Методы для фона ----------
    def set_bg_color(self, color):
        self._set_bg('color', color)

    def choose_bg_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Выберите изображение", "", "Images (*.png *.jpg *.jpeg *.bmp *.gif)")
        if file_path:
            with open(file_path, 'rb') as f:
                data = base64.b64encode(f.read()).decode('utf-8')
                ext = file_path.split('.')[-1].lower()
                mime = f"image/{ext}" if ext in ['png','jpg','jpeg','bmp','gif'] else "image/png"
                data_url = f"data:{mime};base64,{data}"
            self._set_bg('image', data_url)

    def clear_bg(self):
        self._set_bg('color', '#0a0f14')

    def _set_bg(self, bg_type, value):
        try:
            requests.post('http://127.0.0.1:5000/api/backgrounds/set',
                          json={'type': bg_type, 'value': value})
            if self.browser_window:
                wv = self.browser_window.get_current_web_view()
                if wv:
                    wv.reload()
                    QMessageBox.information(self, "Успешно", "Фон обновлён. Страница перезагружена.")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить фон: {e}")

    # ---------- Методы для виджетов ----------
    def refresh_widget_list(self):
        try:
            resp = requests.get('http://127.0.0.1:5000/api/widgets/get')
            if resp.status_code == 200:
                widgets = resp.json()
                text = ""
                for i, w in enumerate(widgets):
                    text += f"{i+1}. {w.get('icon','🌐')} {w.get('name','')} – {w.get('url','')}\n"
                self.widget_list.setText(text)
            else:
                self.widget_list.setText("Ошибка загрузки виджетов")
        except Exception as e:
            self.widget_list.setText(f"Ошибка: {e}")

    def add_widget_dialog(self):
        name, ok1 = QInputDialog.getText(self, "Добавить виджет", "Название:")
        if not ok1 or not name:
            return
        url, ok2 = QInputDialog.getText(self, "Добавить виджет", "URL (с http://):")
        if not ok2 or not url:
            return
        icon, ok3 = QInputDialog.getText(self, "Добавить виджет", "Иконка (эмодзи):")
        if not ok3:
            icon = "🌐"

        try:
            resp = requests.get('http://127.0.0.1:5000/api/widgets/get')
            if resp.status_code != 200:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить виджеты")
                return
            widgets = resp.json()
            widgets.append({"name": name, "url": url, "icon": icon})
            resp2 = requests.post('http://127.0.0.1:5000/api/widgets/set', json=widgets)
            if resp2.status_code == 200:
                self.refresh_widget_list()
                if self.browser_window:
                    wv = self.browser_window.get_current_web_view()
                    if wv:
                        wv.reload()
                QMessageBox.information(self, "Успешно", "Виджет добавлен")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить виджет")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    def remove_widget_dialog(self):
        index_str, ok = QInputDialog.getText(self, "Удалить виджет", "Введите номер виджета для удаления:")
        if not ok or not index_str:
            return
        try:
            index = int(index_str) - 1
            if index < 0:
                raise ValueError
            resp = requests.get('http://127.0.0.1:5000/api/widgets/get')
            if resp.status_code != 200:
                QMessageBox.warning(self, "Ошибка", "Не удалось получить виджеты")
                return
            widgets = resp.json()
            if index >= len(widgets):
                QMessageBox.warning(self, "Ошибка", f"Номер должен быть от 1 до {len(widgets)}")
                return
            del widgets[index]
            resp2 = requests.post('http://127.0.0.1:5000/api/widgets/set', json=widgets)
            if resp2.status_code == 200:
                self.refresh_widget_list()
                if self.browser_window:
                    wv = self.browser_window.get_current_web_view()
                    if wv:
                        wv.reload()
                QMessageBox.information(self, "Успешно", "Виджет удалён")
            else:
                QMessageBox.warning(self, "Ошибка", "Не удалось сохранить изменения")
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Введите целое число")
        except Exception as e:
            QMessageBox.warning(self, "Ошибка", str(e))

    # ---------- Сохранение общих настроек ----------
    def save_all_settings(self):
        if self.theme_dark.isChecked():
            theme = "dark"
        elif self.theme_light.isChecked():
            theme = "light"
        else:
            theme = "system"
        lang_map = {"Русский": "ru", "English": "en", "Кыргызча": "ky"}
        lang = lang_map.get(self.lang_combo.currentText(), "ru")

        self.settings["theme"] = theme
        self.settings["language"] = lang
        save_settings(self.settings)

        if self.browser_window:
            self.browser_window.apply_theme(theme)
        QMessageBox.information(self, "Настройки", "Настройки сохранены и применены.")

# ---------- КЛАСС КИНОТЕАТРА (3D Cinema) ----------
class CinemaWindow(QWidget):
    def __init__(self, video_url, brightness=0.7, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎥 3D Кинотеатр")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(100, 100, 1200, 700)

        self.brightness = brightness
        self.ambient_enabled = True
        self.current_color = QColor(30, 30, 30)
        self.timer_interval = 150

        self.background_widget = QWidget(self)
        self.background_widget.setGeometry(0, 0, self.width(), self.height())
        self.background_widget.setStyleSheet("background-color: rgba(0,0,0,0.85);")

        self.web_view = QWebEngineView(self.background_widget)
        self.web_view.setGeometry(80, 50, self.width()-160, self.height()-120)

        settings = self.web_view.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)

        self.video_url = video_url
        self.web_view.setUrl(QUrl(video_url))

        self.control_panel = QWidget(self.background_widget)
        self.control_panel.setStyleSheet("background: rgba(0,0,0,0.4); border-radius: 15px;")
        self.control_panel.setGeometry(20, self.height()-70, self.width()-40, 50)

        self.close_btn = QPushButton("✕", self.control_panel)
        self.close_btn.setStyleSheet("background: #e74c3c; color: white; border: none; border-radius: 15px; font-size: 16px; padding: 6px 14px;")
        self.close_btn.clicked.connect(self.close)
        self.close_btn.setGeometry(10, 10, 40, 30)

        self.fullscreen_btn = QPushButton("⛶", self.control_panel)
        self.fullscreen_btn.setStyleSheet("background: #2ecc71; color: white; border: none; border-radius: 15px; font-size: 16px; padding: 6px 14px;")
        self.fullscreen_btn.clicked.connect(self.toggle_fullscreen)
        self.fullscreen_btn.setGeometry(60, 10, 40, 30)

        self.brightness_label = QLabel("💡", self.control_panel)
        self.brightness_label.setStyleSheet("color: white; font-size: 16px;")
        self.brightness_label.setGeometry(120, 12, 30, 30)

        self.brightness_slider = QSlider(Qt.Orientation.Horizontal, self.control_panel)
        self.brightness_slider.setRange(10, 100)
        self.brightness_slider.setValue(int(self.brightness * 100))
        self.brightness_slider.setStyleSheet("QSlider::groove:horizontal { height: 4px; background: #6effaa; } QSlider::handle:horizontal { width: 14px; height: 14px; background: #6effaa; border-radius: 7px; }")
        self.brightness_slider.setGeometry(160, 15, 120, 20)
        self.brightness_slider.valueChanged.connect(self.on_brightness_changed)

        self.ambient_check = QCheckBox("Ambient", self.control_panel)
        self.ambient_check.setStyleSheet("color: white; font-size: 12px;")
        self.ambient_check.setChecked(True)
        self.ambient_check.setGeometry(300, 10, 80, 30)
        self.ambient_check.stateChanged.connect(self.on_ambient_toggle)

        self.pip_btn = QPushButton("📺 PiP", self.control_panel)
        self.pip_btn.setStyleSheet("background: #3498db; color: white; border: none; border-radius: 15px; font-size: 14px; padding: 4px 12px;")
        self.pip_btn.clicked.connect(self.open_pip_mode)
        self.pip_btn.setGeometry(400, 10, 60, 30)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ambient_light)
        self.timer.start(self.timer_interval)

        self.is_fullscreen = False
        self.drag_pos = None

    def resizeEvent(self, event):
        w = self.width()
        h = self.height()
        self.background_widget.setGeometry(0, 0, w, h)
        self.web_view.setGeometry(80, 50, w-160, h-120)
        self.control_panel.setGeometry(20, h-70, w-40, 50)
        super().resizeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.drag_pos is not None:
            delta = event.globalPosition().toPoint() - self.drag_pos
            self.move(self.pos() + delta)
            self.drag_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.drag_pos = None

    def on_brightness_changed(self, value):
        self.brightness = value / 100.0

    def on_ambient_toggle(self, state):
        self.ambient_enabled = (state == Qt.CheckState.Checked)

    def toggle_fullscreen(self):
        if self.is_fullscreen:
            self.showNormal()
            self.is_fullscreen = False
            self.fullscreen_btn.setText("⛶")
        else:
            self.showFullScreen()
            self.is_fullscreen = True
            self.fullscreen_btn.setText("⛶")

    def open_pip_mode(self):
        if self.parent():
            if hasattr(self.parent(), 'open_pip_simple'):
                self.parent().open_pip_simple(self.video_url)
        self.close()

    def update_ambient_light(self):
        if not self.ambient_enabled:
            return
        js_code = """
        (function() {
            var video = document.querySelector('video');
            if (!video) return null;
            var canvas = document.createElement('canvas');
            canvas.width = 16;
            canvas.height = 16;
            var ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0, 16, 16);
            var imageData = ctx.getImageData(0, 0, 16, 16);
            var data = imageData.data;
            var r=0, g=0, b=0, count=0;
            for (var i=0; i<data.length; i+=4) {
                r += data[i];
                g += data[i+1];
                b += data[i+2];
                count++;
            }
            return [Math.floor(r/count), Math.floor(g/count), Math.floor(b/count)];
        })();
        """
        self.web_view.page().runJavaScript(js_code, self.on_color_received)

    def on_color_received(self, result):
        if result is None:
            return
        try:
            r, g, b = result
            r = int(r * self.brightness)
            g = int(g * self.brightness)
            b = int(b * self.brightness)
            color = QColor(r, g, b)
            self.current_color = color
            self.update_background_gradient(color)
        except Exception:
            pass

    def update_background_gradient(self, color):
        grad = QRadialGradient(self.width()/2, self.height()/2, max(self.width(), self.height())*0.8)
        grad.setColorAt(0, color)
        grad.setColorAt(0.6, color.darker(120))
        grad.setColorAt(1, QColor(0, 0, 0))

        palette = self.background_widget.palette()
        palette.setBrush(QPalette.ColorRole.Window, QBrush(grad))
        self.background_widget.setPalette(palette)
        self.background_widget.setAutoFillBackground(True)

    def closeEvent(self, event):
        self.timer.stop()
        super().closeEvent(event)

# ---------- ГЛАВНОЕ ОКНО БРАУЗЕРА ----------
class BrowserWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FreeSearch")
        icon_path = resource_path("freesearch.jpeg")
        self.setWindowIcon(QIcon(icon_path))

        self.setGeometry(100, 100, 1200, 800)

        font = QFont("Segoe UI", 9)
        QApplication.setFont(font)

        self.settings = load_settings()
        self.apply_theme(self.settings.get("theme", "dark"))

        self.create_ui()

        # Загружаем сохранённые вкладки
        self.load_tabs_state()

        QTimer.singleShot(2000, self.reload_current_tab)

        self.cinema_window = None

    def load_tabs_state(self):
        """Загружает список вкладок из tabs.json и восстанавливает их."""
        try:
            resp = requests.get('http://127.0.0.1:5000/api/tabs/get', timeout=1)
            if resp.status_code == 200:
                data = resp.json()
                tabs = data.get('tabs', [])
                current_index = data.get('current_index', 0)
                if tabs:
                    # Очищаем все текущие вкладки
                    while self.tab_widget.count() > 0:
                        self.tab_widget.removeTab(0)
                    # Создаём вкладки из сохранённых URL
                    for tab in tabs:
                        url = tab.get('url', HOME_URL)
                        self.add_new_tab(url)
                    # Устанавливаем сохранённую активную вкладку
                    if current_index < self.tab_widget.count():
                        self.tab_widget.setCurrentIndex(current_index)
                    else:
                        self.tab_widget.setCurrentIndex(0)
                    self.update_tabs_menu()
                    return
        except Exception as e:
            print(f"Ошибка загрузки вкладок: {e}")
        # Если не загрузились или пусто, создаём домашнюю вкладку
        if self.tab_widget.count() == 0:
            self.add_new_tab(HOME_URL)

    def save_tabs_state(self):
        """Сохраняет текущие вкладки (URL) и активную вкладку в tabs.json."""
        tabs_data = []
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QWebEngineView):
                url = widget.url().toString()
                tabs_data.append({"url": url})
            # Вкладки ProfileWidget не сохраняем (они не являются веб-страницами)
        current_index = self.tab_widget.currentIndex()
        try:
            requests.post('http://127.0.0.1:5000/api/tabs/save',
                          json={"tabs": tabs_data, "current_index": current_index},
                          timeout=1)
        except Exception as e:
            print(f"Ошибка сохранения вкладок: {e}")

    def reload_current_tab(self):
        wv = self.get_current_web_view()
        if wv:
            wv.reload()
            self.statusBar().showMessage("Страница перезагружена")

    def apply_theme(self, theme):
        if theme == "light":
            bg = "#f0f4f8"
            text = "#1a202c"
            accent = "#2b6cb0"
            input_bg = "#ffffff"
            input_border = "#a0aec0"
        elif theme == "dark":
            bg = "#0a0f14"
            text = "#eef2ff"
            accent = "#6effaa"
            input_bg = "#1e2936"
            input_border = "#6effaa"
        else:
            bg = "#0a0f14"
            text = "#eef2ff"
            accent = "#6effaa"
            input_bg = "#1e2936"
            input_border = "#6effaa"

        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {bg}; }}
            QWidget {{ background-color: {bg}; color: {text}; font-family: 'Segoe UI'; font-size: 9pt; }}
            QPushButton {{
                background: transparent; border: none; color: {accent};
                font-size: 16px; padding: 8px 14px; border-radius: 20px; font-weight: 600;
            }}
            QPushButton:hover {{ background: rgba(110, 255, 170, 0.15); color: #aaffcc; }}
            QLineEdit {{
                background: {input_bg}; border: 1px solid {input_border};
                border-radius: 30px; padding: 8px 20px; color: {text}; font-size: 14px;
                selection-background-color: {accent};
            }}
            QLineEdit:focus {{ border: 1px solid {accent}; background: {input_bg}; }}
            QTabWidget::pane {{ border: none; background: {bg}; }}
            QMenu {{ background-color: {input_bg}; color: {text}; border: 1px solid {accent}; border-radius: 12px; }}
            QMenu::item {{ padding: 8px 20px; border-radius: 8px; }}
            QMenu::item:selected {{ background: rgba(110, 255, 170, 0.2); }}
            QStatusBar {{ background-color: {bg}; color: {text}; border-top: 1px solid {accent}; padding: 5px; }}
            QWidget#navBar {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                            stop:0 #0f1724, stop:1 #1a2a3a);
                border-bottom: 2px solid {accent};
            }}
        """)

    def create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        nav_bar = QWidget()
        nav_bar.setObjectName("navBar")
        nav_bar.setFixedHeight(60)
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(15, 10, 15, 10)
        nav_layout.setSpacing(8)

        self.btn_back = QPushButton("⬅️")
        self.btn_back.setToolTip("Назад")
        self.btn_back.clicked.connect(self.go_back)

        self.btn_forward = QPushButton("➡️")
        self.btn_forward.setToolTip("Вперёд")
        self.btn_forward.clicked.connect(self.go_forward)

        self.btn_home = QPushButton("🏠 Домой")
        self.btn_home.clicked.connect(self.go_home)

        self.btn_profile = QPushButton("👤 Профиль")
        self.btn_profile.setToolTip("Открыть профиль и инструменты")
        self.btn_profile.clicked.connect(self.open_profile_tab)

        self.btn_tabs = QPushButton("📑 Вкладки")
        self.btn_tabs.setToolTip("Управление вкладками")
        self.tabs_menu = QMenu(self)
        self.btn_tabs.setMenu(self.tabs_menu)
        self.btn_tabs.clicked.connect(self.show_tabs_menu)

        self.btn_new_tab = QPushButton("➕")
        self.btn_new_tab.setToolTip("Новая вкладка")
        self.btn_new_tab.clicked.connect(lambda: self.add_new_tab(HOME_URL))

        self.btn_cinema = QPushButton("🎬 3D Кино")
        self.btn_cinema.setToolTip("Открыть текущее видео в 3D-кинотеатре")
        self.btn_cinema.clicked.connect(self.open_cinema)

        self.url_bar = QLineEdit()
        self.url_bar.setPlaceholderText("🔍 Введите URL или поисковый запрос")
        self.url_bar.returnPressed.connect(self.navigate_to_url)

        nav_layout.addWidget(self.btn_back)
        nav_layout.addWidget(self.btn_forward)
        nav_layout.addWidget(self.btn_home)
        nav_layout.addWidget(self.btn_profile)
        nav_layout.addWidget(self.btn_tabs)
        nav_layout.addWidget(self.btn_new_tab)
        nav_layout.addWidget(self.btn_cinema)
        nav_layout.addWidget(self.url_bar, 1)

        self.tab_widget = QTabWidget()
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabBar().setVisible(False)
        self.tab_widget.currentChanged.connect(self.on_tab_changed)

        main_layout.addWidget(nav_bar)
        main_layout.addWidget(self.tab_widget, 1)

        self.statusBar().showMessage("🚀 Загрузка...")
        self.statusBar().setStyleSheet("border-top: 1px solid rgba(110, 255, 170, 0.2); padding: 5px;")

        # ---------- ПРОФИЛЬ И СКРИПТ БЛОКИРОВКИ РЕКЛАМЫ RUTUBE ----------
        self.profile = QWebEngineProfile.defaultProfile()
        self.profile.setUrlRequestInterceptor(AdBlockInterceptor())

        # Добавляем скрипт для борьбы с рекламой на Rutube
        self.add_rutube_adblock_script()

        self.add_new_tab(HOME_URL)
        self.update_tabs_menu()
        self.update_status("Готово")

    def add_rutube_adblock_script(self):
        adblock_js = """
        (function() {
            function removeRutubeAds() {
                if (window.playerConfiguration && window.playerConfiguration.advertising) {
                    window.playerConfiguration.advertising = null;
                }
                const ads = document.querySelectorAll('[class*="prmcdn"], [id*="prmcdn"], .video-player-ad-layer');
                ads.forEach(el => el.remove());
            }
            removeRutubeAds();
            setInterval(removeRutubeAds, 500);
        })();
        """
        script = QWebEngineScript()
        script.setSourceCode(adblock_js)
        script.setName("RutubeAdBlocker")
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
        script.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
        script.setRunsOnSubFrames(True)
        self.profile.scripts().insert(script)
        print("✅ Скрипт блокировки рекламы Rutube добавлен в профиль")

    def open_cinema(self):
        wv = self.get_current_web_view()
        if not wv:
            return
        url = wv.url().toString()
        if 'youtube' in url or 'youtu.be' in url or 'rutube' in url or 'vk.com/video' in url:
            video_url = url
        else:
            js = """
            (function() {
                var video = document.querySelector('video');
                if (video && video.src) {
                    return video.src;
                }
                var iframe = document.querySelector('iframe[src*="youtube"]') || document.querySelector('iframe[src*="rutube"]') || document.querySelector('iframe[src*="vk.com/video"]');
                if (iframe) {
                    return iframe.src;
                }
                return null;
            })();
            """
            wv.page().runJavaScript(js, self.on_video_url_extracted)
            return
        self.open_cinema_window(video_url)

    def on_video_url_extracted(self, result):
        if result:
            self.open_cinema_window(result)
        else:
            text, ok = QInputDialog.getText(self, "3D Кинотеатр", "Введите URL видео (YouTube, Rutube, VK):")
            if ok and text:
                self.open_cinema_window(text)

    def open_cinema_window(self, video_url):
        if self.cinema_window is not None:
            self.cinema_window.close()
            self.cinema_window = None
        self.cinema_window = CinemaWindow(video_url, brightness=0.7, parent=self)
        self.cinema_window.show()

    def open_profile_tab(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, ProfileWidget):
                self.tab_widget.setCurrentIndex(i)
                return
        profile_widget = ProfileWidget(self, self)
        index = self.tab_widget.addTab(profile_widget, "👤 Профиль")
        self.tab_widget.setCurrentIndex(index)

    def add_new_tab(self, url=None):
        web_view = QWebEngineView()
        web_view.setUrl(QUrl(url or HOME_URL))
        web_view.urlChanged.connect(lambda qurl, wv=web_view: self.on_url_changed(wv, qurl))
        web_view.loadFinished.connect(lambda ok, wv=web_view: self.on_load_finished(wv))

        settings = web_view.settings()
        settings.setAttribute(settings.WebAttribute.JavascriptEnabled, True)
        settings.setAttribute(settings.WebAttribute.AutoLoadImages, True)
        settings.setAttribute(settings.WebAttribute.ErrorPageEnabled, False)
        settings.setAttribute(settings.WebAttribute.PluginsEnabled, False)
        settings.setAttribute(settings.WebAttribute.LocalStorageEnabled, True)

        index = self.tab_widget.addTab(web_view, "Новая вкладка")
        self.tab_widget.setCurrentIndex(index)
        self.update_tabs_menu()
        self.save_tabs_state()
        return web_view

    def close_current_tab(self):
        if self.tab_widget.count() <= 1:
            self.add_new_tab(HOME_URL)
        else:
            current = self.tab_widget.currentIndex()
            self.tab_widget.removeTab(current)
            self.update_tabs_menu()
            self.save_tabs_state()

    def switch_to_tab(self, index):
        if 0 <= index < self.tab_widget.count():
            self.tab_widget.setCurrentIndex(index)
            self.update_tabs_menu()

    def get_current_web_view(self):
        widget = self.tab_widget.currentWidget()
        if isinstance(widget, QWebEngineView):
            return widget
        return None

    def on_tab_changed(self, index):
        if index >= 0:
            widget = self.tab_widget.widget(index)
            if isinstance(widget, QWebEngineView):
                self.url_bar.setText(widget.url().toString())
                self.update_nav_buttons(widget)
            self.save_tabs_state()

    def on_url_changed(self, web_view, qurl):
        if web_view == self.get_current_web_view():
            self.url_bar.setText(qurl.toString())
            title = web_view.page().title() or "Новая вкладка"
            index = self.tab_widget.indexOf(web_view)
            if index >= 0:
                self.tab_widget.setTabText(index, title)
                self.update_tabs_menu()

    def on_load_finished(self, web_view):
        if web_view == self.get_current_web_view():
            self.update_nav_buttons(web_view)
        title = web_view.page().title() or "Новая вкладка"
        index = self.tab_widget.indexOf(web_view)
        if index >= 0:
            self.tab_widget.setTabText(index, title)
            self.update_tabs_menu()

    def go_back(self):
        wv = self.get_current_web_view()
        if wv and wv.history().canGoBack():
            wv.back()
        else:
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, QWebEngineView) and widget.history().canGoBack():
                    self.tab_widget.setCurrentIndex(i)
                    widget.back()
                    return

    def go_forward(self):
        wv = self.get_current_web_view()
        if wv and wv.history().canGoForward():
            wv.forward()
        else:
            for i in range(self.tab_widget.count()):
                widget = self.tab_widget.widget(i)
                if isinstance(widget, QWebEngineView) and widget.history().canGoForward():
                    self.tab_widget.setCurrentIndex(i)
                    widget.forward()
                    return

    def go_home(self):
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QWebEngineView):
                self.tab_widget.setCurrentIndex(i)
                widget.setUrl(QUrl(HOME_URL))
                return
        self.add_new_tab(HOME_URL)

    def load_url(self, url):
        wv = self.get_current_web_view()
        if wv:
            wv.setUrl(QUrl(url))
        else:
            self.add_new_tab(url)

    def navigate_to_url(self):
        text = self.url_bar.text().strip()
        if not text:
            return
        if not text.startswith(("http://", "https://")):
            if "." in text and " " not in text:
                text = "https://" + text
            else:
                search_url = f"https://duckduckgo.com/?q={text.replace(' ', '+')}"
                self.load_url(search_url)
                return
        self.load_url(text)

    def update_nav_buttons(self, web_view):
        if web_view:
            self.btn_back.setEnabled(web_view.history().canGoBack())
            self.btn_forward.setEnabled(web_view.history().canGoForward())

    def update_tabs_menu(self):
        self.tabs_menu.clear()
        for i in range(self.tab_widget.count()):
            widget = self.tab_widget.widget(i)
            if isinstance(widget, QWebEngineView):
                title = widget.page().title() or f"Вкладка {i+1}"
            elif isinstance(widget, ProfileWidget):
                title = "👤 Профиль"
            else:
                title = "Вкладка"
            if len(title) > 40:
                title = title[:40] + "..."
            action = QAction(title, self)
            action.setData(i)
            action.triggered.connect(lambda checked, idx=i: self.switch_to_tab(idx))
            self.tabs_menu.addAction(action)

        self.tabs_menu.addSeparator()
        new_tab_action = QAction("➕ Новая вкладка", self)
        new_tab_action.triggered.connect(lambda: self.add_new_tab(HOME_URL))
        self.tabs_menu.addAction(new_tab_action)

        close_tab_action = QAction("❌ Закрыть вкладку", self)
        close_tab_action.triggered.connect(self.close_current_tab)
        self.tabs_menu.addAction(close_tab_action)

    def show_tabs_menu(self):
        pass

    def update_status(self, msg):
        self.statusBar().showMessage(msg)

    def closeEvent(self, event):
        self.save_tabs_state()
        super().closeEvent(event)

# ---------- ЗАПУСК ----------
if __name__ == '__main__':
    flask_thread.start()
    for _ in range(30):
        try:
            requests.get(f'http://127.0.0.1:{PORT}', timeout=1)
            print(f"✅ Flask запущен на порту {PORT}")
            break
        except:
            time.sleep(1)
    else:
        print(f"⚠️ Flask не запустился на порту {PORT}")

    app_qt = QApplication(sys.argv)
    window = BrowserWindow()
    window.show()
    sys.exit(app_qt.exec())