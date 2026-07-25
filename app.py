import os, re, sqlite3, uuid, json, base64, calendar, hashlib
from datetime import datetime, timedelta
from functools import wraps

import cv2
import pytesseract
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, jsonify, send_from_directory)
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

if os.name == "nt":
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:
    pytesseract.pytesseract.tesseract_cmd = "tesseract"

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fisai_secret_2026")

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def sifre_hashle(sifre):
    return hashlib.sha256(sifre.encode("utf-8")).hexdigest()

# Veritabanı

def get_db():
    conn = sqlite3.connect("akillicuzdan.db", timeout=10)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ad              TEXT NOT NULL,
        email           TEXT UNIQUE NOT NULL,
        sifre           TEXT NOT NULL,
         telefon         TEXT DEFAULT '',
        dogum_tarihi    TEXT DEFAULT '',
         meslek          TEXT DEFAULT '',
        aylik_gelir     REAL DEFAULT 0,
        sehir           TEXT DEFAULT '',
        avatar_harf     TEXT DEFAULT '',
        olusturma_tarihi TEXT DEFAULT (datetime('now')),
        bildirim_butce  INTEGER DEFAULT 1,
        bildirim_fatura INTEGER DEFAULT 1,
        maas_yatis_gunu INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS fisler (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL,
        tarih           TEXT,
        saat            TEXT DEFAULT '',
        toplam          REAL DEFAULT 0,
        kdv             REAL DEFAULT 0,
        kdv_orani       TEXT DEFAULT '',
        kategori        TEXT DEFAULT 'Diger',
        magaza          TEXT DEFAULT 'Bilinmiyor',
        vergi_no        TEXT DEFAULT '',
        ocr_text        TEXT DEFAULT '',
        ai_yorum        TEXT DEFAULT '',
        dosya_adi       TEXT DEFAULT '',
        duzeltilmis     INTEGER DEFAULT 0,
        belge_tipi      TEXT DEFAULT 'fis',
        eklenme_tarihi  TEXT DEFAULT (datetime('now')),
        urunler         TEXT DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS butceler (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        kategori    TEXT NOT NULL,
        limit_tl    REAL NOT NULL,
        ay          TEXT NOT NULL,
        UNIQUE(user_id, kategori, ay)
    );

    CREATE TABLE IF NOT EXISTS gelirler (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        tip         TEXT NOT NULL,
        tutar       REAL NOT NULL,
        aciklama    TEXT DEFAULT '',
        tarih       TEXT DEFAULT (date('now')),
        tekrarlayan INTEGER DEFAULT 0,
        tekrar_gunu INTEGER DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS abonelikler (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id         INTEGER NOT NULL,
        ad              TEXT NOT NULL,
        tutar           REAL NOT NULL,
        odeme_gunu      INTEGER NOT NULL,
        kategori        TEXT DEFAULT 'Eglence',
        aktif           INTEGER DEFAULT 1,
        renk            TEXT DEFAULT '#4f46e5'
    );

    CREATE TABLE IF NOT EXISTS sohbet_oturumlari (
        id          TEXT PRIMARY KEY,
        user_id     INTEGER NOT NULL,
        baslik      TEXT DEFAULT 'Yeni Sohbet',
        olusturma_tarihi TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sohbet_mesajlari (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        oturum_id   TEXT NOT NULL,
        user_id     INTEGER NOT NULL,
        rol         TEXT NOT NULL,
        icerik      TEXT NOT NULL,
        tarih       TEXT DEFAULT (datetime('now')),
        FOREIGN KEY (oturum_id) REFERENCES sohbet_oturumlari(id)
    );
    """)

    try:
        c.execute("ALTER TABLE users ADD COLUMN maas_yatis_gunu INTEGER DEFAULT 1")
    except:
        pass
    try:
        c.execute("ALTER TABLE gelirler ADD COLUMN tekrar_gunu INTEGER DEFAULT 1")
    except:
        pass

    conn.commit()
    conn.close()

init_db()

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated

def temizle(text):
    return (text.lower()
            .replace("i̇", "i").replace("ı", "i").replace("ş", "s")
            .replace("ğ", "g").replace("ü", "u").replace("ö", "o").replace("ç", "c"))

KATEGORILER = [
    "Market", "Yeme-İçme", "Teknoloji", "Ulaşım", "Sağlık",
    "Eğitim", "Kıyafet", "Eğlence", "Ev Giderleri", "Faturalar",
    "Abonelikler", "Akaryakıt", "Kozmetik", "Diğer"
]

MAGAZA_MAP = {
    "a101": "A101", "migros": "Migros", "bim": "BİM", "sok": "ŞOK",
    "carrefour": "CarrefourSA", "lcw": "LC Waikiki", "zara": "Zara",
    "starbucks": "Starbucks", "mcdonald": "McDonald's", "burger king": "Burger King",
    "kfc": "KFC", "popeyes": "Popeyes", "pizza hut": "Pizza Hut", "domino": "Domino's",
    "teknosa": "Teknosa", "vatan": "Vatan Bilgisayar", "mediamarkt": "MediaMarkt",
    "opet": "OPET", "shell": "Shell", "bp": "BP", "petrol": "Petrol Ofisi",
    "ptttcargo": "PTT Kargo", "mng": "MNG Kargo", "yurtici": "Yurtiçi Kargo",
    "hepsiburada": "Hepsiburada", "trendyol": "Trendyol", "n11": "N11",
    "gratis": "Gratis", "watsons": "Watsons", "eczane": "Eczane",
    "otogar": "Otogar", "metro": "Metro"
}

def magaza_bul(text):
    t = temizle(text)
    for anahtar, isim in MAGAZA_MAP.items():
        if anahtar in t:
            return isim
    return "Bilinmiyor"

def kategori_bul(text):
    t = temizle(text)
    if any(x in t for x in ["a101", "migros", "bim", "sok", "carrefour", "market", "süt", "peynir", "yoğurt"]):
        return "Market"
    if any(x in t for x in
           ["starbucks", "mcdonald", "burger", "kfc", "popeyes", "pizza", "restoran", "cafe", "lokanta"]):
        return "Yeme-İçme"
    if any(x in t for x in ["teknosa", "vatan", "mediamarkt", "bilgisayar", "telefon", "elektronik"]):
        return "Teknoloji"
    if any(x in t for x in ["opet", "shell", "bp", "petrol", "akaryakit", "benzin"]):
        return "Akaryakıt"
    if any(x in t for x in ["eczane", "hastane", "saglik", "klinik", "ilac"]):
        return "Sağlık"
    if any(x in t for x in ["lcw", "zara", "h&m", "boyner", "kiyafet", "giyim"]):
        return "Kıyafet"
    if any(x in t for x in ["kargo", "mng", "yurtici", "aras"]):
        return "Ulaşım"
    if any(x in t for x in ["gratis", "watsons", "kozmetik", "parfum"]):
        return "Kozmetik"
    if any(x in t for x in ["elektrik", "su faturasi", "dogalgaz", "internet", "fatura"]):
        return "Faturalar"
    return "Diğer"

def belge_tipi_bul(text):
    t = temizle(text)
    if any(x in t for x in ["elektrik", "su faturasi", "dogalgaz", "internet fatura", "telefon fatura"]):
        return "fatura"
    if any(x in t for x in ["e-arsiv", "e arsiv", "e-fatura"]):
        return "fatura"
    return "fis"

def resmi_iyilestir(yol):
    img = cv2.imread(yol)
    if img is None:
        raise Exception("Görsel okunamadı")
    gri = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gri = cv2.bilateralFilter(gri, 9, 75, 75)
    _, thresh = cv2.threshold(gri, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def guvenli_float(deger, varsayilan=0.0):
    if deger is None:
        return varsayilan
    if isinstance(deger, (int, float)):
        return round(float(deger), 2)
    metin = str(deger).strip()
    if not metin:
        return varsayilan
    metin = metin.replace("TL", "").replace("₺", "").replace(" ", "")
    metin = re.sub(r"[^0-9,.-]", "", metin)
    if not metin:
        return varsayilan
    try:
        if "," in metin and "." in metin:

            if metin.rfind(",") > metin.rfind("."):
                metin = metin.replace(".", "").replace(",", ".")

            else:
                metin = metin.replace(",", "")
        elif "," in metin:
            metin = metin.replace(",", ".")
        return round(float(metin), 2)
    except:
        return varsayilan

def tarih_gecerli(t):
    if not t or str(t).lower() == "bulunamadı":
        return False
    try:
        parts = re.split(r"[./-]", str(t).strip())
        if len(parts) == 3:
            day, month, year = int(parts[0]), int(parts[1]), int(parts[2])
            return 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2099
        return False
    except:
        return False

def saat_gecerli(s):
    if not s or str(s).lower() == "bulunamadı":
        return False
    try:
        parts = str(s).strip().split(":")
        if len(parts) >= 2:
            hour, minute = int(parts[0]), int(parts[1])
            return 0 <= hour <= 23 and 0 <= minute <= 59
        return False
    except:
        return False

def normalize_tarih(t):
    if not t:
        return ""
    t = str(t).strip().replace("-", "/").replace(".", "/")
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", t)
    if not m:
        return ""
    gun, ay, yil = int(m.group(1)), int(m.group(2)), int(m.group(3))
    aday = f"{gun:02d}/{ay:02d}/{yil}"
    return aday if tarih_gecerli(aday) else ""

def normalize_saat(s):
    if not s:
        return ""
    m = re.search(r"(\d{1,2}):(\d{2})", str(s))
    if not m:
        return ""
    aday = f"{int(m.group(1)):02d}:{int(m.group(2)):02d}"
    return aday if saat_gecerli(aday) else ""

def json_metnini_ayikla(content):
    if not content:
        raise json.JSONDecodeError("Boş cevap", "", 0)
    metin = content.strip()
    if "```json" in metin:
        metin = metin.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in metin:
        metin = metin.split("```", 1)[1].split("```", 1)[0].strip()
    ilk = metin.find("{")
    son = metin.rfind("}")
    if ilk != -1 and son != -1 and son > ilk:
        metin = metin[ilk:son + 1]
    return json.loads(metin)

def ocr_text_temizle(text):
    if not text:
        return ""
    text = text.replace("\x0c", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    lines = [l.strip() for l in text.splitlines()]
    lines = [l for l in lines if l]
    return "\n".join(lines)

def ocr_guven_hesapla(img, lang="tur+eng", config="--oem 3 --psm 6"):
    try:
        data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)
    except:
        data = pytesseract.image_to_data(img, lang="eng", config=config, output_type=pytesseract.Output.DICT)
    confs = []
    for c in data.get("conf", []):
        try:
            val = float(c)
            if val >= 0:
                confs.append(val)
        except:
            pass
    if not confs:
        return 0
    return round(sum(confs) / len(confs), 1)

#OCR işlemleri burda
def tesseract_ocr_oku(yol):
    img = cv2.imread(yol)
    if img is None:
        raise Exception("Görsel okunamadı")

    h, w = img.shape[:2]
    scale = 2 if max(h, w) < 1800 else 1
    if scale > 1:
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

    variants = []
    variants.append(("gray", gray))

    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, otsu = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(("otsu", otsu))

    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 11
    )
    variants.append(("adaptive", adaptive))

    configs = [
        "--oem 3 --psm 6",
        "--oem 3 --psm 4",
        "--oem 3 --psm 11"
    ]

    sonuclar = []
    for ad, image in variants:
        for config in configs:
            try:
                try:
                    raw_text = pytesseract.image_to_string(image, lang="tur+eng", config=config)
                    conf = ocr_guven_hesapla(image, lang="tur+eng", config=config)
                except:
                    raw_text = pytesseract.image_to_string(image, lang="eng", config=config)
                    conf = ocr_guven_hesapla(image, lang="eng", config=config)

                clean_text = ocr_text_temizle(raw_text)
                if clean_text:
                    skor = (conf * 2) + min(len(clean_text), 3000) / 30
                    sonuclar.append({
                        "variant": ad,
                        "config": config,
                        "text": clean_text,
                        "confidence": conf,
                        "score": skor
                    })
            except Exception:
                continue

    if not sonuclar:
        raise Exception("Tesseract OCR metin çıkaramadı. Tesseract kurulumu ve dil paketlerini kontrol edin.")

    en_iyi = sorted(sonuclar, key=lambda x: x["score"], reverse=True)[0]
    return en_iyi["text"], en_iyi["confidence"], en_iyi["variant"], en_iyi["config"]

def ai_ocr_duzelt_ve_yapilandir(ocr_text, kural_sonuc):
    prompt = f"""
Aşağıda Tesseract OCR ile okunmuş bir Türk fiş/fatura metni var.
Bu metin hatalı olabilir: 0/O, 1/I, 5/S, virgül/nokta, TL sembolü, tarih ve saat formatı hataları olabilir.

GÖREVİN:
1. Sadece OCR metninde bulunan bilgilere dayan.
2. Eksik bilgiyi uydurma. OCR metninde yoksa boş string veya 0 kullan.
3. Mağaza adı, tarih, saat, toplam, KDV, KDV oranı, vergi no, kategori ve ürünleri çıkar.
4. Ürünlerde yalnızca gerçekten ürün satırı gibi görünenleri al; toplam, KDV, nakit, kart, para üstü, provizyon gibi satırları ürün yapma.
5. Ürün satırlarında satır sonundaki *37,00 / X61,25 / 57,00 gibi değer ürünün toplam fiyatıdır. Gramajı veya adet bilgisini fiyat yapma. Örnek: "HOTCORN 130G ... *57,00" => ad HOTCORN 130G, fiyat 57.00.
6. Eğer kural tabanlı ilk ayrıştırma ürün toplamı ile fiş toplamı uyumluysa onu esas al ve gereksiz değişiklik yapma.
7. Tarih formatı gg/aa/yyyy, saat formatı hh:mm olsun.
6. Kategori şu listeden biri olsun: {', '.join(KATEGORILER)}.
7. Sadece geçerli JSON döndür, açıklama yazma.

Kural tabanlı ilk ayrıştırma sonucu:
{kural_sonuc}

HAM OCR METNİ:
{ocr_text[:4000]}

JSON ŞEMASI:
{{
  "tarih": "gg/aa/yyyy veya boş",
  "saat": "hh:mm veya boş",
  "toplam": 0.0,
  "kdv": 0.0,
  "kdv_orani": "%18 veya boş",
  "magaza": "mağaza adı veya Bilinmiyor",
  "vergi_no": "varsa",
  "kategori": "kategori",
  "urunler": [{{"ad": "ürün adı", "fiyat": 0.0}}]
}}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1200,
        temperature=0.1
    )
    return json_metnini_ayikla(response.choices[0].message.content)

def ai_urun_listesi_kurtar(ocr_text, toplam):
    try:
        prompt = f"""
Aşağıdaki metin Tesseract OCR çıktısıdır. Görsel yoktur, sadece OCR metni vardır.
Ürün satırlarını OCR metninden düzeltip çıkar.

Kurallar:
- Sadece ürünleri döndür; TOPLAM, TOPKDV, KDV, KREDİ KARTI, provizyon, banka, tarih, saat satırlarını alma.
- "2 X 18,50" gibi miktar/birim fiyat satırlarını ürün olarak alma.
- Bir ürünün satır sonunda *37,00 / ¥37,00 / #57,00 / %61,25 gibi değer varsa bu ürünün toplam fiyatıdır.
- Gramaj veya ürün kodunu fiyat sanma. Örnek: HOTCORN 130G fiyat değildir; fiyat satır sonundaki 57,00 değeridir.
- OCR karakter hatalarını düzelt: 1306 -> 130G, 1356 -> 135G, 21,56 -> 21,5 G, ALISVERI$ -> ALISVERIS.
- Ürün fiyatları toplamı mümkünse fiş toplamına yakın olsun: {toplam} TL.
- Eksik ürün uydurma; sadece OCR metninde görünen ürünleri al.
- Sadece geçerli JSON array döndür. Açıklama yazma.

OCR METNİ:
{ocr_text[:4000]}

Beklenen format:
[
  {{"ad":"ÜRÜN ADI", "fiyat":37.0}}
]
"""
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=900,
            temperature=0.0
        )
        data = json_metnini_ayikla(response.choices[0].message.content)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("urunler"), list):
            return data.get("urunler")
    except Exception:
        pass
    return []

def ai_ocr_gorsel_destekli_dogrula(yol, ocr_text, kural_sonuc, ai_sonuc=None):
    try:
        with open(yol, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        prompt = f"""
Bu bir OCR SONRASI DOĞRULAMA görevidir.
Sistem önce Tesseract OCR ile aşağıdaki ham metni çıkardı. OCR metninde ürün adları bozulmuş olabilir.
Görseli yalnızca OCR çıktısını doğrulamak ve bozuk ürün satırlarını düzeltmek için kullan.

ÇOK ÖNEMLİ KURALLAR:
1. Eksik ürün uydurma; sadece OCR metninde veya görselde net görünen ürünleri yaz.
2. Ürünlerde satır sonundaki *37,00 / 37,00 / 61,25 gibi değer ürün toplam fiyatıdır.
3. "2 X 18,50", "4 X 5,00", "5 X 12,25" gibi satırlar ürün değildir; bunlar adet x birim fiyat bilgisidir.
4. Gramaj/kod fiyat değildir: 22 G, 21,5 G, 130G, 135G, 301 gibi değerleri fiyat yapma.
5. TOPKDV, TOPLAM, KREDİ KARTI, provizyon, banka, tarih/saat satırlarını ürün yapma.
6. Ürün fiyatları toplamı fiş toplamına mümkün olduğunca eşit olmalı.
7. Tarih gg/aa/yyyy, saat hh:mm olsun.
8. Kategori şu listeden biri olsun: {', '.join(KATEGORILER)}.
9. Sadece geçerli JSON döndür. Açıklama yazma.

Tesseract OCR ham metni:
{ocr_text[:4500]}

Kural tabanlı ilk ayrıştırma:
{kural_sonuc}

İlk AI OCR düzeltme sonucu:
{ai_sonuc or {}}

JSON ŞEMASI:
{{
  "tarih": "gg/aa/yyyy veya boş",
  "saat": "hh:mm veya boş",
  "toplam": 0.0,
  "kdv": 0.0,
  "kdv_orani": "%18 veya boş",
  "magaza": "mağaza adı veya Bilinmiyor",
  "vergi_no": "varsa",
  "kategori": "kategori",
  "belge_tipi": "fis veya fatura",
  "urunler": [{{"ad": "ürün adı", "fiyat": 0.0}}]
}}
"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1600,
            temperature=0.0
        )
        data = json_metnini_ayikla(response.choices[0].message.content)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def analiz_sonucu_daha_guvenilir_sec(klasik, gorsel_destekli):
    if not gorsel_destekli:
        return klasik
    if not klasik:
        return gorsel_destekli

    toplam = guvenli_float(gorsel_destekli.get("toplam"), 0) or guvenli_float(klasik.get("toplam"), 0)
    klasik_urunler = urun_listesi_temizle(klasik.get("urunler", []))
    gorsel_urunler = urun_listesi_temizle(gorsel_destekli.get("urunler", []))

    klasik_fark = abs(urun_toplami(klasik_urunler) - toplam) if toplam else 0
    gorsel_fark = abs(urun_toplami(gorsel_urunler) - toplam) if toplam else 0

    if gorsel_urunler:
        if len(gorsel_urunler) >= len(klasik_urunler) and gorsel_fark <= max(3, toplam * 0.08 if toplam else 3):
            return gorsel_destekli
        if len(klasik_urunler) <= 3 and len(gorsel_urunler) >= 5:
            return gorsel_destekli
        if klasik_fark > max(5, toplam * 0.12 if toplam else 5) and gorsel_fark < klasik_fark:
            return gorsel_destekli

    return klasik

def ai_sonucu_kural_ile_birlestir(ai_sonuc, kural_sonuc, ocr_text):
    ai_sonuc = ai_sonuc or {}
    kural_sonuc = kural_sonuc or {}

    tarih = normalize_tarih(ai_sonuc.get("tarih")) or normalize_tarih(kural_sonuc.get("tarih"))
    saat = normalize_saat(ai_sonuc.get("saat")) or normalize_saat(kural_sonuc.get("saat"))

    toplam = guvenli_float(ai_sonuc.get("toplam"), 0)
    if toplam <= 0:
        toplam = guvenli_float(kural_sonuc.get("toplam"), 0)

    kdv = guvenli_float(ai_sonuc.get("kdv"), 0)
    if kdv <= 0:
        kdv = guvenli_float(kural_sonuc.get("kdv"), 0)

    kdv_orani = str(ai_sonuc.get("kdv_orani") or kural_sonuc.get("kdv_orani") or "").strip()
    if kdv_orani and not kdv_orani.startswith("%") and re.search(r"\d", kdv_orani):
        oran = re.search(r"\d{1,2}", kdv_orani)
        kdv_orani = f"%{oran.group()}" if oran else ""

    magaza = str(ai_sonuc.get("magaza") or "").strip()
    if not magaza or magaza.lower() in ["bilinmiyor", "unknown", "null"]:
        magaza = magaza_bul(ocr_text)
    if not magaza:
        magaza = "Bilinmiyor"

    kategori = str(ai_sonuc.get("kategori") or "").strip()
    if kategori not in KATEGORILER:
        kategori = kategori_bul(ocr_text)
    if kategori not in KATEGORILER or kategori == "Diğer":
        kategori = ai_kategori_bul(ai_sonuc.get("urunler", []), ocr_text)

    belge_tipi = belge_tipi_bul(ocr_text)
    if belge_tipi == "fis":
        belge_tipi = ai_belge_tipi_bul(ocr_text)

    vergi_no = str(ai_sonuc.get("vergi_no") or kural_sonuc.get("vergi_no") or "").strip()

    temiz_urunler = en_guvenilir_urun_listesi_sec(
        ai_sonuc.get("urunler", []),
        kural_sonuc.get("urunler", []),
        toplam
    )

    if toplam and abs(urun_toplami(temiz_urunler) - toplam) > max(5, toplam * 0.10):
        kurtarma_urunleri = urun_listesi_temizle(ai_urun_listesi_kurtar(ocr_text, toplam))
        if kurtarma_urunleri:
            mevcut_fark = abs(urun_toplami(temiz_urunler) - toplam) if temiz_urunler else 999999
            kurtarma_fark = abs(urun_toplami(kurtarma_urunleri) - toplam)
            if kurtarma_fark < mevcut_fark or len(kurtarma_urunleri) > len(temiz_urunler):
                temiz_urunler = kurtarma_urunleri

    return {
        "tarih": tarih,
        "saat": saat,
        "toplam": round(toplam, 2),
        "kdv": round(kdv, 2),
        "kdv_orani": kdv_orani,
        "magaza": magaza,
        "vergi_no": vergi_no,
        "kategori": kategori,
        "belge_tipi": belge_tipi,
        "urunler": temiz_urunler
    }

def urun_adi_temizle(ad):
    if not ad:
        return ""

    ad = str(ad)
    ad = re.sub(r"(\d+),\s+(\d{2})", r"\1,\2", ad)

    ad = re.sub(r"^\s*\d+\s*[xX]\s*\d+[,.]\s*\d{1,2}\s*[^A-Za-zÇĞİÖŞÜçğıöşü0-9]*\s*", "", ad)

    ad = re.sub(r"\b(\d{1,2}),5[6G]\b", r"\1,5 G", ad)

    # KDV kodlarını ayıklama
    ad = re.split(r"\s+[\\/|;:.,\-=]*\s*[#%]?\s*[024]?\s*(?:0[1Iİl]|10|20)\b.*$", ad, maxsplit=1)[0]
    ad = re.split(r"(?<!\d)[xX%#]?[024]?0[1Iİl](?!\d)", ad, maxsplit=1)[0]
    ad = re.split(r"[%#¥₺*\\|=]", ad, maxsplit=1)[0]

    ad = ad.strip(" .;:|/\\'\"“”‘’*xX¥₺%,-_©!°")

    ad = re.sub(r"\b(\d{2,3})6\b", r"\1G", ad)
    ad = re.sub(r"\b(\d{1,3})\s+6\b", r"\1 G", ad)

    ad = ad.replace("$", "S")
    ad = ad.replace("¢", "")

    ad = re.sub(r"[“”‘’\"\\/|_=;:©°!]+", " ", ad)
    ad = re.sub(r"\s+", " ", ad).strip(" .,-")

    ad = re.sub(r"\s+\d$", "", ad).strip()

    ad = re.sub(r"\s+[oO0iİIı]$", "", ad).strip()
    return ad[:80]

def urunleri_kural_tabanli_cek(text):
    if not text:
        return []

    satirlar = []
    for raw in text.splitlines():
        satir = raw.strip()
        if not satir:
            continue
        satir = re.sub(r"(\d+),\s+(\d{2})", r"\1,\2", satir)
        satirlar.append(satir)

    atlanacaklar = [
        "toplam", "toplan", "topkdv", "kdv", "kredi", "kart", "nakit", "para ustu", "paraustu",
        "garanti", "provizyon", "puan", "tarih", "saat", "fis no", "fisno", "fatura no",
          "belge", "etin", "ettn", "tckn", "musteri", "v.d", "vergi", "m.ad", "m.kodu",
        "a101 yeni", "magazacilik", "cavus", "alemdag", "mah", "cad", "e-arsiv", "arsiv",
    "fatura", "bilgi fisi", "tesekkur", "banka", "sube"
    ]

    urunler = []
    gorulen = set()
    onceki_ad_adayi = ""

    para_re = re.compile(r"(?:[xX¥₺*%#]\s*)?[\"'’‘“”]?\s*(\d{1,5}[.,]\s*\d{2})")

    for satir in satirlar:
        satir_norm = temizle(satir)
        satir_bosluk_yok = re.sub(r"\s+", "", satir_norm)

        if re.search(r"\b(topkdv|toplam|toplan|kredi|nakit)\b", satir_norm):
            if urunler:
                break

        if re.fullmatch(r"\d+\s*[xX]\s*\d+[,.]\s*\d{1,2}\s*[^A-Za-zÇĞİÖŞÜçğıöşü0-9]*", satir.strip()):
            continue

        if re.search(r"\b\d{1,2}\s*[./]\s*\d{1,2}\s*[./]\s*\d{2,4}\b", satir):
            continue

        if any(k in satir_norm or k in satir_bosluk_yok for k in atlanacaklar):
            continue

        para_eslesmeleri = list(para_re.finditer(satir))
        if not para_eslesmeleri:
            if re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", satir) and not any(k in satir_norm for k in atlanacaklar):
                onceki_ad_adayi = satir
            continue

        m = para_eslesmeleri[-1]
        fiyat = guvenli_float(m.group(1), 0)
        if not (0 < fiyat < 50000):
            continue

        ad_kismi = satir[:m.start()].strip()

        if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", ad_kismi) and onceki_ad_adayi:
            ad_kismi = onceki_ad_adayi

        ad_kismi = re.sub(r"^\s*\d+\s*[xX]\s*\d+[,.]\s*\d{1,2}\s*[^A-Za-zÇĞİÖŞÜçğıöşü0-9]*\s*", "", ad_kismi)
        if not ad_kismi or re.fullmatch(r"[\d\sXx,\.\-_©|/\\]+", ad_kismi):
            continue

        ad = urun_adi_temizle(ad_kismi)
        ad_norm = temizle(ad)
        if len(ad) < 2 or any(k in ad_norm for k in atlanacaklar):
            continue

        if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]", ad):
            continue

        anahtar = (ad_norm, round(fiyat, 2))
        if anahtar in gorulen:
            continue
        gorulen.add(anahtar)
        urunler.append({"ad": ad, "fiyat": round(fiyat, 2)})
        onceki_ad_adayi = ""

        if len(urunler) >= 60:
            break

    return urunler

def urun_listesi_temizle(urunler):
    temiz_urunler = []
    gorulen = set()
    yasak = [
        "toplam", "kdv", "ara toplam", "aratoplam", "nakit", "kredi", "kart",
        "para ustu", "para üstü", "provizyon", "puan", "tarih", "saat", "belge"
    ]
    for u in urunler or []:
        if not isinstance(u, dict):
            continue
        ad = urun_adi_temizle(str(u.get("ad", "")).strip())
        fiyat = guvenli_float(u.get("fiyat"), 0)
        ad_norm = temizle(ad)
        if len(ad) < 2 or any(y in ad_norm for y in yasak):
            continue
        if 0 < fiyat < 50000:
            key = (ad_norm, round(fiyat, 2))
            if key not in gorulen:
                gorulen.add(key)
                temiz_urunler.append({"ad": ad[:80], "fiyat": round(fiyat, 2)})
        if len(temiz_urunler) >= 60:
            break
    return temiz_urunler

def urun_toplami(urunler):
    return round(sum(guvenli_float(u.get("fiyat"), 0) for u in (urunler or []) if isinstance(u, dict)), 2)

def en_guvenilir_urun_listesi_sec(ai_urunler, kural_urunler, toplam):
    ai_temiz = urun_listesi_temizle(ai_urunler)
    kural_temiz = urun_listesi_temizle(kural_urunler)

    def skor(liste):
        if not liste:
            return -999999
        fark = abs(urun_toplami(liste) - toplam) if toplam else 0
        return -(fark * 100) + min(len(liste), 30)

    if toplam and kural_temiz:
        kural_fark = abs(urun_toplami(kural_temiz) - toplam)
        ai_fark = abs(urun_toplami(ai_temiz) - toplam) if ai_temiz else 999999
        if kural_fark <= 1.0 or kural_fark + 5 < ai_fark:
            return kural_temiz

    return ai_temiz if skor(ai_temiz) >= skor(kural_temiz) else kural_temiz

def ocr_kdv_mantik_notu(toplam, kdv, kdv_orani):
    try:
        if not toplam or not kdv or not kdv_orani:
            return ""
        oran_m = re.search(r"\d{1,2}", str(kdv_orani))
        if not oran_m:
            return ""
        oran = float(oran_m.group())
        beklenen_dahil = round(toplam * oran / (100 + oran), 2)
        if beklenen_dahil > 0 and abs(beklenen_dahil - kdv) > max(5, beklenen_dahil * 0.5):
            return f"\n\nSİSTEM KONTROL NOTU: KDV tutarı OCR/AI tarafından {kdv} TL okunmuştur. %{int(oran)} için toplam tutara göre yaklaşık beklenen dahil KDV {beklenen_dahil} TL olabilir. Bu alan kullanıcı tarafından kontrol edilmelidir."
    except:
        return ""
    return ""

def fis_bilgilerini_cek(text):
    tarih = "Bulunamadı"
    saat = ""
    toplam = 0.0
    kdv = 0.0
    kdv_orani = ""
    vergi_no = ""

    tarih_m = re.search(r"\d{2}[./]\d{2}[./]\d{4}", text)
    if tarih_m:
        tarih = tarih_m.group()

    saat_m = re.search(r"SAAT\s*[:=O0]?\s*(\d{1,2}:\d{2})", text, re.IGNORECASE)
    if not saat_m:
        saat_m = re.search(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", text)
    if saat_m:
        saat = saat_m.group(1) if saat_m.lastindex else saat_m.group()

    vn_m = re.search(r"(?:V\.?D\.?|V\.?N\.?|VERG[İI] NO)\s*[:/\.]?\s*(\d{10,11})", text, re.IGNORECASE)
    if vn_m:
        vergi_no = vn_m.group(1)
    else:
        vn_m = re.search(r"V\.?D\.?\s*[,./]?\s*(\d{10,11})", text, re.IGNORECASE)
        if vn_m:
            vergi_no = vn_m.group(1)

    for satir in text.splitlines():
        satir_duz = re.sub(r"(\d+),\s+(\d{2})", r"\1,\2", satir.strip())
        t = temizle(satir_duz).replace(" ", "")

        if "toplam" in t and "aratoplam" not in t and "topkdv" not in t:
            sayilar = re.findall(r"\d+(?:[.,]\d{1,2})", satir_duz)
            vals = [guvenli_float(s, 0) for s in sayilar]
            vals = [v for v in vals if v > 0]
            if vals:
                toplam = max(vals)

        if "topkdv" in t or ("kdv" in t and "toplam" not in t):
            sayilar = re.findall(r"\d+(?:[.,]\d{1,2})", satir_duz)
            vals = [guvenli_float(s, 0) for s in sayilar]
            vals = [v for v in vals if v > 0]
            if vals:
                kdv = max(vals)

        oranlar = re.findall(r"%\s*\d{1,2}", satir_duz)
        if oranlar:
            temiz_oranlar = ["%" + re.search(r"\d{1,2}", o).group() for o in oranlar if re.search(r"\d{1,2}", o)]
            if temiz_oranlar:
                mevcut = set([x.strip() for x in kdv_orani.split(",") if x.strip()])
                mevcut.update(temiz_oranlar)
                kdv_orani = ", ".join(sorted(mevcut))

    urunler = urunleri_kural_tabanli_cek(text)

    return {
        "tarih": tarih,
        "saat": saat,
        "toplam": round(toplam, 2),
        "kdv": round(kdv, 2),
        "kdv_orani": kdv_orani,
        "vergi_no": vergi_no,
        "urunler": urunler
    }

def ai_kategori_bul(urunler, ocr_text=""):
    urun_listesi = ", ".join([u['ad'] for u in urunler if u.get('ad')]) if urunler else "Bilinmiyor"

    prompt = f"""Aşağıdaki ürünleri ve/veya fiş metnini inceleyerek en uygun TEK bir kategori belirle.
Kategoriler: Market, Yeme-İçme, Teknoloji, Ulaşım, Sağlık, Eğitim, Kıyafet, Eğlence, Ev Giderleri, Faturalar, Abonelikler, Akaryakıt, Kozmetik, Diğer.

Ürünler: {urun_listesi}
Fiş Metni (ilk 500 karakter): {ocr_text[:500]}

Sadece kategori adını döndür, başka bir şey yazma."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=20,
            temperature=0.2
        )
        kategori = response.choices[0].message.content.strip()
        for k in KATEGORILER:
            if k.lower() == kategori.lower():
                return k
        return "Diğer"
    except:
        return "Diğer"

def ai_belge_tipi_bul(ocr_text):
    prompt = f"""Aşağıdaki metin bir fiş mi, fatura mı?
Sadece "fis" veya "fatura" yaz.

Metin:
{ocr_text[:500]}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0.1
        )
        tip = response.choices[0].message.content.strip().lower()
        if "fatura" in tip:
            return "fatura"
        else:
            return "fis"
    except:
        return "fis"

def ai_fis_analizi(ocr_text, kategori, toplam):
    prompt = f"""Sen deneyimli bir kişisel finans danışmanısın.
Aşağıdaki OCR ile okunmuş fiş/fatura metnini analiz et.

KATEGORİ: {kategori}
TOPLAM TUTAR: {toplam} TL

Analiz kuralları:
- Harcama özetini çıkar
- Dikkat çeken noktaları belirt
- Tasarruf önerisi ver
- OCR hatalarını tespit et
- Finansal sağlık puanı ver (0-100)
- Gereksiz harcama var mı?

Cevabı SADECE bu formatta yaz:

HARCAMA_OZETI: [özet]

DIKKAT_CEKENLER:
- [madde 1]
- [madde 2]

TASARRUF_ONERISI: [öneri]

OCR_HATALARI: [tespit edilen hatalar veya "Belirgin hata bulunamadı"]

PUAN: [0-100 arası sayı]

GENEL_DEGERLENDIRME: [kısa değerlendirme]

Fiş metni:
{ocr_text[:3000]}"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"HARCAMA_OZETI: AI analizi şu an kullanılamıyor.\nPUAN: 50\nGENEL_DEGERLENDIRME: Lütfen API anahtarınızı kontrol edin. Hata: {str(e)}"

def format_ai_yorum(raw):
    raw = raw.replace("HARCAMA_OZETI:", '<span class="ai-tag tag-blue">📊 Harcama Özeti</span>')
    raw = raw.replace("DIKKAT_CEKENLER:", '<span class="ai-tag tag-yellow">⚠️ Dikkat Çekenler</span>')
    raw = raw.replace("TASARRUF_ONERISI:", '<span class="ai-tag tag-green">💰 Tasarruf Önerisi</span>')
    raw = raw.replace("OCR_HATALARI:", '<span class="ai-tag tag-purple">🔍 OCR Hata Kontrolü</span>')
    raw = raw.replace("PUAN:", '<span class="ai-tag tag-orange">🏆 Finansal Puan</span>')
    raw = raw.replace("GENEL_DEGERLENDIRME:", '<span class="ai-tag tag-blue">⭐ Genel Değerlendirme</span>')
    return raw

def oturum_olustur(user_id):
    """Yeni bir sohbet oturumu oluşturur, maksimum 10 oturumu geçerse en eskisini siler."""
    conn = get_db()

    count = conn.execute("SELECT COUNT(*) FROM sohbet_oturumlari WHERE user_id=?", (user_id,)).fetchone()[0]
    if count >= 10:

        oldest = conn.execute(
            "SELECT id FROM sohbet_oturumlari WHERE user_id=? ORDER BY olusturma_tarihi ASC LIMIT 1",
            (user_id,)
        ).fetchone()
        if oldest:
            conn.execute("DELETE FROM sohbet_mesajlari WHERE oturum_id=?", (oldest["id"],))
            conn.execute("DELETE FROM sohbet_oturumlari WHERE id=?", (oldest["id"],))

    yeni_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO sohbet_oturumlari (id, user_id, baslik) VALUES (?, ?, ?)",
        (yeni_id, user_id, "Yeni Sohbet")
    )
    conn.commit()
    conn.close()
    return yeni_id

def oturum_baslik_guncelle(oturum_id, ilk_mesaj):
    baslik = ilk_mesaj[:30].strip()
    if not baslik:
        baslik = "Yeni Sohbet"
    conn = get_db()
    conn.execute("UPDATE sohbet_oturumlari SET baslik=? WHERE id=?", (baslik, oturum_id))
    conn.commit()
    conn.close()

def ai_asistan_yanit(user_id, soru, oturum_id=None):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT ad, aylik_gelir FROM users WHERE id=?", (user_id,))
    u = c.fetchone()

    c.execute("""
        SELECT tarih, magaza, kategori, toplam, kdv
        FROM fisler WHERE user_id=? ORDER BY id DESC LIMIT 30
    """, (user_id,))
    fisler = c.fetchall()

    c.execute("SELECT tip, tutar, tarih FROM gelirler WHERE user_id=? ORDER BY tarih DESC LIMIT 10", (user_id,))
    gelirler = c.fetchall()

    if oturum_id:
        c.execute(
            "SELECT rol, icerik FROM sohbet_mesajlari WHERE oturum_id=? AND user_id=? ORDER BY id DESC LIMIT 10",
            (oturum_id, user_id)
        )
        gecmis = list(reversed(c.fetchall()))
    else:
        gecmis = []

    conn.close()

    fis_ozet = "\n".join([f"- {f['tarih']} | {f['magaza']} | {f['kategori']} | {f['toplam']} TL" for f in fisler])
    gelir_ozet = "\n".join([f"- {g['tip']}: {g['tutar']} TL ({g['tarih']})" for g in gelirler])

    toplam_gelir = sum(g["tutar"] for g in gelirler)
    toplam_harcama = sum(f["toplam"] for f in fisler)
    if toplam_gelir > 0:
        oran = toplam_harcama / toplam_gelir
        if oran < 0.5:
            skor = 90
        elif oran < 0.7:
            skor = 75
        elif oran < 0.9:
            skor = 55
        else:
            skor = 30
    else:
        skor = 50

    sistem = f"""Sen AkıllıCüzdan'ın akıllı finans asistanısın. Kullanıcı: {u['ad'] if u else 'Kullanıcı'}.
Aylık gelir: {u['aylik_gelir'] if u else 0} TL.
Finansal sağlık skoru: {skor}/100

Son fiş/faturalar:
{fis_ozet if fis_ozet else "Henüz kayıt yok."}

Gelirler:
{gelir_ozet if gelir_ozet else "Henüz gelir kaydı yok."}

Kullanıcının finansal durumu hakkında kısa, net, Türkçe yanıtlar ver.
Sayısal verilerle destekle. Emoji kullan ama abartma.
Gerektiğinde finansal sağlık skorundan bahset.
Tavsiyelerini kullanıcının gerçek verilerine dayandır."""

    messages = [{"role": "system", "content": sistem}]
    for g in gecmis:
        messages.append({"role": g["rol"], "content": g["icerik"]})
    messages.append({"role": "user", "content": soru})

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini", messages=messages, max_tokens=600
        )
        return resp.choices[0].message.content
    except Exception as e:
        return f"Asistan şu an yanıt veremiyor: {str(e)}"

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    hata = None
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        sifre_girilen = request.form.get("sifre", "")
        sifre_hash = sifre_hashle(sifre_girilen)
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()

        if not user:
            conn.close()
            hata = "Bu e-posta ile kayıtlı hesap bulunamadı."
        elif user["sifre"] != sifre_hash and user["sifre"] != sifre_girilen:
            conn.close()
            hata = "Şifre hatalı."
        else:
            if user["sifre"] == sifre_girilen:
                conn.execute("UPDATE users SET sifre=? WHERE id=?", (sifre_hash, user["id"]))
                conn.commit()
            conn.close()
            session["user_id"] = user["id"]
            session["user_name"] = user["ad"]
            session["user_email"] = user["email"]
            return redirect("/dashboard")
    return render_template("login.html", hata=hata)

@app.route("/register", methods=["GET", "POST"])
def register():
    hata = None
    if request.method == "POST":
        ad = request.form.get("ad", "").strip()
        email = request.form.get("email", "").strip()
        sifre = request.form.get("sifre", "")
        sifre2 = request.form.get("sifre_tekrar", "")
        telefon = request.form.get("telefon", "").strip()
        dogum = request.form.get("dogum_tarihi", "").strip()
        meslek = request.form.get("meslek", "").strip()
        sehir = request.form.get("sehir", "").strip()

        if len(ad) < 2:
            hata = "Ad Soyad en az 2 karakter olmalıdır."
        elif "@" not in email:
            hata = "Geçerli bir e-posta girin."
        elif sifre != sifre2:
            hata = "Şifreler eşleşmiyor."
        elif len(sifre) < 6:
            hata = "Şifre en az 6 karakter olmalıdır."
        elif not any(c.isdigit() for c in sifre):
            hata = "Şifre en az 1 rakam içermelidir."
        else:
            try:
                sifre_kayit = sifre_hashle(sifre)
                conn = get_db()
                conn.execute("""
                    INSERT INTO users(ad,email,sifre,telefon,dogum_tarihi,meslek,sehir,avatar_harf)
                    VALUES(?,?,?,?,?,?,?,?)
                """, (ad, email, sifre_kayit, telefon, dogum, meslek, sehir, ad[0].upper()))
                conn.commit()
                conn.close()
                return redirect("/login")
            except sqlite3.IntegrityError:
                hata = "Bu e-posta zaten kayıtlı."
            except Exception as e:
                hata = f"Kayıt hatası: {e}"
    return render_template("register.html", hata=hata)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard")
@login_required
def dashboard():
    uid = session["user_id"]
    conn = get_db()

    toplam_fis = conn.execute("SELECT COUNT(*) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]

    fis_toplam = conn.execute("SELECT COALESCE(SUM(toplam),0) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]

    abone_toplam = \
    conn.execute("SELECT COALESCE(SUM(tutar),0) FROM abonelikler WHERE user_id=? AND aktif=1", (uid,)).fetchone()[0]

    toplam_harcama = fis_toplam + abone_toplam

    toplam_kdv = conn.execute("SELECT COALESCE(SUM(kdv),0) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]

    ay_str = datetime.now().strftime("%m/%Y")
    ay_harcama_fis = conn.execute(
        "SELECT COALESCE(SUM(toplam),0) FROM fisler WHERE user_id=? AND tarih LIKE ?",
        (uid, f"%{ay_str}%")
    ).fetchone()[0]

    ay_harcama = ay_harcama_fis + abone_toplam

    toplam_gelir = conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM gelirler WHERE user_id=?", (uid,)
    ).fetchone()[0]

    kalan_para = toplam_gelir - ay_harcama

    kat_verileri = conn.execute(
        "SELECT kategori, COUNT(*), SUM(toplam) FROM fisler WHERE user_id=? GROUP BY kategori",
        (uid,)
    ).fetchall()

    son_fisler = conn.execute(
        "SELECT * FROM fisler WHERE user_id=? ORDER BY id DESC LIMIT 5", (uid,)
    ).fetchall()

    bugun = datetime.now().day
    abonelikler_rows = conn.execute(
        "SELECT * FROM abonelikler WHERE user_id=? AND aktif=1", (uid,)
    ).fetchall()
    yaklasan_abonelikler = []
    for a in abonelikler_rows:
        kalan = a["odeme_gunu"] - bugun
        if 0 <= kalan <= 7:
            yaklasan_abonelikler.append({"ad": a["ad"], "tutar": a["tutar"], "kalan": kalan})

    conn.close()

    return render_template("dashboard.html",
                           toplam_fis=toplam_fis,
                           toplam_harcama=round(toplam_harcama, 2),
                           toplam_kdv=round(toplam_kdv, 2),
                           ay_harcama=round(ay_harcama, 2),
                           ay_str=ay_str,
                           kalan_para=round(kalan_para, 2),
                           toplam_gelir=round(toplam_gelir, 2),
                           kat_verileri=kat_verileri,
                           son_fisler=son_fisler,
                           yaklasan_abonelikler=yaklasan_abonelikler,
                           analiz=session.get("analiz"),
                           ocr_text=session.get("ocr_text"),
                           ai_yorum=session.get("ai_yorum"),
                           hata=session.pop("hata", None)
                           )

PENDING_DIR = os.path.join("uploads", "_pending")

def urunleri_form_textine_cevir(urunler):
    satirlar = []
    for u in urunler or []:
        ad = str(u.get("ad", "")).strip()
        fiyat = guvenli_float(u.get("fiyat", 0), 0)
        if ad:
            satirlar.append(f"{ad} | {fiyat:.2f}")
    return "\n".join(satirlar)

def urun_textini_listeye_cevir(urunler_text):
    urunler = []
    for satir in (urunler_text or "").splitlines():
        satir = satir.strip()
        if not satir:
            continue

        ad, fiyat = satir, 0.0
        ayirici_bulundu = False
        for ayirici in ["|", ":", " - "]:
            if ayirici in satir:
                sol, sag = satir.rsplit(ayirici, 1)
                ad = sol.strip()
                fiyat = guvenli_float(sag.strip(), 0)
                ayirici_bulundu = True
                break

        if not ayirici_bulundu:
            m = re.search(r"(.+?)\s+(\d+[\.,]\d{1,2}|\d+)$", satir)
            if m:
                ad = m.group(1).strip()
                fiyat = guvenli_float(m.group(2), 0)

        if ad:
            urunler.append({"ad": ad, "fiyat": round(float(fiyat), 2)})
    return urunler

def pending_id_guvenli_mi(pid):
    return bool(pid and re.match(r"^[a-f0-9\-]{32,40}$", str(pid)))

def pending_fis_kaydet(veri):
    os.makedirs(PENDING_DIR, exist_ok=True)
    pid = str(uuid.uuid4())
    yol = os.path.join(PENDING_DIR, f"{pid}.json")
    with open(yol, "w", encoding="utf-8") as f:
        json.dump(veri, f, ensure_ascii=False, indent=2)
    return pid

def pending_fis_oku(pid):
    if not pending_id_guvenli_mi(pid):
        return None
    yol = os.path.join(PENDING_DIR, f"{pid}.json")
    if not os.path.exists(yol):
        return None
    try:
        with open(yol, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def pending_fis_sil(pid):
    if not pending_id_guvenli_mi(pid):
        return
    yol = os.path.join(PENDING_DIR, f"{pid}.json")
    try:
        if os.path.exists(yol):
            os.remove(yol)
    except Exception:
        pass

def benzer_fisleri_bul(user_id, magaza, tarih, toplam):
    toplam = guvenli_float(toplam, 0)
    if toplam <= 0:
        return []

    conn = get_db()
    rows = conn.execute("""
        SELECT id, magaza, tarih, toplam, kategori, eklenme_tarihi
        FROM fisler
        WHERE user_id=?
          AND tarih=?
          AND toplam BETWEEN ? AND ?
        ORDER BY id DESC
        LIMIT 10
    """, (user_id, tarih, round(toplam - 0.05, 2), round(toplam + 0.05, 2))).fetchall()
    conn.close()

    magaza_norm = temizle(magaza or "")
    sonuc = []
    for r in rows:
        kayit_magaza_norm = temizle(r["magaza"] or "")
        magaza_benzer = False
        if magaza_norm and kayit_magaza_norm:
            magaza_benzer = magaza_norm in kayit_magaza_norm or kayit_magaza_norm in magaza_norm
        if magaza_benzer or magaza_norm in ["bilinmiyor", ""]:
            sonuc.append(dict(r))
    return sonuc

@app.route("/uploads/<path:filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory("uploads", filename)

@app.route("/upload", methods=["POST"])
@login_required
def upload():
    f = request.files.get("receipt")
    if not f or f.filename == "":
        session["hata"] = "Dosya seçilmedi."
        return redirect("/dashboard")

    os.makedirs("uploads", exist_ok=True)
    uzanti = os.path.splitext(f.filename)[1].lower()
    if uzanti not in [".png", ".jpg", ".jpeg", ".webp", ".bmp"]:
        session["hata"] = "Lütfen PNG, JPG, JPEG, WEBP veya BMP formatında bir fiş görseli yükleyin."
        return redirect("/dashboard")

    dosya_adi = f"{uuid.uuid4()}{uzanti if uzanti else '.png'}"
    yol = os.path.join("uploads", dosya_adi)
    f.save(yol)

    try:
        ham_ocr_text, ocr_guven, ocr_variant, ocr_config = tesseract_ocr_oku(yol)
        if not ham_ocr_text or len(ham_ocr_text.strip()) < 10:
            session["hata"] = "OCR fişten yeterli metin çıkaramadı. Daha net, gölgesiz ve düz çekilmiş bir görsel deneyin."
            return redirect("/dashboard")

        kural_sonuc = fis_bilgilerini_cek(ham_ocr_text)

        try:
            ai_json = ai_ocr_duzelt_ve_yapilandir(ham_ocr_text, kural_sonuc)
        except Exception:
            ai_json = {}

        analiz_ocr_only = ai_sonucu_kural_ile_birlestir(ai_json, kural_sonuc, ham_ocr_text)

        # Zor fişlerde ai desteği
        vision_json = ai_ocr_gorsel_destekli_dogrula(yol, ham_ocr_text, kural_sonuc, ai_json)
        analiz_vision = ai_sonucu_kural_ile_birlestir(vision_json, kural_sonuc, ham_ocr_text) if vision_json else {}
        analiz_sonuc = analiz_sonucu_daha_guvenilir_sec(analiz_ocr_only, analiz_vision)

        tarih = analiz_sonuc["tarih"]
        saat = analiz_sonuc["saat"]
        toplam = analiz_sonuc["toplam"]
        kdv = analiz_sonuc["kdv"]
        kdv_orani = analiz_sonuc["kdv_orani"]
        magaza = analiz_sonuc["magaza"]
        kategori = analiz_sonuc["kategori"]
        vergi_no = analiz_sonuc["vergi_no"]
        belge_tipi = analiz_sonuc["belge_tipi"]
        urunler = analiz_sonuc["urunler"]

        ocr_text = (
            f"OCR MOTORU: Tesseract\n"
            f"OCR GÜVEN SKORU: %{ocr_guven}\n"
            f"ÖN İŞLEME: {ocr_variant}\n"
            f"TESSERACT CONFIG: {ocr_config}\n"
            f"AI KATMANI: Ham OCR metni üzerinden düzeltme ve yapılandırma\n"
            f"--- HAM OCR METNİ ---\n{ham_ocr_text}"
        )

        kdv_notu = ocr_kdv_mantik_notu(toplam, kdv, kdv_orani)
        ai_raw = ai_fis_analizi(ocr_text + kdv_notu, kategori, toplam)
        ai_html = format_ai_yorum(ai_raw)

        pending_data = {
            "tarih": tarih,
            "saat": saat,
            "toplam": toplam,
            "kdv": kdv,
            "kdv_orani": kdv_orani if kdv_orani else "",
            "kategori": kategori,
            "magaza": magaza,
            "vergi_no": vergi_no,
            "belge_tipi": belge_tipi,
            "urunler": urunler,
            "ocr_text": ocr_text,
            "ai_yorum": ai_html,
            "dosya_adi": dosya_adi,
            "ocr_guven": ocr_guven,
            "islem_notu": "Tesseract OCR + kural tabanlı ayrıştırma + AI destekli düzeltme/doğrulama"
        }

        pending_id = pending_fis_kaydet(pending_data)
        session["pending_fis_id"] = pending_id
        return redirect(url_for("fis_dogrula", pid=pending_id))

    except Exception as e:
        session["hata"] = f"OCR işleme hatası: {str(e)}"
        return redirect("/dashboard")

@app.route("/fis-dogrula", methods=["GET"])
@login_required
def fis_dogrula():
    pid = request.args.get("pid") or session.get("pending_fis_id")
    pending = pending_fis_oku(pid)
    if not pending:
        flash("Doğrulanacak fiş bulunamadı. Lütfen fişi tekrar yükleyin.", "error")
        return redirect("/dashboard")

    duplicates = benzer_fisleri_bul(
        session["user_id"],
        pending.get("magaza", ""),
        pending.get("tarih", ""),
        pending.get("toplam", 0)
    )

    return render_template(
        "fis_dogrula.html",
        pending=pending,
        pending_id=pid,
        duplicates=duplicates,
        kategoriler=KATEGORILER,
        urunler_text=urunleri_form_textine_cevir(pending.get("urunler", []))
    )

@app.route("/fis-dogrula/kaydet", methods=["POST"])
@login_required
def fis_dogrula_kaydet():
    pid = request.form.get("pending_id") or session.get("pending_fis_id")
    pending = pending_fis_oku(pid)
    if not pending:
        flash("Doğrulanacak fiş bulunamadı. Lütfen fişi tekrar yükleyin.", "error")
        return redirect("/dashboard")

    tarih = request.form.get("tarih", pending.get("tarih", ""))
    saat = request.form.get("saat", pending.get("saat", ""))
    toplam = guvenli_float(request.form.get("toplam"), pending.get("toplam", 0))
    kdv = guvenli_float(request.form.get("kdv"), pending.get("kdv", 0))
    kdv_orani = request.form.get("kdv_orani", pending.get("kdv_orani", ""))
    kategori = request.form.get("kategori", pending.get("kategori", "Diğer"))
    magaza = request.form.get("magaza", pending.get("magaza", "Bilinmiyor"))
    vergi_no = request.form.get("vergi_no", pending.get("vergi_no", ""))
    belge_tipi = request.form.get("belge_tipi", pending.get("belge_tipi", "fis"))
    urunler = urun_textini_listeye_cevir(request.form.get("urunler_text", ""))

    conn = get_db()
    cur = conn.execute("""
        INSERT INTO fisler(user_id,tarih,saat,toplam,kdv,kdv_orani,kategori,magaza,
                           vergi_no,ocr_text,ai_yorum,dosya_adi,belge_tipi,urunler,duzeltilmis)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        session["user_id"], tarih, saat, toplam, kdv, kdv_orani,
        kategori, magaza, vergi_no,
        pending.get("ocr_text", ""), pending.get("ai_yorum", ""),
        pending.get("dosya_adi", ""), belge_tipi,
        json.dumps(urunler, ensure_ascii=False), 1
    ))
    conn.commit()
    yeni_id = cur.lastrowid
    conn.close()

    pending_fis_sil(pid)
    session.pop("pending_fis_id", None)
    session["ocr_text"] = pending.get("ocr_text", "")
    session["ai_yorum"] = pending.get("ai_yorum", "")
    session["analiz"] = {
        "tarih": tarih,
        "saat": saat,
        "toplam": toplam,
        "kdv": kdv,
        "kdv_orani": kdv_orani,
        "kategori": kategori,
        "magaza": magaza,
        "belge_tipi": belge_tipi,
        "urunler": urunler
    }

    flash("✅ Fiş doğrulandı ve kaydedildi.", "success")
    return redirect(url_for("receipt_detail", fid=yeni_id))

@app.route("/fis-dogrula/iptal", methods=["POST"])
@login_required
def fis_dogrula_iptal():
    pid = request.form.get("pending_id") or session.get("pending_fis_id")
    pending_fis_sil(pid)
    session.pop("pending_fis_id", None)
    flash("Fiş doğrulama işlemi iptal edildi. Veritabanına kayıt yapılmadı.", "success")
    return redirect("/dashboard")

@app.route("/clear_dashboard")
@login_required
def clear_dashboard():
    for k in ["ocr_text", "analiz", "ai_yorum"]:
        session.pop(k, None)
    return redirect("/dashboard")

@app.route("/manuel-ekle", methods=["GET", "POST"])
@login_required
def manuel_ekle():
    if request.method == "POST":
        tarih = request.form.get("tarih", datetime.now().strftime("%d/%m/%Y"))
        saat = request.form.get("saat", "")
        toplam = float(request.form.get("toplam", 0))
        kdv = float(request.form.get("kdv", 0))
        kdv_orani = request.form.get("kdv_orani", "")
        kategori = request.form.get("kategori", "Diğer")
        magaza = request.form.get("magaza", "Bilinmiyor")
        vergi_no = request.form.get("vergi_no", "")
        belge_tipi = request.form.get("belge_tipi", "fis")
        urunler_text = request.form.get("urunler", "")

        urunler = []
        if urunler_text.strip():
            for satir in urunler_text.strip().splitlines():
                if ":" in satir:
                    ad, fiyat_str = satir.split(":", 1)
                    try:
                        fiyat = float(fiyat_str.strip().replace(",", "."))
                        urunler.append({"ad": ad.strip(), "fiyat": fiyat})
                    except:
                        urunler.append({"ad": satir.strip(), "fiyat": 0})

        conn = get_db()
        conn.execute("""
            INSERT INTO fisler(user_id, tarih, saat, toplam, kdv, kdv_orani,
                               kategori, magaza, vergi_no, belge_tipi, urunler,
                               ocr_text, ai_yorum, dosya_adi)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            session["user_id"], tarih, saat, toplam, kdv, kdv_orani,
            kategori, magaza, vergi_no, belge_tipi,
            json.dumps(urunler, ensure_ascii=False),
            "Manuel giriş", "Manuel eklendi", ""
        ))
        conn.commit()
        conn.close()
        flash("✅ Fiş manuel olarak eklendi.", "success")
        return redirect("/receipts")

    return render_template("manuel_ekle.html", kategoriler=KATEGORILER)

@app.route("/receipts")
@login_required
def receipts():
    uid = session["user_id"]
    magaza = request.args.get("magaza", "")
    kategori = request.args.get("kategori", "")
    tarih = request.args.get("tarih", "")
    belge = request.args.get("belge", "")
    siralama = request.args.get("siralama", "yeni")

    sql = "SELECT * FROM fisler WHERE user_id=?"
    params = [uid]
    if magaza:   sql += " AND magaza LIKE ?";   params.append(f"%{magaza}%")
    if kategori: sql += " AND kategori=?";       params.append(kategori)
    if tarih:    sql += " AND tarih=?";          params.append(tarih)
    if belge:    sql += " AND belge_tipi=?";     params.append(belge)

    if siralama == "yeni":
        sql += " ORDER BY id DESC"
    elif siralama == "eski":
        sql += " ORDER BY id ASC"
    elif siralama == "tutar_yuksek":
        sql += " ORDER BY toplam DESC"
    elif siralama == "tutar_dusuk":
        sql += " ORDER BY toplam ASC"
    else:
        sql += " ORDER BY id DESC"

    conn = get_db()
    fisler = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template("receipts.html", fisler=fisler, kategoriler=KATEGORILER,
                           req_args=request.args)

@app.route("/receipt/<int:fid>")
@login_required
def receipt_detail(fid):
    conn = get_db()
    fis = conn.execute("SELECT * FROM fisler WHERE id=? AND user_id=?",
                       (fid, session["user_id"])).fetchone()
    conn.close()
    if not fis:
        return redirect("/receipts")
    urunler = json.loads(fis["urunler"]) if fis["urunler"] else []
    return render_template("receipt_detail.html", fis=fis, urunler=urunler)

@app.route("/edit/<int:fid>", methods=["GET", "POST"])
@login_required
def edit_receipt(fid):
    conn = get_db()
    if request.method == "POST":
        conn.execute("""
            UPDATE fisler SET tarih=?,toplam=?,kategori=?,magaza=?,kdv=?,duzeltilmis=1
            WHERE id=? AND user_id=?
        """, (
            request.form["tarih"], request.form["toplam"],
            request.form["kategori"], request.form["magaza"],
            request.form.get("kdv", 0),
            fid, session["user_id"]
        ))
        conn.commit()
        conn.close()
        flash("✅ Fiş güncellendi.", "success")
        return redirect("/receipts")
    fis = conn.execute("SELECT * FROM fisler WHERE id=? AND user_id=?",
                       (fid, session["user_id"])).fetchone()
    conn.close()
    return render_template("edit.html", fis=fis, kategoriler=KATEGORILER)

@app.route("/delete/<int:fid>")
@login_required
def delete_receipt(fid):
    conn = get_db()
    conn.execute("DELETE FROM fisler WHERE id=? AND user_id=?", (fid, session["user_id"]))
    conn.commit()
    conn.close()
    flash("🗑️ Fiş silindi.", "success")
    return redirect("/receipts")

@app.route("/delete_all")
@login_required
def delete_all():
    conn = get_db()
    conn.execute("DELETE FROM fisler WHERE user_id=?", (session["user_id"],))
    conn.commit()
    conn.close()
    flash("🗑️ Tüm geçmiş temizlendi.", "success")
    return redirect("/receipts")

@app.route("/reports")
@login_required
def reports():
    uid = session["user_id"]
    conn = get_db()

    toplam_fis = conn.execute("SELECT COUNT(*) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]
    fis_toplam = conn.execute("SELECT COALESCE(SUM(toplam),0) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]
    abone_toplam = \
    conn.execute("SELECT COALESCE(SUM(tutar),0) FROM abonelikler WHERE user_id=? AND aktif=1", (uid,)).fetchone()[0]
    toplam_harcama = fis_toplam + abone_toplam
    toplam_kdv = conn.execute("SELECT COALESCE(SUM(kdv),0) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]
    en_buyuk = conn.execute("SELECT COALESCE(MAX(toplam),0) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]
    ortalama = round(toplam_harcama / toplam_fis, 2) if toplam_fis else 0

    kat_harcama = conn.execute("""
        SELECT kategori, COUNT(*) as sayi, COALESCE(SUM(toplam),0) as tutar
        FROM fisler WHERE user_id=? GROUP BY kategori ORDER BY tutar DESC
    """, (uid,)).fetchall()

    magazalar = conn.execute("""
        SELECT magaza, COUNT(*) as sayi, COALESCE(SUM(toplam),0) as tutar
        FROM fisler WHERE user_id=? GROUP BY magaza ORDER BY sayi DESC LIMIT 8
    """, (uid,)).fetchall()

    son_fisler = conn.execute("""
        SELECT tarih,magaza,kategori,toplam,kdv FROM fisler
        WHERE user_id=? ORDER BY id DESC LIMIT 10
    """, (uid,)).fetchall()

    aylik_gelir_gider = []
    for i in range(9, -1, -1):
        ay_str = (datetime.now().replace(day=1) - timedelta(days=i * 30)).strftime("%Y-%m")
        gelir_ay = conn.execute(
            "SELECT COALESCE(SUM(tutar),0) FROM gelirler WHERE user_id=? AND substr(tarih,1,7)=?",
            (uid, ay_str)
        ).fetchone()[0]
        gider_ay_fis = conn.execute(
            "SELECT COALESCE(SUM(toplam),0) FROM fisler WHERE user_id=? AND substr(eklenme_tarihi,1,7)=?",
            (uid, ay_str)
        ).fetchone()[0]

        gider_ay = gider_ay_fis + abone_toplam

        aylik_gelir_gider.append({
            "ay": ay_str,
            "gelir": round(gelir_ay, 2),
            "gider": round(gider_ay, 2)
        })

    toplam_gelir = conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM gelirler WHERE user_id=?", (uid,)
    ).fetchone()[0]

    en_kategori = kat_harcama[0] if kat_harcama else None
    kategori_adi = en_kategori["kategori"] if en_kategori else "Yok"
    kategori_tutari = round(en_kategori["tutar"], 2) if en_kategori else 0

    tasarruf_oran = {"Market": 0.05, "Yeme-İçme": 0.10, "Teknoloji": 0.15, "Akaryakıt": 0.08}
    oran = tasarruf_oran.get(kategori_adi, 0.07)
    tasarruf_tutari = round(kategori_tutari * oran, 2)

    yorumlar = []
    if en_kategori:
        yorumlar.append(f"{kategori_adi} kategorisi bu dönemin en yüksek harcama kalemi.")
    if magazalar:
        yorumlar.append(f"En sık alışveriş: {magazalar[0]['magaza']} ({magazalar[0]['sayi']} kez).")
    if ortalama > 500:
        yorumlar.append("Ortalama fiş tutarınız yüksek — planlı alışveriş önerilir.")
    elif ortalama < 100:
        yorumlar.append("Ortalama fiş tutarınız kontrollü görünüyor. 👍")
    kalan = round(toplam_gelir - toplam_harcama, 2)
    if toplam_gelir > 0:
        yorumlar.append(f"Gelir-Gider dengesi: {kalan} TL net {'fazlanız' if kalan >= 0 else 'açığınız'} var.")
    # Abonelik hatırlatması
    if abone_toplam > 0:
        yorumlar.append(f"📅 Aylık abonelik giderleriniz toplam {round(abone_toplam, 2)} TL.")

    skor = 70
    if toplam_gelir > 0:
        oran_h = toplam_harcama / toplam_gelir
        if oran_h < 0.5:
            skor = 95
        elif oran_h < 0.7:
            skor = 80
        elif oran_h < 0.9:
            skor = 65
        else:
            skor = 40

    conn.close()

    return render_template("reports.html",
                           toplam_fis=toplam_fis, toplam_harcama=round(toplam_harcama, 2),
                           toplam_kdv=round(toplam_kdv, 2), ortalama=ortalama, en_buyuk=round(en_buyuk, 2),
                           kat_harcama=kat_harcama, magazalar=magazalar, son_fisler=son_fisler,
                           aylik_gelir_gider=aylik_gelir_gider,
                           kategori_adi=kategori_adi, kategori_tutari=kategori_tutari,
                           tasarruf_tutari=tasarruf_tutari, oran_yuzde=int(oran * 100),
                           yorumlar=yorumlar, toplam_gelir=round(toplam_gelir, 2),
                           kalan=round(toplam_gelir - toplam_harcama, 2),
                           skor=skor
                           )

# bütçe sayfası
def ay_etiketi(ay):
    try:
        dt = datetime.strptime(ay, "%Y-%m")
        aylar = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                 "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        return f"{aylar[dt.month - 1]} {dt.year}"
    except Exception:
        return ay

def fis_ayini_bul(tarih, eklenme_tarihi=""):
    adaylar = []
    if tarih:
        adaylar.append(str(tarih).strip())
    if eklenme_tarihi:
        adaylar.append(str(eklenme_tarihi).strip()[:10])

    for value in adaylar:
        if not value:
            continue
        for fmt in ("%d/%m/%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value[:10], fmt).strftime("%Y-%m")
            except Exception:
                pass
        m = re.search(r"(20\d{2})[-/.](\d{1,2})", value)
        if m:
            return f"{m.group(1)}-{int(m.group(2)):02d}"
        m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})", value)
        if m:
            return f"{m.group(3)}-{int(m.group(2)):02d}"
    return datetime.now().strftime("%Y-%m")

def butce_durum_adi(oran):
    if oran >= 100:
        return "Limit Aşıldı", "danger"
    if oran >= 85:
        return "Kritik", "danger"
    if oran >= 60:
        return "Dikkat", "warning"
    return "Güvenli", "safe"

def butce_ai_yorumu_uret(ay_label, durumlar, toplam_butce, toplam_harcanan, toplam_gelir, abonelik_toplam):
    if not durumlar:
        return "Henüz bütçe tanımlanmadığı için yapay zekâ bütçe yorumu oluşturulmadı. Önce kategori bazlı aylık limit ekleyerek harcamalarınızı takip etmeye başlayabilirsiniz."

    en_yuksek = max(durumlar, key=lambda x: x["oran"]) if durumlar else None
    kalan = round(toplam_butce - toplam_harcanan, 2)
    klasik_yorum = (
        f"{ay_label} döneminde toplam bütçenizin %{round((toplam_harcanan / toplam_butce * 100), 1) if toplam_butce else 0} kadarı kullanılmıştır. "
        f"En çok dikkat isteyen kategori {en_yuksek['kategori']} görünmektedir. "
        f"Kalan bütçeniz {kalan} TL seviyesindedir. Harcama hızınızı özellikle yüksek oranlı kategorilerde azaltmanız önerilir."
    )

    if not os.getenv("OPENAI_API_KEY"):
        return klasik_yorum

    try:
        ozet = []
        for d in durumlar:
            ozet.append({
                "kategori": d["kategori"],
                "limit": d["limit"],
                "harcanan": d["harcanan"],
                "kalan": d["kalan"],
                "oran": d["oran"],
                "durum": d["durum"]
            })
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Sen Türkçe konuşan kişisel finans asistanısın. Kısa, net ve uygulanabilir bütçe yorumu yap. Abartılı yatırım tavsiyesi verme."},
                {"role": "user", "content": f"""
Kullanıcının {ay_label} bütçe verileri aşağıdadır.
Toplam bütçe: {toplam_butce} TL
Toplam harcama: {toplam_harcanan} TL
Aylık gelir: {toplam_gelir} TL
Aktif abonelik toplamı: {abonelik_toplam} TL
Kategori durumları: {json.dumps(ozet, ensure_ascii=False)}

3-5 cümlelik kişiselleştirilmiş bütçe yorumu üret. Limit aşımı varsa belirt. Tasarruf önerisini özellikle isteğe bağlı harcamalara yönelt.
"""}
            ],
            temperature=0.35,
            max_tokens=220
        )
        return response.choices[0].message.content.strip()
    except Exception:
        return klasik_yorum

@app.route("/butce", methods=["GET", "POST"])
@login_required
def butce():
    uid = session["user_id"]
    secili_ay = request.values.get("ay") or datetime.now().strftime("%Y-%m")

    conn = get_db()

    if request.method == "POST":
        kategori = request.form.get("kategori", "").strip()
        limit = guvenli_float(request.form.get("limit"), 0)
        secili_ay = request.form.get("ay") or secili_ay

        if not kategori or limit <= 0:
            flash("❌ Geçerli bir kategori ve limit tutarı girin.", "error")
            conn.close()
            return redirect(f"/butce?ay={secili_ay}")

        mevcut = conn.execute(
            "SELECT id FROM butceler WHERE user_id=? AND kategori=? AND ay=?",
            (uid, kategori, secili_ay)
        ).fetchone()

        if mevcut:
            conn.execute(
                "UPDATE butceler SET limit_tl=? WHERE id=? AND user_id=?",
                (limit, mevcut["id"], uid)
            )
            flash("✅ Bütçe limiti güncellendi.", "success")
        else:
            conn.execute(
                "INSERT INTO butceler(user_id,kategori,limit_tl,ay) VALUES(?,?,?,?)",
                (uid, kategori, limit, secili_ay)
            )
            flash("✅ Yeni bütçe limiti eklendi.", "success")
        conn.commit()
        conn.close()
        return redirect(f"/butce?ay={secili_ay}")

    butceler = conn.execute(
        "SELECT * FROM butceler WHERE user_id=? AND ay=? ORDER BY kategori ASC",
        (uid, secili_ay)
    ).fetchall()

    fis_rows = conn.execute(
        "SELECT id,tarih,eklenme_tarihi,magaza,kategori,toplam FROM fisler WHERE user_id=?",
        (uid,)
    ).fetchall()

    kategori_harcamalari = {}
    ay_fisleri = []
    for row in fis_rows:
        if fis_ayini_bul(row["tarih"], row["eklenme_tarihi"]) == secili_ay:
            kategori = row["kategori"] or "Diğer"
            tutar = float(row["toplam"] or 0)
            kategori_harcamalari[kategori] = kategori_harcamalari.get(kategori, 0) + tutar
            ay_fisleri.append(dict(row))

    abonelik_toplam = conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM abonelikler WHERE user_id=? AND aktif=1",
        (uid,)
    ).fetchone()[0]
    if abonelik_toplam:
        kategori_harcamalari["Abonelikler"] = kategori_harcamalari.get("Abonelikler", 0) + float(abonelik_toplam)

    toplam_gelir = conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM gelirler WHERE user_id=? AND substr(tarih,1,7)=?",
        (uid, secili_ay)
    ).fetchone()[0]

    butceli_kategoriler = {b["kategori"] for b in butceler}
    butcesiz_harcamalar = []
    for kat, tutar in sorted(kategori_harcamalari.items(), key=lambda x: x[1], reverse=True):
        if kat not in butceli_kategoriler and tutar > 0:
            butcesiz_harcamalar.append({"kategori": kat, "harcanan": round(tutar, 2)})

    butce_durumu = []
    for b in butceler:
        limit = float(b["limit_tl"] or 0)
        harcanan = round(float(kategori_harcamalari.get(b["kategori"], 0)), 2)
        kalan = round(limit - harcanan, 2)
        oran = round((harcanan / limit * 100), 1) if limit > 0 else 0
        durum, durum_class = butce_durum_adi(oran)
        butce_durumu.append({
            "id": b["id"],
            "kategori": b["kategori"],
            "limit": round(limit, 2),
            "harcanan": harcanan,
            "kalan": kalan,
            "oran": oran,
            "bar_oran": min(oran, 100),
            "durum": durum,
            "durum_class": durum_class
        })

    toplam_butce = round(sum(d["limit"] for d in butce_durumu), 2)
    toplam_harcanan = round(sum(d["harcanan"] for d in butce_durumu), 2)
    kalan_butce = round(toplam_butce - toplam_harcanan, 2)
    kullanim_orani = round((toplam_harcanan / toplam_butce * 100), 1) if toplam_butce > 0 else 0
    gelir_orani = round((toplam_butce / toplam_gelir * 100), 1) if toplam_gelir > 0 else 0
    tahmini_birikim = round(toplam_gelir - toplam_butce, 2) if toplam_gelir > 0 else 0

    uyarilar = []
    for d in butce_durumu:
        if d["oran"] >= 100:
            uyarilar.append({
                "tip": "danger",
                "metin": f"{d['kategori']} bütçesi {abs(d['kalan'])} TL aşılmış durumda."
            })
        elif d["oran"] >= 85:
            uyarilar.append({
                "tip": "danger",
                "metin": f"{d['kategori']} bütçesinin %{d['oran']} kadarı kullanıldı. Limit aşımına çok yakın."
            })
        elif d["oran"] >= 60:
            uyarilar.append({
                "tip": "warning",
                "metin": f"{d['kategori']} bütçesinde %{d['oran']} kullanım var. Ay sonuna kadar takip edilmeli."
            })

    top_fisler = sorted(ay_fisleri, key=lambda x: float(x.get("toplam") or 0), reverse=True)[:5]
    top_fisler = [{
        "id": f["id"],
        "tarih": f["tarih"],
        "magaza": f["magaza"],
        "kategori": f["kategori"],
        "toplam": round(float(f["toplam"] or 0), 2)
    } for f in top_fisler]

    ai_yorum = butce_ai_yorumu_uret(
        ay_etiketi(secili_ay), butce_durumu, toplam_butce,
        toplam_harcanan, float(toplam_gelir or 0), float(abonelik_toplam or 0)
    )

    conn.close()

    return render_template(
        "butce.html",
        ay=secili_ay,
        ay_label=ay_etiketi(secili_ay),
        kategoriler=KATEGORILER,
        butce_durumu=butce_durumu,
        butcesiz_harcamalar=butcesiz_harcamalar,
        toplam_butce=toplam_butce,
        toplam_harcanan=toplam_harcanan,
        kalan_butce=kalan_butce,
        kullanim_orani=kullanim_orani,
        gelir_orani=gelir_orani,
        toplam_gelir=round(float(toplam_gelir or 0), 2),
        tahmini_birikim=tahmini_birikim,
        abonelik_toplam=round(float(abonelik_toplam or 0), 2),
        uyarilar=uyarilar,
        top_fisler=top_fisler,
        ai_yorum=ai_yorum
    )

@app.route("/butce/sil/<int:bid>")
@login_required
def butce_sil(bid):
    uid = session["user_id"]
    secili_ay = request.args.get("ay") or datetime.now().strftime("%Y-%m")
    conn = get_db()
    conn.execute("DELETE FROM butceler WHERE id=? AND user_id=?", (bid, uid))
    conn.commit()
    conn.close()
    flash("🗑️ Bütçe limiti silindi.", "success")
    return redirect(f"/butce?ay={secili_ay}")

@app.route("/gelir", methods=["GET", "POST"])
@login_required
def gelir():
    uid = session["user_id"]
    if request.method == "POST":
        tip = request.form["tip"]
        tutar = float(request.form["tutar"])
        tarih = request.form["tarih"]
        aciklama = request.form.get("aciklama", "")
        tekrarlayan = 1 if request.form.get("tekrarlayan") else 0
        tekrar_gunu = int(request.form.get("tekrar_gunu", 1)) if tekrarlayan else 0

        conn = get_db()
        conn.execute("""
            INSERT INTO gelirler(user_id,tip,tutar,aciklama,tarih,tekrarlayan,tekrar_gunu)
            VALUES(?,?,?,?,?,?,?)
        """, (uid, tip, tutar, aciklama, tarih, tekrarlayan, tekrar_gunu))
        conn.commit()
        conn.close()
        flash("✅ Gelir eklendi.", "success")
        return redirect("/gelir")

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM gelirler WHERE user_id=? ORDER BY tarih DESC", (uid,)
    ).fetchall()
    toplam = conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM gelirler WHERE user_id=?", (uid,)
    ).fetchone()[0]
    conn.close()

    gelirler = [dict(row) for row in rows]

    return render_template("gelir.html", gelirler=gelirler, toplam=round(toplam, 2))

@app.route("/gelir/sil/<int:gid>")
@login_required
def gelir_sil(gid):
    conn = get_db()
    conn.execute("DELETE FROM gelirler WHERE id=? AND user_id=?", (gid, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect("/gelir")

@app.route("/gelir/guncelle/<int:gid>", methods=["POST"])
@login_required
def gelir_guncelle(gid):
    tip = request.form["tip"]
    tutar = float(request.form["tutar"])
    tarih = request.form["tarih"]
    aciklama = request.form.get("aciklama", "")
    tekrarlayan = 1 if request.form.get("tekrarlayan") else 0
    tekrar_gunu = int(request.form.get("tekrar_gunu", 1)) if tekrarlayan else 0

    conn = get_db()
    conn.execute("""
        UPDATE gelirler SET tip=?, tutar=?, aciklama=?, tarih=?,
        tekrarlayan=?, tekrar_gunu=? WHERE id=? AND user_id=?
    """, (tip, tutar, aciklama, tarih, tekrarlayan, tekrar_gunu, gid, session["user_id"]))
    conn.commit()
    conn.close()
    flash("✅ Gelir güncellendi.", "success")
    return redirect("/gelir")

@app.route("/abonelikler", methods=["GET", "POST"])
@login_required
def abonelikler():
    uid = session["user_id"]
    if request.method == "POST":
        conn = get_db()
        conn.execute("""
            INSERT INTO abonelikler(user_id,ad,tutar,odeme_gunu,kategori,renk)
            VALUES(?,?,?,?,?,?)
        """, (
            uid, request.form["ad"], float(request.form["tutar"]),
            int(request.form["odeme_gunu"]), request.form.get("kategori", "Eglence"),
            request.form.get("renk", "#4f46e5")
        ))
        conn.commit()
        conn.close()
        flash("✅ Abonelik eklendi.", "success")
        return redirect("/abonelikler")

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM abonelikler WHERE user_id=? ORDER BY odeme_gunu", (uid,)
    ).fetchall()
    toplam_aylik = conn.execute(
        "SELECT COALESCE(SUM(tutar),0) FROM abonelikler WHERE user_id=? AND aktif=1", (uid,)
    ).fetchone()[0]
    conn.close()

    abonelikler = [dict(row) for row in rows]
    bugun = datetime.now().day
    return render_template("abonelikler.html",
                           abonelikler=abonelikler, toplam_aylik=round(toplam_aylik, 2),
                           bugun=bugun, kategoriler=KATEGORILER)

@app.route("/abonelik/toggle/<int:aid>")
@login_required
def abonelik_toggle(aid):
    conn = get_db()
    conn.execute("""
        UPDATE abonelikler SET aktif = CASE WHEN aktif=1 THEN 0 ELSE 1 END
        WHERE id=? AND user_id=?
    """, (aid, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect("/abonelikler")

@app.route("/abonelik/sil/<int:aid>")
@login_required
def abonelik_sil(aid):
    conn = get_db()
    conn.execute("DELETE FROM abonelikler WHERE id=? AND user_id=?", (aid, session["user_id"]))
    conn.commit()
    conn.close()
    return redirect("/abonelikler")

@app.route("/abonelik/guncelle/<int:aid>", methods=["POST"])
@login_required
def abonelik_guncelle(aid):
    ad = request.form["ad"]
    tutar = float(request.form["tutar"])
    odeme_gunu = int(request.form["odeme_gunu"])
    kategori = request.form.get("kategori", "Eglence")
    renk = request.form.get("renk", "#4f46e5")

    conn = get_db()
    conn.execute("""
        UPDATE abonelikler SET ad=?, tutar=?, odeme_gunu=?, kategori=?, renk=?
        WHERE id=? AND user_id=?
    """, (ad, tutar, odeme_gunu, kategori, renk, aid, session["user_id"]))
    conn.commit()
    conn.close()
    flash("✅ Abonelik güncellendi.", "success")
    return redirect("/abonelikler")

@app.route("/asistan")
@login_required
def asistan():
    uid = session["user_id"]
    conn = get_db()
    oturumlar = conn.execute(
        "SELECT * FROM sohbet_oturumlari WHERE user_id=? ORDER BY olusturma_tarihi DESC",
        (uid,)
    ).fetchall()

    aktif_oturum_id = request.args.get("oturum")
    if not aktif_oturum_id and oturumlar:
        aktif_oturum_id = oturumlar[0]["id"]
        return redirect(f"/asistan?oturum={aktif_oturum_id}")

    mesajlar = []
    if aktif_oturum_id:
        mesajlar = conn.execute(
            "SELECT * FROM sohbet_mesajlari WHERE oturum_id=? AND user_id=? ORDER BY id ASC",
            (aktif_oturum_id, uid)
        ).fetchall()

    conn.close()
    return render_template("asistan.html",
                           oturumlar=oturumlar,
                           aktif_oturum_id=aktif_oturum_id,
                           mesajlar=mesajlar)

@app.route("/asistan/yeni")
@login_required
def asistan_yeni():
    yeni_id = oturum_olustur(session["user_id"])
    return redirect(f"/asistan?oturum={yeni_id}")

@app.route("/asistan/mesaj", methods=["POST"])
@login_required
def asistan_mesaj():
    uid = session["user_id"]
    oturum_id = request.form.get("oturum_id")
    soru = request.form.get("soru", "").strip()

    if not oturum_id or not soru:
        flash("Geçersiz istek.", "error")
        return redirect("/asistan")

    conn = get_db()
    msg_count = conn.execute(
        "SELECT COUNT(*) FROM sohbet_mesajlari WHERE oturum_id=?", (oturum_id,)
    ).fetchone()[0]
    if msg_count == 0:
        oturum_baslik_guncelle(oturum_id, soru)

    conn.execute(
        "INSERT INTO sohbet_mesajlari (oturum_id, user_id, rol, icerik) VALUES (?, ?, 'user', ?)",
        (oturum_id, uid, soru)
    )
    conn.commit()

    yanit = ai_asistan_yanit(uid, soru, oturum_id=oturum_id)

    conn.execute(
        "INSERT INTO sohbet_mesajlari (oturum_id, user_id, rol, icerik) VALUES (?, ?, 'assistant', ?)",
        (oturum_id, uid, yanit)
    )
    conn.commit()
    conn.close()

    return redirect(f"/asistan?oturum={oturum_id}")

@app.route("/asistan/sil/<oturum_id>")
@login_required
def asistan_sil(oturum_id):
    uid = session["user_id"]
    conn = get_db()

    conn.execute("DELETE FROM sohbet_mesajlari WHERE oturum_id=? AND user_id=?", (oturum_id, uid))

    conn.execute("DELETE FROM sohbet_oturumlari WHERE id=? AND user_id=?", (oturum_id, uid))
    conn.commit()
    conn.close()
    flash("🗑️ Sohbet silindi.", "success")
    return redirect("/asistan")

@app.route("/profil", methods=["GET", "POST"])
@login_required
def profil():
    uid = session["user_id"]
    conn = get_db()

    if request.method == "POST":
        aksiyon = request.form.get("aksiyon")
        if aksiyon == "bilgi":
            conn.execute("""
                UPDATE users SET ad=?,email=?,telefon=?,dogum_tarihi=?,
                meslek=?,sehir=? WHERE id=?
            """, (
                request.form["ad"], request.form["email"], request.form.get("telefon", ""),
                request.form.get("dogum_tarihi", ""), request.form.get("meslek", ""),
                request.form.get("sehir", ""),
                uid
            ))
            conn.commit()
            session["user_name"] = request.form["ad"]
            session["user_email"] = request.form["email"]
            flash("✅ Profil güncellendi.", "success")

        elif aksiyon == "sifre":
            eski = request.form["old_password"]
            yeni = request.form["new_password"]
            yeni2 = request.form["new_password2"]
            mevcut = conn.execute("SELECT sifre FROM users WHERE id=?", (uid,)).fetchone()["sifre"]
            if mevcut != eski:
                flash("❌ Mevcut şifre yanlış.", "error")
            elif yeni != yeni2:
                flash("❌ Yeni şifreler eşleşmiyor.", "error")
            elif len(yeni) < 6:
                flash("❌ Yeni şifre en az 6 karakter olmalıdır.", "error")
            else:
                conn.execute("UPDATE users SET sifre=? WHERE id=?", (yeni, uid))
                conn.commit()
                flash("✅ Şifre güncellendi.", "success")

        conn.close()
        return redirect("/profil")

    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    fis_sayisi = conn.execute("SELECT COUNT(*) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]
    toplam_harc = conn.execute("SELECT COALESCE(SUM(toplam),0) FROM fisler WHERE user_id=?", (uid,)).fetchone()[0]
    uye_tarihi = conn.execute("SELECT olusturma_tarihi FROM users WHERE id=?", (uid,)).fetchone()["olusturma_tarihi"]
    conn.close()

    return render_template("profil.html", user=user,
                           fis_sayisi=fis_sayisi, toplam_harc=round(toplam_harc, 2),
                           uye_tarihi=uye_tarihi)

@app.route("/profil/sil", methods=["POST"])
@login_required
def profil_sil():
    uid = session["user_id"]
    conn = get_db()

    conn.execute("DELETE FROM fisler WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM gelirler WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM abonelikler WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM sohbet_mesajlari WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM sohbet_oturumlari WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM butceler WHERE user_id=?", (uid,))

    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.commit()
    conn.close()

    session.clear()
    flash("Hesabınız ve tüm verileriniz silindi.", "success")
    return redirect("/")

@app.route("/api/sohbet", methods=["POST"])
@login_required
def api_sohbet():
    soru = request.json.get("soru", "").strip()
    if not soru:
        return jsonify({"hata": "Soru boş"})
    yanit = ai_asistan_yanit(session["user_id"], soru)
    uid = session["user_id"]
    conn = get_db()
    conn.execute("INSERT INTO sohbet_gecmisi(user_id,rol,icerik) VALUES(?,?,?)", (uid, "user", soru))
    conn.execute("INSERT INTO sohbet_gecmisi(user_id,rol,icerik) VALUES(?,?,?)", (uid, "assistant", yanit))
    conn.commit()
    conn.close()
    return jsonify({"yanit": yanit})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)