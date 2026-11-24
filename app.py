import os
import time
import re
import shutil
import pysubs2
import requests
import telebot
from telebot.types import BotCommand
from flask import Flask
from threading import Thread

# ==================== WEB SERVER (For Hosting 24/7) ====================
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Elite Anime/Donghua Series-Aware Translation Bot (Gemini 4 Hydrogen) is running!"

def run_Index():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))

Thread(target=run_Index, daemon=True).start()

# ==================== ENVIRONMENT VARIABLES ====================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()

# ==================== UNLOCKED FULL-POWER GEMINI 4 HYDROGEN ENGINE ====================
PRIMARY_MODELS = [
    "gemini-4-hydrogen",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-pro-latest",
    "gemini-2.5-flash-lite"
]

NON_TEXT_KEYWORDS = [
    "transcribe", "argon", "carbon", "vision", "embedding", "imagen",
    "tts", "audio", "veo", "aqa", "live", "robotics", "computer",
    "learnlm", "gemma", "medlm", "whisper", "native", "image", "video"
]

CACHED_MODELS = []
LAST_FETCH_TS = 0
DEAD_MODELS = set()
NO_CIVIC_MODELS = set()
NO_SYS_INST_MODELS = set()

SYSTEM_INSTRUCTION_TEXT = (
    "You are an Elite Myanmar Anime & Donghua Fansub Translator.\n"
    "Translate English/Romaji subtitle lines into crisp, punchy, everyday spoken Myanmar (Burmese) just like a top-tier human anime fansub.\n"
    "CORE PRINCIPLES:\n"
    "1. ZERO NOVEL / FAIRYTALE / LITERARY STYLE: This is an ANIME subtitle, NOT a novel or storybook. NEVER use bookish/literary phrasing (e.g., NO တည်ရှိ, ရောက်ရှိ, ကျန်ရစ်, လာရောက်, များသောအားဖြင့်, ...ဟာ, ...ခဲ့ပါတယ်, ...ပါပြီ in narration). Even for narration/monologues, use direct, casual spoken Burmese (e.g., ရှိတယ်, ရောက်လာတယ်, ကျန်ခဲ့တယ်, လာတောင်းကြတယ်).\n"
    "2. STRICT BAN ON FORCED FILLERS: NEVER add unnecessary particles like ပေါ့, တာပေါ့, ရှင်, ဗျာ, ခင်ဗျာ, ပါ့ when not strictly required by the original dialogue.\n"
    "3. CONTEXT-FIRST ADAPTATION: Never translate word-for-word like Google Translate; adapt phrasing naturally to fit the series and genre.\n"
    "4. PRONOUN SAFETY: Never mismatch gender pronouns. When speaker/listener gender or relationship is unclear, use neutral phrasing or omit pronouns without losing meaning.\n"
    "5. MEANING OVER SOUND & COMPLETE TRANSLATION: Keep ONLY personal character names and place names in English. Translate 100% of all other words into natural Burmese meaning (never phonetic transliteration, never leave partial English).\n"
    "6. NO PUNCTUATION SYMBOLS: Never include '?', ';', or '!' in the output; convey questions and attitude through natural spoken Burmese endings.\n"
    "7. FLAWLESS ORTHOGRAPHY: 100% accurate standard Myanmar spelling with zero typos."
)

def is_valid_text_model(name):
    if not name or name in DEAD_MODELS:
        return False
    low = name.lower()
    if "gemini" not in low:
        return False
    if any(k in low for k in NON_TEXT_KEYWORDS):
        return False
    return True

def get_available_models():
    global CACHED_MODELS, LAST_FETCH_TS
    if CACHED_MODELS and (time.time() - LAST_FETCH_TS) < 1800:
        return [m for m in CACHED_MODELS if m not in DEAD_MODELS]
    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models?key=" + GEMINI_API_KEY
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            valid = []
            for m in data.get("models", []):
                methods = m.get("supportedGenerationMethods", [])
                if "generateContent" in methods:
                    name = m.get("name", "").replace("models/", "")
                    if is_valid_text_model(name):
                        valid.append(name)
            hydrogen_models = [x for x in valid if "hydrogen" in x]
            flash_models = [x for x in valid if "flash" in x and "lite" not in x and x not in hydrogen_models]
            pro_models = [x for x in valid if "pro" in x and x not in hydrogen_models]
            other_models = [x for x in valid if x not in hydrogen_models and x not in flash_models and x not in pro_models]
            CACHED_MODELS = hydrogen_models + flash_models + pro_models + other_models
            LAST_FETCH_TS = time.time()
            return CACHED_MODELS
    except Exception:
        pass
    return []

def _single_model_request(model_name, prompt_text, timeout_sec, temp):
    url = "https://generativelanguage.googleapis.com/v1beta/models/" + model_name + ":generateContent"
    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY
    }
    safety_list = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    if model_name not in NO_CIVIC_MODELS:
        safety_list.append({"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"})

    payload = {
        "contents": [{"parts": [{"text": prompt_text}]}],
        "safetySettings": safety_list
    }

    if not model_name.lower().startswith("gemini-4"):
        payload["generationConfig"] = {
            "temperature": temp,
            "topP": 0.9,
            "topK": 40
        }

    if model_name not in NO_SYS_INST_MODELS:
        payload["systemInstruction"] = {"parts": [{"text": SYSTEM_INSTRUCTION_TEXT}]}

    resp = requests.post(url, headers=headers, json=payload, timeout=(10, timeout_sec))

    if resp.status_code == 400:
        err_txt = resp.text.lower()
        if "systeminstruction" in err_txt and model_name not in NO_SYS_INST_MODELS:
            NO_SYS_INST_MODELS.add(model_name)
            return _single_model_request(model_name, prompt_text, timeout_sec, temp)
        if model_name not in NO_CIVIC_MODELS:
            NO_CIVIC_MODELS.add(model_name)
            return _single_model_request(model_name, prompt_text, timeout_sec, temp)
    return resp

def _extract_text_from_response(data):
    candidates = data.get("candidates", [])
    if not candidates:
        return ""
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    out_parts = []
    for p in parts:
        if not p.get("thought", False) and "text" in p and p["text"]:
            out_parts.append(p["text"])
    if not out_parts:
        for p in parts:
            if "text" in p and p["text"]:
                out_parts.append(p["text"])
    return "\n".join(out_parts).strip()

def call_gemini_reliable(prompt_text, uid=None, timeout_sec=75, temp=0.2):
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY မရှိပါ။ Environment Variables တွင် ထည့်သွင်းပေးပါ။")

    dynamic_models = get_available_models()

    models_to_try = []
    for m in PRIMARY_MODELS:
        if m not in models_to_try and m not in DEAD_MODELS:
            models_to_try.append(m)
    for m in dynamic_models:
        if m not in models_to_try and m not in DEAD_MODELS:
            models_to_try.append(m)

    if not models_to_try:
        DEAD_MODELS.clear()
        models_to_try = list(PRIMARY_MODELS)

    errors = []

    for cycle in range(3):
        for model_name in list(models_to_try):
            if uid and cancel_flags.get(uid):
                raise ValueError("Cancelled by user")
            if not model_name or model_name in DEAD_MODELS:
                continue

            try:
                cur_temp = min(0.35, temp + (cycle * 0.05))
                resp = _single_model_request(model_name, prompt_text, timeout_sec, cur_temp)

                if resp.status_code == 200:
                    data = resp.json()
                    text_out = _extract_text_from_response(data)
                    if text_out:
                        return text_out
                    errors.append("[" + model_name + ": Empty]")
                    continue

                elif resp.status_code == 429:
                    err_body = resp.text.lower()
                    if "limit: 0" in err_body or "quota_limit_value\":\"0\"" in err_body:
                        DEAD_MODELS.add(model_name)
                        continue
                    errors.append("[" + model_name + ": 429]")
                    time.sleep(2.0)
                    continue

                elif resp.status_code in (500, 502, 503, 504):
                    errors.append("[" + model_name + ": " + str(resp.status_code) + "]")
                    time.sleep(1.5)
                    continue

                elif resp.status_code in (404, 403):
                    DEAD_MODELS.add(model_name)
                    continue

                else:
                    errors.append("[" + model_name + ": " + str(resp.status_code) + "]")
                    continue

            except requests.Timeout:
                errors.append("[" + model_name + ": Timeout]")
                continue
            except Exception as e:
                if "Cancelled by user" in str(e):
                    raise
                errors.append("[" + model_name + ": Err]")
                time.sleep(1.0)
                continue

        time.sleep(3.0)

    raise RuntimeError(" | ".join(errors[-4:]) if errors else "Gemini API busy.")

# ==================== BOT & STORAGE INIT ====================
bot = telebot.TeleBot(BOT_TOKEN, threaded=True)

cancel_flags = {}
user_settings = {
    "target_chat": None,
    "series_title": "",
    "series_genre": "",
    "series_bible": "",
    "cast_info": "",
    "series_glossary": ""
}
user_states = {}

TARGET_CHAT_FILE = "target_chat.txt"
SERIES_TITLE_FILE = "series_title.txt"
SERIES_GENRE_FILE = "series_genre.txt"
SERIES_BIBLE_FILE = "series_bible.txt"
CAST_INFO_FILE = "cast_info.txt"
SERIES_GLOSSARY_FILE = "series_glossary.txt"

def is_owner(message):
    return bool(message.from_user and message.from_user.id == OWNER_ID)

def load_text_file(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

def save_text_file(filepath, content):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass

t_chat = load_text_file(TARGET_CHAT_FILE)
if t_chat.lstrip("-").isdigit():
    user_settings["target_chat"] = int(t_chat)

user_settings["series_title"] = load_text_file(SERIES_TITLE_FILE)
user_settings["series_genre"] = load_text_file(SERIES_GENRE_FILE)
user_settings["series_bible"] = load_text_file(SERIES_BIBLE_FILE)
user_settings["cast_info"] = load_text_file(CAST_INFO_FILE)
user_settings["series_glossary"] = load_text_file(SERIES_GLOSSARY_FILE)

def save_target_chat(chat_id):
    user_settings["target_chat"] = chat_id
    save_text_file(TARGET_CHAT_FILE, str(chat_id))

def guess_anime_title_from_filename(filename):
    base = os.path.splitext(filename)[0]
    base = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", base)
    base = re.sub(r"(?i)\b(?:ep|episode|s\d+e\d+|s\d+|bd|web|bluray|1080p|720p|480p|x264|x265|hevc|aac|flac|dual|audio|sub|raw|v\d+|cr|webrip|multisub)\b", " ", base)
    base = re.sub(r"\b[0-9A-Fa-f]{8}\b", " ", base)
    base = re.sub(r"\b\d{1,3}\b", " ", base)
    base = re.sub(r"[_\-\.\s]+", " ", base).strip()
    return base

def generate_series_translation_bible(title, genre, uid=None):
    genre_str = genre if genre else "Auto-Detect from Series Title"
    prompt = (
        "Target Series Title: " + str(title) + "\n"
        "Target Genre: " + str(genre_str) + "\n\n"
        "Create a concise, high-accuracy 'Series Localization Guide' for translating '" + str(title) + "' into crisp, natural spoken Myanmar (Burmese) anime fansub style:\n"
        "1. Character Names & Pronouns: List the main characters, their genders/personalities, and appropriate Burmese pronoun pairs. When gender or relationship is unclear, default to neutral phrasing or omit pronouns. Keep character and place names in English.\n"
        "2. Series Terminology (Natural Burmese Meaning — NO Phonetic Transliteration): Provide natural Burmese translations for 10-12 key powers, titles, roles, or lore terms in this series.\n"
        "3. Genre Tone & Flow: Describe how dialogue and narration should sound for this exact genre so it feels like a top-tier human fansub (never like a novel or fairytale, no forced filler particles)."
    )
    try:
        return call_gemini_reliable(prompt, uid=uid, timeout_sec=60, temp=0.2)
    except Exception:
        return "Series: " + str(title) + " | Genre: " + str(genre_str)

# ==================== FORMATTING & PROGRESS HELPERS ====================
def format_bytes(size_bytes):
    if size_bytes <= 0:
        return "0 B"
    mb = size_bytes / (1024 * 1024)
    if mb >= 1024:
        return f"{mb / 1024:.2f} GB"
    return f"{mb:.2f} MB"

def safe_edit(chat_id, msg_id, text):
    try:
        bot.edit_message_text(text, chat_id, msg_id)
    except Exception:
        pass

@bot.my_chat_member_handler()
def auto_set_target(update):
    try:
        if update.new_chat_member and update.new_chat_member.status == "administrator":
            save_target_chat(update.chat.id)
    except Exception:
        pass

@bot.message_handler(commands=["setchat"], func=is_owner)
def cmd_setchat(message):
    save_target_chat(message.chat.id)
    bot.reply_to(message, "✅ ဤ Group/Chat ကို ဖိုင်များ ပို့မည့်နေရာအဖြစ် သတ်မှတ်လိုက်ပါပြီ။")

@bot.message_handler(commands=["cancel"], func=is_owner)
def cancel_process(message):
    uid = message.from_user.id
    cancel_flags[uid] = True
    user_states[uid] = None
    bot.reply_to(message, "🛑 လုပ်ဆောင်နေသော ဘာသာပြန်လုပ်ငန်းစဉ်ကို ရပ်တန့်လိုက်ပါပြီ။")

# ==================== MENUS & COMMANDS ====================
@bot.message_handler(commands=["start"], func=is_owner)
def cmd_start(message):
    try:
        bot.set_my_commands([
            BotCommand("start", "Bot စတင်ရန်နှင့် အချက်အလက်ကြည့်ရန်"),
            BotCommand("setseries", "ဇာတ်ကားနာမည်နှင့် အမျိုးအစား (Genre) သတ်မှတ်ရန်"),
            BotCommand("clearseries", "သတ်မှတ်ထားသော ဇာတ်ကားအချက်အလက် ဖျက်ရန်"),
            BotCommand("translate", "Subtitle (.ass / .srt) အကောင်းဆုံးဘာသာပြန်ရန်"),
            BotCommand("setcast", "ဇာတ်ကောင်စရိုက်နှင့် နာမ်စား ထပ်ဖြည့်ရန်"),
            BotCommand("clearcast", "ဇာတ်ကောင်စာရင်း ဖျက်ရန်"),
            BotCommand("glossary", "လက်ရှိ ဇာတ်ကား Lore မှတ်တမ်း ကြည့်ရန်"),
            BotCommand("setchat", "ဖိုင်ပို့မည့် Group သတ်မှတ်ရန်"),
            BotCommand("cancel", "လုပ်ဆောင်နေသော လုပ်ငန်းစဉ် ရပ်တန့်ရန်")
        ])
    except Exception:
        pass

    s_title = user_settings.get("series_title") or "Auto-Detect (ဖိုင်နာမည်မှ အလိုအလျောက်ရှာမည်)"
    s_genre = user_settings.get("series_genre") or "Auto"
    msg_text = (
        "👋 မင်္ဂလာပါ! Elite Pro Fansub Subtitle Bot (Gemini 4 Hydrogen) အဆင်သင့်ဖြစ်ပါပြီ။\n\n"
        "🔥 အထူးအဆင့်မြှင့်တင်ထားသော စနစ်များ:\n"
        "၁။ Gemini 4 Hydrogen Engine: နောက်ဆုံးပေါ် gemini-4-hydrogen ဖြင့် ဝတ္တုမဆန်ဘဲ Anime Fansub စစ်စစ်လို သဘာဝကျကျ ဘာသာပြန်ပေးပါမည်။\n"
        "၂။ Smart Pronoun & Clean Tone: နာမ်စားအမှားမဖြစ်အောင် ထိန်းပေးပြီး မလိုအပ်တဲ့ အဆက်စကားလုံးတွေ အတင်းမထည့်ပါ။\n"
        "၃။ 100% Pure Burmese & Clean Spelling: အသံထွက်အတိုင်းပြန်ခြင်း၊ စာလုံးကျန်ခြင်း၊ သင်္ကေတများနှင့် သတ်ပုံအမှားများကို အပြည့်အဝ စစ်ဆေးပေးပါမည်။\n\n"
        "🎬 လက်ရှိ ဇာတ်ကား: " + str(s_title) + "\n"
        "🎭 အမျိုးအစား (Genre): " + str(s_genre) + "\n\n"
        "💡 ဇာတ်ကားသတ်မှတ်ရန် /setseries ဇာတ်ကားနာမည် | အမျိုးအစား ဟု ရိုက်ထည့်ပါ။"
    )
    bot.reply_to(message, msg_text)

@bot.message_handler(commands=["setseries"], func=is_owner)
def cmd_setseries(message):
    uid = message.from_user.id
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        user_states[uid] = "setseries"
        return bot.reply_to(
            message,
            "🎬 ဘာသာပြန်မည့် ဇာတ်ကားနာမည် နှင့် အမျိုးအစား (Genre) ကို ပို့ပေးပါ။\n\n"
            "နမူနာ ပုံစံများ -\n"
            "• Black Clover | Fantasy, Action, Magic\n"
            "• Grand Blue | Ecchi, Gag Comedy, College\n"
            "• Battle Through the Heavens | Donghua, Xianxia, Action\n"
            "• Dandadan | Supernatural, Action, Rom-Com"
        )
    Thread(target=process_setseries_input, args=(message, uid, parts[1].strip()), daemon=True).start()

def process_setseries_input(message, uid, raw_input):
    if "|" in raw_input:
        s_title, s_genre = [x.strip() for x in raw_input.split("|", 1)]
    elif "-" in raw_input and len(raw_input.split("-", 1)[1].strip()) > 3:
        s_title, s_genre = [x.strip() for x in raw_input.split("-", 1)]
    else:
        s_title, s_genre = raw_input.strip(), "Auto-Detect"

    status_msg = bot.reply_to(
        message,
        "🔍 " + s_title + " (" + s_genre + ") ဇာတ်ကား၏ ဇာတ်လမ်းတည်ဆောက်ပုံ၊ ဝေါဟာရများနှင့် ဇာတ်ကောင်စကားပြောဟန်ကို Gemini 4 Hydrogen ဖြင့် စိစစ်ပြင်ဆင်နေပါသည်..."
    )
    cancel_flags[uid] = False
    bible = generate_series_translation_bible(s_title, s_genre, uid=uid)

    user_settings["series_title"] = s_title
    user_settings["series_genre"] = s_genre
    user_settings["series_bible"] = bible
    save_text_file(SERIES_TITLE_FILE, s_title)
    save_text_file(SERIES_GENRE_FILE, s_genre)
    save_text_file(SERIES_BIBLE_FILE, bible)
    user_states[uid] = "translate"

    safe_edit(
        message.chat.id,
        status_msg.message_id,
        "✅ ဇာတ်ကားနှင့် အမျိုးအစားကို အောင်မြင်စွာ သတ်မှတ်ပြီးပါပြီ!\n\n"
        "🎬 ဇာတ်ကား: " + s_title + "\n"
        "🎭 Genre: " + s_genre + "\n\n"
        "📖 /glossary ကိုနှိပ်၍ ဤဇာတ်ကားအတွက် သတ်မှတ်ထားသော အခေါ်အဝေါ်များကို ကြည့်ရှုနိုင်ပါသည်။\n"
        "👉 ယခု ဘာသာပြန်လိုသော .ass သို့မဟုတ် .srt Subtitle ဖိုင်ကို ပို့ပေးနိုင်ပါပြီ။"
    )

@bot.message_handler(commands=["clearseries"], func=is_owner)
def cmd_clearseries(message):
    user_settings["series_title"] = ""
    user_settings["series_genre"] = ""
    user_settings["series_bible"] = ""
    user_settings["series_glossary"] = ""
    for f in [SERIES_TITLE_FILE, SERIES_GENRE_FILE, SERIES_BIBLE_FILE, SERIES_GLOSSARY_FILE]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass
    bot.reply_to(message, "🗑 သတ်မှတ်ထားသော ဇာတ်ကားအချက်အလက်ကို ဖျက်လိုက်ပါပြီ။")

@bot.message_handler(commands=["glossary"], func=is_owner)
def cmd_glossary(message):
    s_title = user_settings.get("series_title") or "Auto-Detected"
    s_genre = user_settings.get("series_genre") or "Auto"
    bible = user_settings.get("series_bible", "")
    if not bible:
        return bot.reply_to(message, "📚 လက်ရှိ သတ်မှတ်ထားသော ဇာတ်ကားမှတ်တမ်း မရှိသေးပါ။ /setseries ဖြင့် သတ်မှတ်နိုင်ပါသည်။")
    out = "🎬 ဇာတ်ကား: " + str(s_title) + " (" + str(s_genre) + ")\n\n📖 Series Guide & Terminology:\n" + bible[:3200]
    bot.reply_to(message, out)

@bot.message_handler(commands=["setcast"], func=is_owner)
def cmd_setcast(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        user_states[message.from_user.id] = "setcast"
        return bot.reply_to(message, "👥 ဇာတ်ကောင် စရိုက်နှင့် နာမ်စား ထပ်မံဖြည့်စွက်လိုပါက ရိုက်ထည့်ပါ။")
    cast_str = parts[1].strip()
    user_settings["cast_info"] = cast_str
    save_text_file(CAST_INFO_FILE, cast_str)
    user_states[message.from_user.id] = "translate"
    bot.reply_to(message, "✅ မှတ်သားပြီးပါပြီ: " + cast_str)

@bot.message_handler(commands=["clearcast"], func=is_owner)
def cmd_clearcast(message):
    user_settings["cast_info"] = ""
    if os.path.exists(CAST_INFO_FILE):
        try:
            os.remove(CAST_INFO_FILE)
        except Exception:
            pass
    bot.reply_to(message, "🗑 ဇာတ်ကောင်စာရင်းကို ဖျက်လိုက်ပါပြီ။")

@bot.message_handler(commands=["translate"], func=is_owner)
def cmd_translate(message):
    uid = message.from_user.id
    user_states[uid] = "translate"
    cancel_flags[uid] = False
    s_title = user_settings.get("series_title")
    info_txt = "\n(လက်ရှိ သတ်မှတ်ထားသော ဇာတ်ကား: " + s_title + ")" if s_title else "\n(ဇာတ်ကားနာမည် သတ်မှတ်လိုပါက /setseries ကို အရင်သုံးနိုင်ပါသည်)"
    bot.reply_to(message, "🎬 ဘာသာပြန်လိုသော Subtitle (.ass / .srt) ဖိုင်ကို ပို့ပေးပါ။" + info_txt)

# ==================== SUBTITLE CLEANING & ORTHOGRAPHY ENGINE ====================
def load_subtitle_safe(sub_path):
    for enc in ["utf-8", "utf-8-sig", "utf-16", "latin-1"]:
        try:
            return pysubs2.load(sub_path, encoding=enc)
        except Exception:
            continue
    return pysubs2.load(sub_path)

def is_translatable_line(line):
    if getattr(line, "is_comment", False):
        return False
    txt = line.text.strip()
    if not txt or r"\p1" in txt or r"\p2" in txt or r"\p3" in txt:
        return False
    style_lower = getattr(line, "style", "").lower()
    actor_lower = getattr(line, "name", "").lower()
    if any(k in style_lower or k in actor_lower for k in ["romaji", "kana", "pinyin"]):
        return False
    clean_txt = re.sub(r"\{[^}]*\}", "", txt).strip()
    clean_txt = re.sub(r"^[O0〇●]+(?=[A-Za-z\u1000-\u109F])", "", clean_txt).strip()
    if clean_txt in ["O", "o", "0"] or not re.search(r"[A-Za-z\u1000-\u109F]", clean_txt):
        return False
    return True

def is_song_line(line):
    style, actor, txt = getattr(line, "style", "").lower(), getattr(line, "name", "").lower(), line.text
    if any(k in style or k in actor for k in ["op", "ed", "song", "lyric", "kara", "opening", "ending", "insert", "theme", "music", "chorus"]):
        return True
    return any(c in txt for c in ["♪", "♫", "♬"])

def is_sign_or_screen_line(line):
    style = getattr(line, "style", "").lower()
    actor = getattr(line, "name", "").lower()
    txt = line.text
    if any(k in style or k in actor for k in ["sign", "title", "board", "caption", "label", "msc", "call"]):
        return True
    if actor in ["text", "sign", "signs", "titles"]:
        return True
    if re.search(r"\\(?:pos|move|org|frz|fax|fay)", txt) and not is_song_line(line) and "main" not in style and "default" not in style:
        return True
    return False

def strip_leading_o_and_prefixes(s, is_source=False):
    for _ in range(3):
        s = s.strip()
        s = re.sub(r"^[O0〇●]\s*(?=[A-Z][a-z]|[\u1000-\u109F])", "", s)
        s = re.sub(r"^<\s*Speaker\s*:[^>]*>\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^\(\s*Speaker\s*:[^)]*\)\s*", "", s, flags=re.IGNORECASE)
        s = re.sub(r"^\[\s*Speaker\s*:[^\]]*\]\s*", "", s, flags=re.IGNORECASE)
        if not is_source:
            s = re.sub(r"^(?!Mode\b|Union\b|Magic\b|Spell\b|Chapter\b|Episode\b)[A-Z]{2,14}:\s+", "", s)
    return s.strip()

def strip_dual_language_brackets(text):
    text = re.sub(
        r"\b[A-Za-z][A-Za-z0-9\-\'\s]{1,35}?\s*[\(\[（]\s*([\u1000-\u109F][^\)\]）]*?)\s*[\)\]）]",
        lambda m: m.group(1),
        text
    )
    text = re.sub(
        r"([\u1000-\u109F])\s*[\(\[（]\s*[A-Za-z][A-Za-z0-9\-\'\s]{1,35}?\s*[\)\]）]",
        lambda m: m.group(1),
        text
    )
    text = re.sub(
        r"[\(\[（]\s*([\u1000-\u109F][^\)\]）]*?)\s*[\)\]）]",
        lambda m: " " + m.group(1) + " ",
        text
    )
    return re.sub(r"\s{2,}", " ", text).strip()

def prepare_source_line_for_ai(txt):
    no_tags = re.sub(r"\{[^}]*\}", "", txt)
    no_tags = strip_leading_o_and_prefixes(no_tags, is_source=True)
    if re.search(r"(?:\\N|/N|\r?\n)\s*[-–—]", no_tags):
        return re.sub(r"(?:/N|\r?\n)", lambda _: "\\N", no_tags).strip()
    cleaned = re.sub(r"\s*(?:\\N|/N|\\n|/n|\r?\n)\s*", " ", no_tags)
    return re.sub(r"\s{2,}", " ", cleaned).strip()

def get_speaker_hint(line):
    actor = getattr(line, "name", "").strip()
    if not actor:
        return ""
    low = actor.lower()
    if low in ["ntp", "main", "default", "dialogue", "text", "sign", "signs", "titles", "comment", "fx", "sfx", "op", "ed", "lyric", "lyrics", "unknown", "none", "narrator"]:
        return ""
    if re.match(r"^[A-Za-z][A-Za-z0-9_\-\s]{0,18}$", actor):
        return actor
    return ""

def get_visual_length(s):
    stripped = re.sub(r"[\u102D-\u1030\u1032-\u1037\u1039\u103A\u103D\u103E]", "", s)
    return len(stripped)

def apply_scene_cut_and_timing_polish(subs):
    dialogue_lines = [l for l in subs if not getattr(l, "is_comment", False) and not is_sign_or_screen_line(l) and not is_song_line(l)]
    dialogue_lines.sort(key=lambda x: x.start)
    for i in range(len(dialogue_lines) - 1):
        curr_l = dialogue_lines[i]
        next_l = dialogue_lines[i + 1]
        gap = next_l.start - curr_l.end
        if 0 < gap <= 120 and (curr_l.end - curr_l.start) > 900:
            curr_l.end = max(curr_l.start + 600, next_l.start - 40)

def optimize_readability_and_wrap(text, line_obj=None, is_song=False, is_sign=False):
    if is_song or is_sign or re.search(r"\\(?:pos|move|org|clip|fad)", text):
        return text

    lead_tags = ""
    m = re.match(r"^(\{[^}]+\})+", text)
    if m:
        lead_tags = m.group(0)
        body = text[len(lead_tags):].strip()
    else:
        body = text.strip()

    body = strip_leading_o_and_prefixes(body, is_source=False)
    is_dual_speaker = bool(re.search(r"(?:\\N|/N)\s*[-–—]", body))
    if not is_dual_speaker:
        body = re.sub(r"\s*(?:\\N|/N|\\n|/n)\s*", " ", body)
        body = re.sub(r"\s{2,}", " ", body).strip()

    vis_len = get_visual_length(body)
    if not is_dual_speaker and vis_len > 42 and len(body) > 68 and " " in body:
        mid = len(body) // 2
        spaces = [i for i, ch in enumerate(body) if ch == " "]
        valid_spaces = [sp for sp in spaces if get_visual_length(body[:sp]) >= 14 and get_visual_length(body[sp + 1:]) >= 14]
        if valid_spaces:
            best_split = min(valid_spaces, key=lambda x: abs(x - mid))
            body = body[:best_split].strip() + "\\N" + body[best_split + 1:].strip()

    return lead_tags + body

def normalize_myanmar_unicode(text):
    text = text.replace("ဩော်", "အော်").replace("သြော်", "အော်").replace("ဪော်", "အော်")
    text = text.replace("\u1029\u1031\u102C\u103A", "အော်")
    text = text.replace("\u101E\u103C\u1031\u102C\u103A", "အော်")

    text = re.sub(r"\u1031([\u103B-\u103E]+)", lambda m: m.group(1) + "\u1031", text)
    text = re.sub(r"\u103E([\u103B\u103C\u103D])", lambda m: m.group(1) + "\u103E", text)
    text = re.sub(r"\u103D([\u103B\u103C])", lambda m: m.group(1) + "\u103D", text)
    text = re.sub(r"([\u102F\u1030])([\u102D\u102E\u1032])", lambda m: m.group(2) + m.group(1), text)

    text = text.replace("\u1037\u1036", "\u1036\u1037")
    text = text.replace("\u1036\u102F", "\u102F\u1036")
    text = text.replace("\u1037\u103A", "\u103A\u1037")
    text = text.replace("\u1038\u103A", "\u103A\u1038")

    for ch in ["\u103B", "\u103C", "\u103D", "\u103E", "\u1031", "\u102D", "\u102E", "\u102F", "\u1030", "\u1032", "\u1036", "\u1037", "\u1038", "\u103A"]:
        text = re.sub(ch + r"{2,}", ch, text)
    text = re.sub(r"([ာါ])[ာါ]+", lambda m: m.group(1), text)

    return text

LEFTOVER_ENGLISH_FIXES = [
    (r"ပြန်လည်\s*regenerate\s*ဖြစ်တဲ့\s*စွမ်းရည်", "ပြန်လည်ကုသနိုင်စွမ်း"),
    (r"ပြန်လည်\s*regenerate\s*လုပ်နိုင်တဲ့\s*စွမ်းရည်", "ပြန်လည်ကုသနိုင်စွမ်း"),
    (r"ပြန်လည်\s*regenerate\s*ဖြစ်", "ပြန်လည်ကုသ"),
    (r"ပြန်လည်\s*regenerate\s*လုပ်", "ပြန်လည်ကုသ"),
    (r"(?i)\bregenerate\s*ဖြစ်", "ပြန်လည်ကုသ"),
    (r"(?i)\bregenerate\s*လုပ်", "ပြန်လည်ကုသ"),
    (r"(?i)\bregeneration\b", "ပြန်လည်ကုသနိုင်စွမ်း"),
    (r"(?i)\bregenerate\b", "ပြန်လည်ကုသ"),
    (r"(?i)\bshadow\s+magic\s*:\s*heaven'?s\s+shadow\s+second\s+sight\b", "အရိပ်မှော်ပညာ - ကောင်းကင်ဘုံရဲ့ အရိပ် ဒုတိယအမြင်"),
    (r"(?i)\bdevil\s+union\s+mode\s*:\s*", "နတ်ဆိုးပေါင်းစည်းခြင်းပုံစံ - "),
    (r"(?i)\bdevil\s+union\s+mode\b", "နတ်ဆိုးပေါင်းစည်းခြင်းပုံစံ"),
    (r"(?i)\bunion\s+mode\s*:\s*", "ပေါင်းစည်းခြင်းပုံစံ - "),
    (r"(?i)\bunion\s+mode\b", "ပေါင်းစည်းခြင်းပုံစံ"),
    (r"(?i)\bdevil\s+union\b", "နတ်ဆိုးပေါင်းစည်းခြင်း"),
    (r"(?i)\bmode\s*:\s*([A-Za-z]+)", lambda m: "ပုံစံ - " + m.group(1)),
    (r"(?i)\bshadow\s+magic\b", "အရိပ်မှော်ပညာ"),
    (r"(?i)\bdark\s+magic\b", "အမှောင်မှော်ပညာ"),
    (r"(?i)\blight\s+magic\b", "အလင်းမှော်ပညာ"),
    (r"(?i)\bspatial\s+magic\b", "ဟင်းလင်းပြင်မှော်ပညာ"),
    (r"(?i)\bspatial\s+mage\b", "ဟင်းလင်းပြင်မှော်ဆရာ"),
    (r"(?i)\bbriar\s+magic\b", "ဆူးနွယ်မှော်ပညာ"),
    (r"(?i)\bcursed\s+briars?\b", "ကျိန်စာသင့်ဆူးနွယ်"),
    (r"(?i)\brune\s+arrays?\b", "မှော်အင်းကွက်"),
    (r"(?i)\brunes?\b", "မှော်သင်္ကေတ"),
    (r"(?i)\bslash\s+magic\b", "ခုတ်ပိုင်းခြင်းမှော်ပညာ"),
    (r"(?i)\bgravity\s+magic\b", "ဆွဲငင်အားမှော်ပညာ"),
    (r"(?i)\bbone\s+magic\b", "အရိုးမှော်ပညာ"),
    (r"(?i)\bblood\s+magic\b", "သွေးမှော်ပညာ"),
    (r"(?i)\bfire\s+magic\b", "မီးမှော်ပညာ"),
    (r"(?i)\bwater\s+magic\b", "ရေမှော်ပညာ"),
    (r"(?i)\bwind\s+magic\b", "လေမှော်ပညာ"),
    (r"(?i)\bearth\s+magic\b", "မြေမှော်ပညာ"),
    (r"(?i)\blightning\s+magic\b", "မိုးကြိုးမှော်ပညာ"),
    (r"(?i)\bworld\s+tree\s+magic\b", "ကမ္ဘာ့သစ်ပင်မှော်ပညာ"),
    (r"(?i)\btime\s+magic\b", "အချိန်မှော်ပညာ"),
    (r"(?i)\bspirit\s+magic\b", "ဝိညာဉ်မှော်ပညာ"),
    (r"(?i)\bcurse\s+magic\b", "ကျိန်စာမှော်ပညာ"),
    (r"(?i)\banti[\-\s]?magic\b", "မှော်ပယ်စွမ်းအင်"),
    (r"(?i)\bmagic\s+knights?\b", "မှော်စစ်သည်"),
    (r"(?i)\bwizard\s+king\b", "မှော်ဘုရင်"),
    (r"(?i)\bmana\s+method\b", "မှော်စွမ်းအင်နည်းစနစ်"),
    (r"(?i)\bmana\s+zone\b", "မှော်စွမ်းအင်နယ်မြေ"),
    (r"(?i)\bmana\b", "မှော်စွမ်းအင်"),
    (r"(?i)\bgrimoire\b", "မှော်ကျမ်း"),
    (r"(?i)\bdark\s+triad\b", "အမှောင်သုံးဖော်"),
    (r"(?i)\bdark\s+disciples?\b", "အမှောင်တပည့်"),
    (r"(?i)\bmagic\b", "မှော်စွမ်းအား")
]

UNIVERSAL_ORTHO_FIXES = [
    (r"ဩော်", "အော်"), (r"သြော်", "အော်"),
    (r"မာရ်နတ်ဘုရင်", "နတ်ဆိုးဘုရင်"), (r"မာန်နတ်ဘုရင်", "နတ်ဆိုးဘုရင်"),
    (r"မာရ်နတ်", "နတ်ဆိုး"), (r"မာန်နတ်", "နတ်ဆိုး"),
    (r"အန်တီမှော်စွမ်းအင်", "မှော်ပယ်စွမ်းအင်"), (r"အန်တီမှော်", "မှော်ပယ်"),
    (r"ရွန်စာတန်းတွေ", "မှော်သင်္ကေတတွေ"), (r"ရွန်စာတန်း", "မှော်သင်္ကေတ"),
    (r"မာနာ", "မှော်စွမ်းအင်"),

    (r"တည်ရှိနေတာပေါ့$", "ရှိနေတာ"),
    (r"နေတာပေါ့$", "နေတာ"),
    (r"တာပေါ့$", "တာ"),

    (r"ပိုကောင်းလာခဲ့ပြီ", "ပိုကောင်းလာပြီ"),
    (r"ကောင်းလာခဲ့ပြီ", "ကောင်းလာပြီ"),
    (r"သန်မာလာခဲ့ပြီ", "သန်မာလာပြီ"),
    (r"တိုးတက်လာခဲ့ပြီ", "တိုးတက်လာပြီ"),
    (r"ပြောင်းလဲလာခဲ့ပြီ", "ပြောင်းလဲလာပြီ"),
    (r"ပြောင်းလဲသွားခဲ့ပြီ", "ပြောင်းလဲသွားပြီ"),
    (r"ဖြစ်လာခဲ့ပြီ", "ဖြစ်လာပြီ"),
    (r"ဖြစ်သွားခဲ့ပြီ", "ဖြစ်သွားပြီ"),
    (r"သေသွားခဲ့ပြီ", "သေသွားပြီ"),
    (r"ပျောက်ကွယ်သွားခဲ့ပြီ", "ပျောက်ကွယ်သွားပြီ"),
    (r"ပြီးဆုံးသွားခဲ့ပြီ", "ပြီးဆုံးသွားပြီ"),
    (r"ရောက်လာခဲ့ပြီ", "ရောက်လာပြီ"),
    (r"တွေ့ရှိခဲ့ပြီ", "ရှာတွေ့သွားပြီ"),
    (r"သိရှိခဲ့ပြီ", "သိသွားပြီ"),

    (r"ကျွမ်းကျင်ပိုင်နိုင်အောင်\s*လုပ်ခြင်းအားဖြင့်", "ကျွမ်းကျင်သွားတဲ့အတွက်"),
    (r"ပိုင်နိုင်အောင်\s*လုပ်ခြင်းအားဖြင့်", "ပိုင်နိုင်သွားလို့"),
    (r"လုပ်ခြင်းအားဖြင့်", "လုပ်လိုက်လို့"),
    (r"ခြင်းအားဖြင့်", "တဲ့အတွက်"),
    (r"မှန်ကန်စွာ\s*သုံးတတ်တဲ့နည်း", "လိုသလို အသုံးချနိုင်မယ့်နည်း"),
    (r"လို့\s*သူတို့(?:က)?\s*ပြောကြပါတယ်$", "တဲ့"),
    (r"လို့\s*သူတို့(?:က)?\s*ပြောကြတယ်$", "တဲ့"),

    (r"ဆုံတွေ့?ခဲ့မယ်", "ဆုံတွေ့ခဲ့တယ်"),
    (r"ဆုံတွေ(?!့)", "ဆုံတွေ့"),
    (r"တွေခဲ့", "တွေ့ခဲ့"),
    (r"တွေရ(?=[တမပဘလနခသအ\s]|$)", "တွေ့ရ"),
    (r"တွေမယ်", "တွေ့မယ်"),
    (r"တွေပြီ", "တွေ့ပြီ"),
    (r"တွေပီ", "တွေ့ပြီ"),
    (r"တွေလို့", "တွေ့လို့"),
    (r"တွေရင်", "တွေ့ရင်"),
    (r"တွေနိုင်", "တွေ့နိုင်"),
    (r"တွေချင်", "တွေ့ချင်"),
    (r"မေသွား", "မေ့သွား"),
    (r"မေနေ", "မေ့နေ"),
    (r"ပြည်စုံ", "ပြည့်စုံ"),
    (r"အပြည်အဝ", "အပြည့်အဝ"),
    (r"ရွေလျား", "ရွေ့လျား"),

    (r"တချိန်လုံး", "တစ်ချိန်လုံး"), (r"တယောက်", "တစ်ယောက်"), (r"တခု", "တစ်ခု"),
    (r"တခါး", "တံခါး"), (r"တခါ(?!း)", "တစ်ခါ"), (r"တနေ့", "တစ်နေ့"), (r"တမျိုး", "တစ်မျိုး"),
    (r"တပိုင်း", "တစ်ပိုင်း"), (r"တကောင်(?!့)", "တစ်ကောင်"), (r"တလျှောက်လုံး", "တစ်လျှောက်လုံး"),
    (r"သက်ပုံ", "သတ်ပုံ"), (r"ရင်ဘက်", "ရင်ဘတ်"), (r"အရှေ့ဖက်", "အရှေ့ဘက်"),
    (r"ရှေ့ဖက်", "ရှေ့ဘက်"), (r"အနောက်ဖက်", "အနောက်ဘက်"), (r"နောက်ဖက်", "နောက်ဘက်"),
    (r"ဘယ်ဖက်", "ဘယ်ဘက်"), (r"ညာဖက်", "ညာဘက်"), (r"အပေါ်ဖက်", "အပေါ်ဘက်"),
    (r"အောက်ဖက်", "အောက်ဘက်"), (r"အပြင်ဖက်", "အပြင်ဘက်"), (r"အတွင်းဖက်", "အတွင်းဘက်"),
    (r"ဟိုဖက်", "ဟိုဘက်"), (r"ဒီဖက်", "ဒီဘက်"), (r"တဖက်သတ်", "တစ်ဖက်သတ်"),
    (r"မမျှော်လင်ဘဲ", "မမျှော်လင့်ဘဲ"), (r"မျှော်လင်နေ", "မျှော်လင့်နေ"),
    (r"မျှော်လင်ထား", "မျှော်လင့်ထား"), (r"မျှော်လင်ချက်", "မျှော်လင့်ချက်"),
    (r"ခန္ဒာကိုယ်", "ခန္ဓာကိုယ်"), (r"ခန္တာကိုယ်", "ခန္ဓာကိုယ်"), (r"နှာဗူး", "နှာဘူး"),
    (r"ပါးစတ်", "ပါးစပ်"), (r"နှုတ်ခန်း", "နှုတ်ခမ်း"), (r"နုတ်ခမ်း", "နှုတ်ခမ်း"),
    (r"လက်ဘက်ရည်", "လက်ဖက်ရည်"), (r"လက်ဘက်", "လက်ဖက်"), (r"သတိ္တ", "သတ္တိ"),
    (r"သတ္တီ", "သတ္တိ"), (r"သိက္ခါ", "သိက္ခာ"), (r"အိန္ဒြေ", "ဣန္ဒြေ"),
    (r"ဝိညာဥ်", "ဝိညာဉ်"), (r"ဝိဉာဉ်", "ဝိညာဉ်"), (r"ကျိုးစား", "ကြိုးစား"),
    (r"ကျိုးပမ်း", "ကြိုးပမ်း"), (r"စိတ်လုပ်ရှား", "စိတ်လှုပ်ရှား"),
    (r"အနှောက်အယှက်", "အနှောင့်အယှက်"), (r"အနှောက်ယှက်", "အနှောင့်အယှက်"),
    (r"နှောက်ယှက်", "နှောင့်ယှက်"), (r"လျို့ဝှက်", "လျှို့ဝှက်"), (r"လျှိုဝှက်", "လျှို့ဝှက်"),
    (r"လျစ်လျူရူ", "လျစ်လျူရှု"), (r"လစ်လျူရှု", "လျစ်လျူရှု"), (r"စိုးရိန်", "စိုးရိမ်"),
    (r"ပက်ဝန်းကျင်", "ပတ်ဝန်းကျင်"), (r"ပတ်ဝန်းကြင်", "ပတ်ဝန်းကျင်"), (r"ဆုံးဖြက်", "ဆုံးဖြတ်"),
    (r"ဆပ်သွယ်", "ဆက်သွယ်"), (r"ဆပ်လက်", "ဆက်လက်"), (r"လပ်နက်", "လက်နက်"),
    (r"မျတ်နှာ", "မျက်နှာ"), (r"မျတ်လုံး", "မျက်လုံး"), (r"မျတ်ရည်", "မျက်ရည်"),
    (r"အသတ်ရှင်", "အသက်ရှင်"), (r"အသတ်ရှူ", "အသက်ရှူ"), (r"အသက်ရူ", "အသက်ရှူ"),
    (r"တိုတ်ခိုက်", "တိုက်ခိုက်"), (r"ပျက်ဆီး", "ပျက်စီး"), (r"ပျတ်စီး", "ပျက်စီး"),
    (r"ဖျတ်ဆီး", "ဖျက်ဆီး"), (r"စီးကမ်း", "စည်းကမ်း"), (r"ပစည်း", "ပစ္စည်း"),
    (r"ပစ်စည်း", "ပစ္စည်း"), (r"ဥာဏ်", "ဉာဏ်"), (r"ညီအကို", "ညီအစ်ကို"),
    (r"မောင်နှစ်မ", "မောင်နှမ"), (r"တစ်ကယ်", "တကယ်"), (r"တစ်ဖြည်းဖြည်း", "တဖြည်းဖြည်း"),
    (r"တဖြေးဖြေး", "တဖြည်းဖြည်း"), (r"တစ်မင်", "တမင်"), (r"ခနလေး", "ခဏလေး"),
    (r"ခနစောင့်", "ခဏစောင့်"), (r"ယောက်ကျား", "ယောက်ျား"), (r"ယောကျ်ား", "ယောက်ျား"),
    (r"အဲ့တာ", "အဲဒါ"), (r"အဲ့ဒါ", "အဲဒါ"), (r"အဲတာ", "အဲဒါ"),
    (r"အဲ့လို", "အဲဒီလို"), (r"အဲလို", "အဲဒီလို"), (r"အဲ့ဒီ", "အဲဒီ"),
    (r"ပီးတော့", "ပြီးတော့"), (r"ပီးရင်", "ပြီးရင်"), (r"ပီးပြီ", "ပြီးပြီ"),
    (r"သွားပီ(?=$|\s)", "သွားပြီ"), (r"လာပီ(?=$|\s)", "လာပြီ"),
    (r"သိပီ(?=$|\s)", "သိပြီ"), (r"ရပီ(?=$|\s)", "ရပြီ"), (r"ဟုတ်ပီ(?=$|\s)", "ဟုတ်ပြီ"),
    (r"မပီး", "မပြီး"), (r"ဖစ်နေ", "ဖြစ်နေ"), (r"ဖစ်သွား", "ဖြစ်သွား"),
    (r"မဖစ်", "မဖြစ်"), (r"ဖစ်နိုင်", "ဖြစ်နိုင်"), (r"ဖစ်တယ်", "ဖြစ်တယ်"),
    (r"ဖစ်ပါတယ်", "ဖြစ်ပါတယ်"), (r"ကျေးဇူးတင်ပတယ်", "ကျေးဇူးတင်ပါတယ်"),
    (r"ဟုတ်ပတယ်", "ဟုတ်ပါတယ်"), (r"မဟုတ်ပဘူး", "မဟုတ်ပါဘူး"),
    (r"သိပတယ်", "သိပါတယ်"), (r"ရပတယ်", "ရပါတယ်"),
    (r"တောင်းပန်ပတယ်", "တောင်းပန်ပါတယ်"), (r"စောင့်လျှောက်", "စောင့်ရှောက်"),
    (r"ကြည့်ရူ", "ကြည့်ရှု"), (r"အန္တရယ်", "အန္တရာယ်"), (r"အန္တာရာယ်", "အန္တရာယ်"),
    (r"ပြသနာ", "ပြဿနာ"), (r"ပြသာနာ", "ပြဿနာ"), (r"သတ်သေ", "သက်သေ"),
    (r"အဓိပ္ပါယ်", "အဓိပ္ပာယ်"), (r"အဓိပယ်", "အဓိပ္ပာယ်"), (r"ပတ်သတ်", "ပတ်သက်"),
    (r"ပက်သက်", "ပတ်သက်"), (r"ဆပ်ဆံ", "ဆက်ဆံ"), (r"လပ်ခံ", "လက်ခံ"),
    (r"သတ်ဆိုင်", "သက်ဆိုင်"), (r"အံ့သြ", "အံ့ဩ"), (r"အံသြ", "အံ့ဩ"),
    (r"အခြေနေ", "အခြေအနေ"), (r"ဘယ်လိုပဲဖစ်ဖစ်", "ဘယ်လိုပဲဖြစ်ဖြစ်"),
    (r"ဆင်ပိုင်း", "Senpai"), (r"ဆင်ပိုင်", "Senpai"), (r"ဆန်ပိုင်း", "Senpai"),
    (r"ဆန်ဆေး", "Sensei"), (r"ဆင်ဆေး", "Sensei"), (r"သောကြောင့်", "လို့"),
    (r"သည့်အတွက်ကြောင့်", "တာကြောင့်"), (r"သည့်အတွက်", "တဲ့အတွက်"),
    (r"သော်လည်းပဲ", "ပေမဲ့"), (r"သော်လည်း", "ပေမဲ့"), (r"သည့်အခါ", "တဲ့အခါ"),
    (r"မည်ဆိုလျှင်", "မယ်ဆိုရင်"), (r"မည်နည်း", "မလဲ"), (r"အဘယ်ကြောင့်", "ဘာလို့"),
    (r"မည်သို့", "ဘယ်လို"), (r"မည်သူ", "ဘယ်သူ"), (r"မဟုတ်ချေ", "မဟုတ်ဘူး"),
    (r"မဟုတ်ပေ", "မဟုတ်ပါဘူး"), (r"ဖြစ်ပေသည်", "ဖြစ်ပါတယ်"), (r"ဖြစ်သည်", "ဖြစ်တယ်"),
    (r"သွားမည်", "သွားမယ်"), (r"လုပ်မည်", "လုပ်မယ်"), (r"ပြောမည်", "ပြောမယ်"),
    (r"လာမည်", "လာမယ်"), (r"ရမည်", "ရမယ်"), (r"လိမ့်မည်", "လိမ့်မယ်"),
    (r"ကျွန်ုပ်တို့", "ငါတို့"), (r"ကျွန်ုပ်", "ကျုပ်")
]

def enforce_semantic_accuracy(trans_text, orig_text):
    trans_text = strip_dual_language_brackets(trans_text)
    for pat, rep in LEFTOVER_ENGLISH_FIXES:
        trans_text = re.sub(pat, rep, trans_text)
    return trans_text

def fallback_short_english_phrases(orig_text):
    clean_o = prepare_source_line_for_ai(orig_text)
    low = re.sub(r"[.!?,;~…\"']+", "", clean_o).strip().lower()
    short_dict = {
        "union": "ပေါင်းစည်းခြင်း",
        "devil union": "နတ်ဆိုးပေါင်းစည်းခြင်း",
        "all right": "ကောင်းပြီလေ", "alright": "ကောင်းပြီလေ", "good morning": "မင်္ဂလာနံနက်ခင်းပါ",
        "morning": "မင်္ဂလာနံနက်ခင်းပါ", "good night": "ကောင်းသောညပါ", "good evening": "မင်္ဂလာညချမ်းပါ",
        "hello": "မင်္ဂလာပါ", "hi": "ဟိုင်း", "hey": "ဟေး", "okay": "အိုကေ", "ok": "အိုကေ",
        "yes": "ဟုတ်ကဲ့", "yeah": "အင်း", "yep": "အင်း", "no": "မဟုတ်ဘူး", "nope": "ဟင့်အင်း",
        "what": "ဘာလဲဟ", "why": "ဘာလို့လဲ", "who": "ဘယ်သူလဲ", "where": "ဘယ်မှာလဲ", "when": "ဘယ်တုန်းကလဲ",
        "really": "တကယ်လား", "seriously": "တကယ်ကြီးလား", "wait": "ခဏနေဦး", "hold on": "ခဏနေပါဦး",
        "stop": "ရပ်လိုက်စမ်း", "stop it": "တော်တော့ကွာ", "shut up": "ပါးစပ်ပိတ်ထားစမ်း",
        "thank you": "ကျေးဇူးတင်ပါတယ်", "thanks": "ကျေးဇူးပဲ", "sorry": "တောင်းပန်ပါတယ်",
        "i'm sorry": "တောင်းပန်ပါတယ်", "excuse me": "ခွင့်ပြုပါဦး", "see you": "နောက်မှတွေ့မယ်",
        "bye": "တာ့တာ", "goodbye": "သွားတော့မယ်", "let's go": "သွားကြစို့", "come on": "လာပါကွာ",
        "hurry": "မြန်မြန်လုပ်", "hurry up": "မြန်မြန်လုပ်ပါဟ", "help": "ကယ်ကြပါဦး",
        "impossible": "မဖြစ်နိုင်တာ", "no way": "မဖြစ်နိုင်တာကွာ", "delicious": "စားလို့ကောင်းလိုက်တာ",
        "itadakimasu": "စားပါတော့မယ်", "thank you for the meal": "စားလို့ကောင်းခဲ့ပါတယ်",
        "i'm home": "ပြန်ရောက်ပါပြီ", "welcome back": "ပြန်လာတာ ကြိုဆိုပါတယ်", "professor": "ပါမောက္ခကြီး", "safe": "လွတ်တယ်"
    }
    if low in short_dict:
        return short_dict[low]
    for pat, rep in LEFTOVER_ENGLISH_FIXES:
        if re.search(pat, clean_o):
            converted = re.sub(pat, rep, clean_o)
            if re.search(r"[\u1000-\u109F]", converted):
                return converted
    return ""

def sanitize_myanmar_syllables_and_glitches(text):
    text = strip_leading_o_and_prefixes(text, is_source=False)
    text = strip_dual_language_brackets(text)
    text = normalize_myanmar_unicode(text)

    text = re.sub(r"ဒီအချိန်တွေ[ုူိီေဲံ့း]*[က-အ]?[့်း]+", "ဒီအချိန်တုန်းက", text)
    text = re.sub(r"အချိန်တွေ[ုူိီေဲံ့း]*[က-အ]?[့်း]+", "အချိန်တုန်းက", text)
    text = re.sub(r"တွေ[ုူ][နမငကတပ][့်း]+", "တုန်းက", text)
    text = re.sub(r"တွေ[ုူိီဲံ့]+", "တွေ", text)

    text = re.sub(r"မျှော်လင်္[က-အ][ျြွှ]?", "မျှော်လင့်", text)
    text = re.sub(r"(?<!အ)င်္ကျ(?!ီ)", "င့်", text)
    text = re.sub(r"\u1004\u103A\u1039(?![ကခဂဃဘပမသဟ])", "\u1004\u103A\u1037", text)
    text = re.sub(r"(?<!\u1004)\u103A\u1039(?![က-အ])", "\u103A\u1037", text)
    text = text.replace("\u1037\u1039", "\u1037").replace("\u1039\u1037", "\u1037")
    text = re.sub(r"(^|\s)[\u102B-\u103E]+", lambda m: m.group(1), text)
    return text

def fix_universal_myanmar_orthography(text, is_song=False):
    text = text.replace("\u0d06", "အ").replace("\u0d05", "အ")
    text = re.sub(r"[\u200B-\u200D\uFEFF]", "", text)
    text = sanitize_myanmar_syllables_and_glitches(text)

    for pat, rep in UNIVERSAL_ORTHO_FIXES:
        text = re.sub(pat, rep, text)

    text = sanitize_myanmar_syllables_and_glitches(text)

    tags = []
    def save_tag(m):
        tags.append(m.group(0))
        return "@@TAG" + str(len(tags) - 1) + "@@"
    temp_text = re.sub(r"\{[^}]*\}", save_tag, text)
    allowed_pattern = r"[^\u1000-\u109F\uAA60-\uAA7F\u0020-\u007E\u2010-\u2027♪♫♬\n\r]"
    temp_text = re.sub(allowed_pattern, "", temp_text)
    for i, t in enumerate(tags):
        temp_text = temp_text.replace("@@TAG" + str(i) + "@@", t)
    return temp_text

def clean_subtitle_line(text, orig_text="", line_obj=None, is_song=False, is_sign=False):
    for _ in range(5):
        text = re.sub(r"^\s*\[\s*\d+\s*\]\s*[:\-]?\s*", "", text)
        text = re.sub(r"\[\s*(?:SONG|FAST|SIGN|Text)\s*\]", "", text, flags=re.IGNORECASE)
        text = re.sub(r"<\s*(?:M|F|Actor|Speaker|ScreenText|ChatMsg|Chat)[^>]*>", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\(\s*Speaker\s*:[^)]*\)", "", text, flags=re.IGNORECASE)

    text = re.sub(r"^[\s:\-]+", "", text)

    tags = []
    def hide_tag(m):
        tags.append(m.group(0))
        return "@@ASS" + str(len(tags) - 1) + "@@"
    work = re.sub(r"\{[^}]*\}", hide_tag, text)
    work = strip_leading_o_and_prefixes(work, is_source=False)
    work = strip_dual_language_brackets(work)

    if orig_text:
        work = enforce_semantic_accuracy(work, orig_text)
    work = fix_universal_myanmar_orthography(work, is_song=is_song)
    work = strip_dual_language_brackets(work)
    work = strip_leading_o_and_prefixes(work, is_source=False)

    if orig_text and not re.search(r"[\u1000-\u109F]", work):
        fb = fallback_short_english_phrases(orig_text)
        if fb:
            work = fb

    work = re.sub(r'[?!？！;；၊။""\'\'…]+', " ", work)
    work = re.sub(r"\.{2,}", " ", work)
    work = re.sub(r"(?i)\s*[/\\]n\s*", lambda _: "\\N", work)
    work = re.sub(r"([\u1000-\u109F])\s+N\s+([\u1000-\u109F])", lambda m: m.group(1) + " " + m.group(2), work)
    work = re.sub(r"\s{2,}", " ", work).strip()

    for i, t in enumerate(tags):
        work = work.replace("@@ASS" + str(i) + "@@", t)

    return optimize_readability_and_wrap(work, line_obj=line_obj, is_song=is_song, is_sign=is_sign)

def has_leftover_english_words(trans_text):
    no_tags = re.sub(r"\{[^}]*\}", "", trans_text)
    no_tags = no_tags.replace("\\N", " ")
    no_tags = re.sub(r"\b[A-Z][a-zA-Z]*-(?:kun|chan|san|sama|sensei|senpai|dono)\b", "", no_tags)
    if re.search(r"\b[a-z]{3,}\b", no_tags):
        return True
    if re.search(r"\b(?:is|am|to|of|in|on|at|by|we|he|my|me|us|do|go|so|no|if|or|as|it|be|How|What|Why|Who|Where|When|The|This|That|You|Your|They|Their)\b", no_tags):
        return True
    return False

def is_valid_translation(trans_text, orig_text):
    clean_trans = re.sub(r"\{[^}]*\}", "", trans_text).strip()
    if not clean_trans or not re.search(r"[\u1000-\u109F]", clean_trans):
        return False
    if has_leftover_english_words(clean_trans):
        return False
    return True

def extract_leading_ass_tags(text):
    m = re.match(r"^(\{[^}]+\})+", text.strip())
    return m.group(0) if m else ""

def build_local_episode_context(subs, valid_items):
    speakers = set()
    honorific_names = set()
    ignore_words = {
        "ntp", "main", "default", "dialogue", "text", "sign", "signs", "titles",
        "comment", "fx", "sfx", "op", "ed", "lyric", "lyrics", "unknown", "none",
        "narrator", "all", "everyone", "both", "crowd", "voice", "voices", "man",
        "woman", "boy", "girl", "knight", "knights", "captain", "soldier", "soldiers"
    }
    for line in subs:
        sp = get_speaker_hint(line)
        if sp and sp.lower() not in ignore_words:
            speakers.add(sp.title() if sp.isupper() else sp)

    for idx, txt in valid_items:
        clean_t = prepare_source_line_for_ai(txt)
        for m in re.finditer(r"\b([A-Z][a-z]{2,}-(?:kun|chan|san|sama|sensei|senpai|dono))\b", clean_t):
            honorific_names.add(m.group(1))

    all_char_names = sorted(list(speakers | honorific_names))
    if all_char_names:
        return "Episode Character Names (Keep ONLY these personal names in English): " + ", ".join(all_char_names[:35])
    return ""

def parse_ai_translation_output(result_text, subs, expected_indices, orig_map, allow_partial_english=False):
    matched_indices = set()
    if not result_text:
        return matched_indices
    for match in re.finditer(r"^\s*\[\s*(\d+)\s*\][\s:\-]*(.+)$", result_text, re.MULTILINE):
        idx = int(match.group(1))
        raw_trans = match.group(2).strip()
        if idx in expected_indices and idx < len(subs) and raw_trans:
            orig_eng = orig_map.get(idx, subs[idx].text)
            song_flag = is_song_line(subs[idx])
            sign_flag = is_sign_or_screen_line(subs[idx])
            cleaned_trans = clean_subtitle_line(
                raw_trans, orig_text=orig_eng, line_obj=subs[idx], is_song=song_flag, is_sign=sign_flag
            )
            valid_check = bool(cleaned_trans and re.search(r"[\u1000-\u109F]", cleaned_trans)) if allow_partial_english else is_valid_translation(cleaned_trans, orig_eng)
            if valid_check:
                lead_tags = extract_leading_ass_tags(orig_eng)
                if lead_tags and not cleaned_trans.startswith("{"):
                    cleaned_trans = lead_tags + cleaned_trans
                subs[idx].text = cleaned_trans
                matched_indices.add(idx)
    return matched_indices

@bot.message_handler(content_types=["text"], func=lambda m: is_owner(m) and not (m.text or "").startswith("/"))
def handle_text_states(message):
    uid = message.from_user.id
    state = user_states.get(uid)
    if state == "setseries":
        Thread(target=process_setseries_input, args=(message, uid, message.text.strip()), daemon=True).start()
        return
    if state == "setcast":
        cast_str = message.text.strip()
        user_settings["cast_info"] = cast_str
        save_text_file(CAST_INFO_FILE, cast_str)
        user_states[uid] = "translate"
        bot.reply_to(message, "✅ မှတ်သားပြီးပါပြီ: " + cast_str + "\nယခု ဘာသာပြန်မည့် Subtitle ဖိုင်ကို ပို့ပါ။")

# ==================== HANDLE SUBTITLE DOCUMENTS ====================
@bot.message_handler(content_types=["document"], func=is_owner)
def handle_incoming_document(message):
    Thread(target=process_subtitle_document, args=(message,), daemon=True).start()

def process_subtitle_document(message):
    uid = message.from_user.id
    doc = message.document
    orig_name = doc.file_name or "subtitle.ass"
    ext = os.path.splitext(orig_name)[1].lower()

    if ext not in [".srt", ".ass"]:
        return bot.reply_to(message, "⚠️ ဘာသာပြန်ရန် .ass သို့မဟုတ် .srt Subtitle ဖိုင်ကိုသာ ပို့ပေးပါ။")

    user_states[uid] = "translate"
    cancel_flags[uid] = False
    msg = bot.reply_to(message, "⏳ Subtitle ဖိုင်ကို ဒေါင်းလုဒ်ဆွဲပြီး Gemini 4 Hydrogen Translator ဖြင့် စတင်နေပါပြီ...")
    chat_id = message.chat.id
    msg_id = msg.message_id
    dl_dir = None

    try:
        dl_dir = "downloads/sub_" + str(message.message_id)
        os.makedirs(dl_dir, exist_ok=True)

        file_info = bot.get_file(doc.file_id)
        downloaded_bytes = bot.download_file(file_info.file_path)
        sub_path = os.path.join(dl_dir, orig_name)
        with open(sub_path, "wb") as f:
            f.write(downloaded_bytes)

        base_name = os.path.splitext(orig_name)[0]
        out_file = os.path.join(dl_dir, base_name + "_MM" + ext)
        subs = load_subtitle_safe(sub_path)

        for line in subs:
            if not getattr(line, "is_comment", False) and line.text:
                lead = extract_leading_ass_tags(line.text)
                body_part = line.text[len(lead):]
                body_part = re.sub(r"^[O0〇●](?=[A-Z][a-z])", "", body_part.strip())
                line.text = lead + body_part

        apply_scene_cut_and_timing_polish(subs)

        valid_items = [(i, line.text.strip()) for i, line in enumerate(subs) if is_translatable_line(line)]
        orig_map = {i: txt for i, txt in valid_items}
        total_lines = len(valid_items)
        if total_lines == 0:
            return safe_edit(chat_id, msg_id, "⚠️ ဘာသာပြန်ရမည့် စာသား မတွေ့ပါ။")

        active_title = user_settings.get("series_title", "").strip()
        active_genre = user_settings.get("series_genre", "").strip()
        active_bible = user_settings.get("series_bible", "").strip()

        if not active_title:
            guessed_title = guess_anime_title_from_filename(orig_name)
            if guessed_title and len(guessed_title) >= 3:
                active_title = guessed_title
                active_genre = "Auto-Detected"
                safe_edit(chat_id, msg_id, "🔍 ဖိုင်နာမည်မှ " + active_title + " ဇာတ်ကားကို သိရှိပြီး ဇာတ်လမ်းအခေါ်အဝေါ်များ (Series Guide) တည်ဆောက်နေပါသည်...")
                active_bible = generate_series_translation_bible(active_title, active_genre, uid=uid)

        local_glossary = build_local_episode_context(subs, valid_items)
        user_settings["series_glossary"] = local_glossary
        save_text_file(SERIES_GLOSSARY_FILE, local_glossary)

        manual_cast = user_settings.get("cast_info", "")
        series_context_block = "\n"
        if active_title:
            genre_disp = active_genre if active_genre else "Auto"
            series_context_block += "TARGET SERIES: " + active_title + " (Genre: " + genre_disp + ")\n"
        if active_bible:
            series_context_block += "SERIES LOCALIZATION GUIDE:\n" + active_bible + "\n\n"
        if manual_cast:
            series_context_block += "CHARACTER NOTES: " + manual_cast + "\n"
        if local_glossary:
            series_context_block += local_glossary + "\n\n"

        CHUNK_SIZE = 25
        chunks = [valid_items[i:i + CHUNK_SIZE] for i in range(0, total_lines, CHUNK_SIZE)]
        total_chunks = len(chunks)
        prev_context = []

        core_rules = (
            "Translate the subtitle lines below into crisp, natural, Pro-Fansub spoken Myanmar (Burmese) — NEVER like a novel or storybook.\n\n"
            "STRICT TRANSLATION RULES:\n"
            "1. ANTI-NOVEL / ANTI-FAIRYTALE RULE (CRITICAL): Anime subtitles must sound like real spoken Burmese, NOT literary narration. "
            "In narration or monologues, use plain casual spoken endings (`တယ်`, `ပြီ`, `နေတာ`, `ခဲ့တယ်`), NOT polite/bookish endings (`ပါတယ်`, `ပါပြီ`, `ခဲ့ပါတယ်`) and NOT literary verbs (`တည်ရှိ`, `ရောက်ရှိ`, `ကျန်ရစ်`, `လာရောက်`, `များသောအားဖြင့်`).\n"
            "2. ZERO FORCED FILLERS: STRICTLY FORBIDDEN to tack on `ပေါ့`, `တာပေါ့`, `ရှင်`, `ဗျာ`, `ခင်ဗျာ` unless the original line explicitly demands that exact tone.\n"
            "3. NO LITERAL TRANSLATION: Never translate word-for-word like Google Translate. Translate the true meaning according to story context and genre.\n"
            "4. PRONOUN SAFETY: Never mismatch male/female pronouns. If speaker/listener gender or relationship is unclear, use neutral pronouns or omit the pronoun completely while keeping the full meaning.\n"
            "5. NO PHONETIC TRANSLITERATION & ZERO LEFTOVER ENGLISH: Keep ONLY personal character names and place names in English. Translate 100% of all other words into natural Burmese meaning (never phonetic transliteration, never leave English words behind, no dual-language brackets).\n"
            "6. NO PUNCTUATION SYMBOLS: Do NOT include `?`, `;`, or `!` in the Burmese translation. Express questions and character attitude naturally through spoken Burmese endings.\n"
            "7. PERFECT MYANMAR SPELLING & NATURAL ADAPTATION: Maintain 100% accurate standard Burmese spelling with zero typos. Freely adjust phrasing (လိုတိုးပိုလျှော့) so every line is concise and natural.\n"
            "8. CLEAN FORMAT: No `<Speaker: ...>` tags, no speaker prefixes, no line breaks (`/N` or `\\N`). Output ONLY `[index] burmese_translation`.\n\n"
        )

        series_label = "🎬 ဇာတ်ကား: " + active_title + " (" + active_genre + ")\n" if active_title else ""

        for c_idx, chunk in enumerate(chunks, start=1):
            if cancel_flags.get(uid):
                raise ValueError("Cancelled by user")
            pct = int(((c_idx - 1) / total_chunks) * 100)
            progress_msg = (
                "⚡ Gemini 4 Hydrogen Pro Translator ဖြင့် အကောင်းဆုံး ဘာသာပြန်နေပါပြီ...\n\n"
                "📂 ဖိုင်: " + orig_name + "\n"
                + series_label +
                "📊 အပိုင်း: " + str(c_idx) + " / " + str(total_chunks) + " (" + str(pct) + "%)\n"
                "📝 စုစုပေါင်း: " + str(total_lines) + " ကြောင်း\n\n"
                "🛑 ရပ်တန့်လိုပါက /cancel နှိပ်ပါ"
            )
            safe_edit(chat_id, msg_id, progress_msg)

            formatted_lines = []
            expected_indices = set()
            for idx, txt in chunk:
                expected_indices.add(idx)
                clean_line = prepare_source_line_for_ai(txt)
                sp_hint = get_speaker_hint(subs[idx])
                if sp_hint:
                    formatted_lines.append(f"[{idx}] <Speaker: {sp_hint}> {clean_line}")
                else:
                    formatted_lines.append("[" + str(idx) + "] " + clean_line)
            chunk_text = "\n".join(formatted_lines)

            prev_block = ""
            if prev_context:
                prev_block = "PREVIOUS DIALOGUE CONTEXT (For story continuity only, do NOT output these):\n" + "\n".join(prev_context[-8:]) + "\n\n"

            next_block = ""
            if c_idx < total_chunks:
                next_chunk = chunks[c_idx][:5]
                next_preview = [prepare_source_line_for_ai(t) for _, t in next_chunk]
                if next_preview:
                    next_block = "\nUPCOMING LINES PREVIEW (For context only, do NOT translate these yet):\n" + "\n".join(next_preview) + "\n\n"

            prompt = (
                core_rules
                + series_context_block
                + prev_block
                + "LINES TO TRANSLATE:\n" + chunk_text
                + next_block
            )

            draft_text = ""
            try:
                draft_text = call_gemini_reliable(prompt, uid=uid, timeout_sec=75, temp=0.2)
            except Exception as e:
                if "Cancelled by user" in str(e):
                    raise
                mid_pt = max(1, len(formatted_lines) // 2)
                for sub_lines in [formatted_lines[:mid_pt], formatted_lines[mid_pt:]]:
                    if not sub_lines:
                        continue
                    sub_prompt = core_rules + series_context_block + "LINES TO TRANSLATE:\n" + "\n".join(sub_lines)
                    try:
                        part_res = call_gemini_reliable(sub_prompt, uid=uid, timeout_sec=60, temp=0.2)
                        draft_text += "\n" + part_res
                    except Exception as sub_e:
                        if "Cancelled by user" in str(sub_e):
                            raise

            parse_ai_translation_output(draft_text, subs, expected_indices, orig_map, allow_partial_english=False)

            missing_indices = expected_indices - set(i for i in expected_indices if is_valid_translation(subs[i].text, orig_map[i]))
            if missing_indices and not cancel_flags.get(uid):
                retry_lines = []
                for idx, txt in chunk:
                    if idx in missing_indices:
                        fb = fallback_short_english_phrases(txt)
                        if fb:
                            lead_tags = extract_leading_ass_tags(txt)
                            subs[idx].text = lead_tags + fb
                        else:
                            stripped_txt = prepare_source_line_for_ai(txt).replace('"', '')
                            retry_lines.append("[" + str(idx) + "] " + stripped_txt)
                if retry_lines:
                    retry_prompt = (
                        core_rules + series_context_block +
                        "CRITICAL: Translate EVERY SINGLE WORD in the lines below into pure, natural spoken Burmese (မြန်မာစာ). "
                        "Keep ONLY personal character names in English. Leave ZERO untranslated English words, NO `?` or `;`, NO novel style, and NO forced fillers. "
                        "Output ONLY `[index] burmese_text`:\n\n" + "\n".join(retry_lines)
                    )
                    try:
                        retry_res = call_gemini_reliable(retry_prompt, uid=uid, timeout_sec=60, temp=0.2)
                        parse_ai_translation_output(retry_res, subs, missing_indices, orig_map, allow_partial_english=True)
                    except Exception as re_err:
                        if "Cancelled by user" in str(re_err):
                            raise

            for idx, orig_raw in chunk:
                orig_clean = prepare_source_line_for_ai(orig_raw)
                trans_clean = re.sub(r"\{[^}]*\}", "", subs[idx].text).strip()
                prev_context.append(f"{orig_clean} => {trans_clean}")
            time.sleep(0.8)

        untranslated_items = []
        for idx, orig_txt in valid_items:
            clean_curr = re.sub(r"\{[^}]*\}", "", subs[idx].text).strip()
            if not re.search(r"[\u1000-\u109F]", clean_curr) or has_leftover_english_words(clean_curr):
                fb = fallback_short_english_phrases(orig_txt)
                if fb:
                    lead_tags = extract_leading_ass_tags(orig_txt)
                    subs[idx].text = lead_tags + fb
                else:
                    untranslated_items.append((idx, orig_txt))

        if untranslated_items and not cancel_flags.get(uid):
            safe_edit(chat_id, msg_id, "🔍 Final QC Sweep: ကျန်ရှိနေသော စာကြောင်း (" + str(len(untranslated_items)) + ") ကြောင်းကို အချောသတ် စစ်ဆေးဘာသာပြန်နေပါသည် (99%)...")
            audit_chunks = [untranslated_items[i:i + 20] for i in range(0, len(untranslated_items), 20)]
            for a_chunk in audit_chunks:
                if cancel_flags.get(uid):
                    break
                a_expected = set(i for i, _ in a_chunk)
                a_lines = ["[" + str(idx) + "] " + prepare_source_line_for_ai(txt).replace('"', '') for idx, txt in a_chunk]
                audit_prompt = (
                    core_rules + series_context_block +
                    "You MUST translate every single line below into 100% pure, natural spoken Myanmar script (မြန်မာစာ). "
                    "Leave ZERO common English words untranslated and NO `?` or `;`. If a line is a single character name, add a natural Burmese particle. "
                    "Output ONLY `[index] translated_burmese_text`:\n\n" + "\n".join(a_lines)
                )
                try:
                    a_res = call_gemini_reliable(audit_prompt, uid=uid, timeout_sec=60, temp=0.2)
                    parse_ai_translation_output(a_res, subs, a_expected, orig_map, allow_partial_english=True)
                except Exception as au_err:
                    if "Cancelled by user" in str(au_err):
                        raise
                time.sleep(0.8)

        subs.save(out_file, encoding="utf-8")
        safe_edit(chat_id, msg_id, "📤 ဘာသာပြန်ပြီးသော ဖိုင်ကို ပို့ပေးနေပါပြီ (100%)...")
        out_basename = os.path.basename(out_file)
        sub_size = format_bytes(os.path.getsize(out_file))
        target_dest = user_settings.get("target_chat") or chat_id
        caption_done = (
            "✅ Gemini 4 Hydrogen Pro Translator ဖြင့် 100% ဘာသာပြန်ပြီးပါပြီ!\n"
            "📄 ဖိုင်: " + out_basename + "\n"
            + series_label +
            "📝 စုစုပေါင်း: " + str(total_lines) + " ကြောင်း\n"
            "💾 Data Size: " + sub_size
        )
        with open(out_file, "rb") as f:
            bot.send_document(target_dest, f, caption=caption_done)
        try:
            bot.delete_message(chat_id, msg_id)
        except Exception:
            pass
    except Exception as e:
        if "Cancelled by user" in str(e):
            safe_edit(chat_id, msg_id, "🛑 ရပ်တန့်လိုက်ပါပြီ။")
        else:
            safe_edit(chat_id, msg_id, "❌ Error: " + repr(e))
    finally:
        if dl_dir:
            shutil.rmtree(dl_dir, ignore_errors=True)
        user_states[uid] = None

if __name__ == "__main__":
    if not BOT_TOKEN:
        print("❌ ERROR: BOT_TOKEN missing.", flush=True)
    else:
        telebot.apihelper.CONNECT_TIMEOUT = 30
        telebot.apihelper.READ_TIMEOUT = 90
        print("Starting Elite Pro Series-Aware Subtitle Bot (Gemini 4 Hydrogen - TeleBot)...", flush=True)
        bot.infinity_polling(timeout=30, long_polling_timeout=20)
