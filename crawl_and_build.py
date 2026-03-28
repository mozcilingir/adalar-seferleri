"""
crawl_and_build.py
------------------
Adalar vapur seferleri için web crawling + HTML build scripti.
GitHub Actions tarafından her gün otomatik çalıştırılır.

Gereksinimler:
    pip install requests beautifulsoup4 anthropic

Kullanım:
    python3 crawl_and_build.py
    
Ortam değişkenleri:
    ANTHROPIC_API_KEY  →  Prenstur OCR için (GitHub Secret olarak tanımlayın)
"""

import re, json, os, sys, time, base64
import requests
from bs4 import BeautifulSoup
import anthropic

# ================================================================
# CRAWLING
# ================================================================

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (compatible; AdalarSeferleriBot/1.0)',
    'Accept-Language': 'tr-TR,tr;q=0.9',
}

def fetch(url, retries=3, timeout=15):
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            r.encoding = 'utf-8'
            return r
        except Exception as e:
            print(f"  [{i+1}/{retries}] {url} → {e}")
            time.sleep(3)
    return None

def parse_tables(html):
    """BeautifulSoup ile tüm tabloları satır listesi olarak döndür."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = []
    for tbl in soup.find_all('table'):
        rows = []
        for tr in tbl.find_all('tr'):
            cells = [td.get_text(strip=True) for td in tr.find_all(['td','th'])]
            if any(c for c in cells):
                rows.append(cells)
        if rows:
            tables.append(rows)
    return tables

def trips(raw, dep_col, arr_col):
    return [{'dep': r[dep_col], 'arr': r[arr_col]}
            for r in raw if len(r) > max(dep_col, arr_col)
            and r[dep_col] != '-' and r[arr_col] != '-']

def clean_star(t):
    return t.replace(' *', '★').replace('*', '★').strip()

def malt_trips(raw, dep_col, arr_col):
    return [{'dep': clean_star(r[dep_col]), 'arr': clean_star(r[arr_col])}
            for r in raw if len(r) > max(dep_col, arr_col)
            and r[dep_col] != '-' and r[arr_col] != '-']

def malt_paz(raw, dep_col, arr_col):
    return [t for t in malt_trips(raw, dep_col, arr_col) if '★' not in t['dep']]


# ================================================================
# ŞEHİR HATLARI CRAWL
# ================================================================

SH_URLS = {
    'kabatas':   'https://www.sehirhatlari.istanbul/tr/seferler/ic-hatlar/adalar-hatlari/kabatas-adalar-177',
    'besiktas':  'https://www.sehirhatlari.istanbul/tr/seferler/ic-hatlar/adalar-hatlari/adalar-besiktas-769',
    'bostanci':  'https://www.sehirhatlari.istanbul/tr/seferler/ic-hatlar/adalar-hatlari/bostanci-adalar-ring-',
    'maltepe':   'https://www.sehirhatlari.istanbul/tr/seferler/ic-hatlar/adalar-hatlari/maltepe-buyukada-heybeliada',
    'sedef':     'https://www.sehirhatlari.istanbul/tr/seferler/ic-hatlar/adalar-hatlari/buyukada-sedef-adasi-',
    'tuzla':     'https://www.sehirhatlari.istanbul/tr/seferler/ic-hatlar/adalar-hatlari/tuzla-pendik-buyukada',
}

def crawl_sh():
    print("\n=== Şehir Hatları crawl ediliyor ===")
    data = {}
    for key, url in SH_URLS.items():
        print(f"  {key}: {url}")
        r = fetch(url)
        if r:
            data[key] = parse_tables(r.text)
            print(f"    → {len(data[key])} tablo bulundu")
        else:
            print(f"    → BAŞARISIZ, mevcut veri kullanılacak")
            data[key] = None
    return data

def build_sh(sh_data):
    """Şehir Hatları verilerini D yapısı formatına dönüştür."""

    # Kabataş tablosu
    # Tablo 1 = HİÇ gidiş, Tablo 2 = PAZ gidiş
    # Tablo 3 = HİÇ dönüş, Tablo 4 = PAZ dönüş
    # Sütunlar gidiş: Kabataş(0), Eminönü(1), Kadıköy(2), Kın(3), Bur(4), Hey(5), Buy(6), Bostancı(7)
    # Sütunlar dönüş: Bostancı(0), Buy(1), Hey(2), Bur(3), Kın(4), Kadıköy(5), Eminönü(6), Kabataş(7)

    kab = sh_data.get('kabatas')
    kab_gid_hic = kab[1][2:] if kab and len(kab) > 1 else []  # başlık satırlarını atla
    kab_gid_paz = kab[2][2:] if kab and len(kab) > 2 else []
    kab_don_hic = kab[3][2:] if kab and len(kab) > 3 else []
    kab_don_paz = kab[4][2:] if kab and len(kab) > 4 else []

    # Beşiktaş tablosu
    # Tablo 1 = HİÇ dönüş (Buy→...→Kadıköy→Beşiktaş), Tablo 2 = PAZ dönüş
    # Tablo 3 = HİÇ gidiş (Beşiktaş→...→Buy),          Tablo 4 = PAZ gidiş
    bes = sh_data.get('besiktas')
    bes_don_hic = bes[1][2:] if bes and len(bes) > 1 else []
    bes_don_paz = bes[2][2:] if bes and len(bes) > 2 else []
    bes_gid_hic = bes[3][2:] if bes and len(bes) > 3 else []
    bes_gid_paz = bes[4][2:] if bes and len(bes) > 4 else []

    # Bostancı Ring
    # Tablo 1 = HİÇ gidiş (Bostancı→Kın→Bur→Hey→Buy→Bostancı)
    # Tablo 2 = PAZ gidiş
    # Tablo 3 = HİÇ dönüş (Bostancı→Buy→Hey→Bur→Kın→Bostancı)
    # Tablo 4 = PAZ dönüş
    bos = sh_data.get('bostanci')
    ring_gid_hic = bos[1][2:] if bos and len(bos) > 1 else []
    ring_gid_paz = bos[2][2:] if bos and len(bos) > 2 else []
    ring_don_hic = bos[3][2:] if bos and len(bos) > 3 else []
    ring_don_paz = bos[4][2:] if bos and len(bos) > 4 else []

    # Maltepe (tek tablo, HİÇ=PAZ ancak ★ olanlar pazar yapılmaz)
    malt = sh_data.get('maltepe')
    malt_gid = malt[1][2:] if malt and len(malt) > 1 else []
    malt_don = malt[2][2:] if malt and len(malt) > 2 else []

    return {
        'kab_gid_hic': kab_gid_hic, 'kab_gid_paz': kab_gid_paz,
        'kab_don_hic': kab_don_hic, 'kab_don_paz': kab_don_paz,
        'bes_gid_hic': bes_gid_hic, 'bes_gid_paz': bes_gid_paz,
        'bes_don_hic': bes_don_hic, 'bes_don_paz': bes_don_paz,
        'ring_gid_hic': ring_gid_hic, 'ring_gid_paz': ring_gid_paz,
        'ring_don_hic': ring_don_hic, 'ring_don_paz': ring_don_paz,
        'malt_gid': malt_gid, 'malt_don': malt_don,
    }


# ================================================================
# MAVİ MARMARA CRAWL
# ================================================================

MM_URLS = {
    'bos_buy':  'https://mavimarmara.net/tarifeler/bostanci-buyukada/',
    'bos_bur':  'https://mavimarmara.net/tarifeler/bostanci-burgazada/',
    'buy_bos':  'https://mavimarmara.net/tarifeler/buyukada-bostanci/',
    'bur_bos':  'https://mavimarmara.net/tarifeler/burgazada-bostanci/',
    'kin_bur':  'https://mavimarmara.net/tarifeler/kinaliada-burgazada/',
    'bes_buy':  'https://mavimarmara.net/tarifeler/besiktas-buyukada/',
    'bes_hey':  'https://mavimarmara.net/tarifeler/besiktas-heybeliada/',
    'buy_kab':  'https://mavimarmara.net/tarifeler/buyukada-kabatas/',
    'hey_kab':  'https://mavimarmara.net/tarifeler/heybeliada-kabatas/',
    'emi_buy':  'https://mavimarmara.net/tarifeler/eminonu-buyukada/',
    'emi_hey':  'https://mavimarmara.net/tarifeler/eminonu-heybeliada/',
}

def crawl_mm():
    print("\n=== Mavi Marmara crawl ediliyor ===")
    data = {}
    for key, url in MM_URLS.items():
        print(f"  {key}: {url}")
        r = fetch(url)
        if r:
            tables = parse_tables(r.text)
            # İlk anlamlı tabloyu al (cookie tablosunu atla)
            sched = [t for t in tables if t and len(t[0]) == 2 and ':' in str(t)]
            data[key] = sched[0][1:] if sched else []  # başlık satırını atla
            print(f"    → {len(data[key])} sefer bulundu")
        else:
            data[key] = []
    return data

def parse_mm_route(rows):
    """SAAT | VARIŞ GÜZERGAHI formatındaki tabloyu parse et."""
    result = []
    for row in rows:
        if len(row) >= 1:
            t = row[0].replace('*', '★').strip()
            result.append({'dep': t, 'arr': ''})
    return result

def mm_paz(rows):
    return [x for x in parse_mm_route(rows) if '★' not in x['dep']]


# ================================================================
# PRENSTUR OCR (Anthropic API)
# ================================================================

PRENSTUR_URL = 'https://www.prenstur.net/'

def crawl_prenstur_ocr():
    print("\n=== Prenstur OCR ===")
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("  ANTHROPIC_API_KEY bulunamadı, mevcut veri kullanılacak")
        return None

    # Tarife resmini bul ve indir
    r = fetch(PRENSTUR_URL)
    if not r:
        return None

    soup = BeautifulSoup(r.text, 'html.parser')
    img_url = None
    for img in soup.find_all('img'):
        src = img.get('src','')
        if 'Tarife' in src or 'tarife' in src:
            img_url = src if src.startswith('http') else PRENSTUR_URL.rstrip('/') + src
            break

    if not img_url:
        print("  Tarife resmi bulunamadı")
        return None

    print(f"  Resim: {img_url}")
    img_r = fetch(img_url)
    if not img_r:
        return None

    img_b64 = base64.standard_b64encode(img_r.content).decode('utf-8')
    ext = img_url.split('.')[-1].lower()
    media_type = 'image/jpeg' if ext in ('jpg','jpeg') else 'image/png'

    client = anthropic.Anthropic(api_key=api_key)
    print("  Claude Vision ile OCR yapılıyor...")

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=2000,
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'image', 'source': {'type': 'base64', 'media_type': media_type, 'data': img_b64}},
                {'type': 'text', 'text': '''Bu Prenstur vapur tarife tablosundaki tüm sefer saatlerini JSON formatında çıkar.
Sadece JSON döndür, başka hiçbir şey yazma.
Format:
{
  "gidis": [
    {"dep": "06:20*", "buy_arr": "06:45*", "hey_arr": "06:55*"},
    ...
  ],
  "donus": [
    {"hey_dep": "07:00*", "buy_dep": "07:15*", "arr": "07:40*"},
    ...
  ]
}
* işareti pazar ve tatil günleri yapılmaz anlamına gelir.'''}
            ]
        }]
    )

    text = response.content[0].text.strip()
    text = re.sub(r'^```json\s*', '', text)
    text = re.sub(r'\s*```$', '', text)

    try:
        parsed = json.loads(text)
        print(f"  Gidiş: {len(parsed.get('gidis',[]))} sefer, Dönüş: {len(parsed.get('donus',[]))} sefer")
        return parsed
    except Exception as e:
        print(f"  JSON parse hatası: {e}")
        print(f"  Ham yanıt: {text[:200]}")
        return None


# ================================================================
# D YAPISI OLUŞTUR
# ================================================================

def build_D(sh, mm, pr):
    D = {ada: {'gidis': [], 'donus': []} for ada in ['Büyükada','Heybeliada','Burgazada','Kınalıada']}
    note_mm = '★ işaretli sefer Pazar ve Resmi Tatil günleri yapılmaz'
    note_malt = '★ işaretli seferler Pazar ve Resmi Tatil günleri yapılmaz'

    # --- KABATAŞ GİDİŞ ---
    # Sütunlar: 0=Kabataş, 1=Eminönü, 2=Kadıköy, 3=Kın, 4=Bur, 5=Hey, 6=Buy, 7=Bostancı
    for ada, col in [('Kınalıada',3),('Burgazada',4),('Heybeliada',5),('Büyükada',6)]:
        D[ada]['gidis'].append({'iskele':'Kabataş','sirket':'Şehir Hatları','note':'',
            'hic': trips(sh['kab_gid_hic'],0,col),
            'pazar': trips(sh['kab_gid_paz'],0,col)})
    for ada, col in [('Kınalıada',3),('Burgazada',4),('Heybeliada',5),('Büyükada',6)]:
        D[ada]['gidis'].append({'iskele':'Kadıköy','sirket':'Şehir Hatları','note':'',
            'hic': trips(sh['kab_gid_hic'],2,col),
            'pazar': trips(sh['kab_gid_paz'],2,col)})

    # --- KABATAŞ / KADİKÖY DÖNÜŞ ---
    # Sütunlar: 0=Bostancı, 1=Buy, 2=Hey, 3=Bur, 4=Kın, 5=Kadıköy, 6=Eminönü, 7=Kabataş
    for ada, col in [('Büyükada',1),('Heybeliada',2),('Burgazada',3),('Kınalıada',4)]:
        D[ada]['donus'].append({'iskele':f'{ada} → Kabataş','sirket':'Şehir Hatları','note':'',
            'hic': trips(sh['kab_don_hic'],col,7),
            'pazar': trips(sh['kab_don_paz'],col,7)})
        D[ada]['donus'].append({'iskele':f'{ada} → Kadıköy','sirket':'Şehir Hatları','note':'',
            'hic': trips(sh['kab_don_hic'],col,5),
            'pazar': trips(sh['kab_don_paz'],col,5)})

    # --- BEŞİKTAŞ ---
    # Gidiş: 0=Beşiktaş, 1=Kın, 2=Bur, 3=Hey, 4=Buy
    # Dönüş: 0=Buy, 1=Hey, 2=Bur, 3=Kın, 4=Kadıköy, 5=Beşiktaş
    for ada, gc, dc in [('Kınalıada',1,3),('Burgazada',2,2),('Heybeliada',3,1),('Büyükada',4,0)]:
        D[ada]['gidis'].append({'iskele':'Beşiktaş','sirket':'Şehir Hatları','note':'',
            'hic': trips(sh['bes_gid_hic'],0,gc),
            'pazar': trips(sh['bes_gid_paz'],0,gc)})
        D[ada]['donus'].append({'iskele':f'{ada} → Beşiktaş','sirket':'Şehir Hatları','note':'',
            'hic': trips(sh['bes_don_hic'],dc,5),
            'pazar': trips(sh['bes_don_paz'],dc,5)})
        D[ada]['donus'].append({'iskele':f'{ada} → Kadıköy','sirket':'Şehir Hatları','note':'Beşiktaş hattı üzerinden',
            'hic': trips(sh['bes_don_hic'],dc,4),
            'pazar': trips(sh['bes_don_paz'],dc,4)})

    # --- BOSTANCI RING ---
    # Gidiş: 0=Bostancı, 1=Kın, 2=Bur, 3=Hey, 4=Buy, 5=Bostancı(dön)
    # Dönüş: 0=Bostancı, 1=Buy, 2=Hey, 3=Bur, 4=Kın, 5=Bostancı(dön)
    ring_gid_ada = {'Kınalıada':1,'Burgazada':2,'Heybeliada':3,'Büyükada':4}
    ring_don_ada = {'Büyükada':1,'Heybeliada':2,'Burgazada':3,'Kınalıada':4}
    for ada in ['Büyükada','Heybeliada','Burgazada','Kınalıada']:
        gc = ring_gid_ada[ada]
        dc = ring_don_ada[ada]
        base_hic = trips(sh['ring_gid_hic'],0,gc)
        base_paz = trips(sh['ring_gid_paz'],0,gc)
        # Kabataş tablosundan gelen ek Bostancı kalkışları
        kab_extra_col = {'Büyükada':1,'Heybeliada':2,'Burgazada':3,'Kınalıada':4}[ada]
        ext = [{'dep': r[0], 'arr': r[kab_extra_col]}
               for r in sh['kab_don_hic'] if r[0]!='-' and len(r)>kab_extra_col and r[kab_extra_col]!='-']
        existing = {t['dep'] for t in base_hic}
        extra = [t for t in ext if t['dep'] not in existing]
        all_hic = sorted(base_hic + extra, key=lambda t: t['dep'])
        all_paz = sorted(base_paz + [t for t in extra
                         if t['dep'] not in {t2['dep'] for t2 in base_paz}], key=lambda t: t['dep'])
        D[ada]['gidis'].append({'iskele':'Bostancı','sirket':'Şehir Hatları','note':'Ring hat',
            'hic': all_hic, 'pazar': all_paz})
        D[ada]['donus'].append({'iskele':f'{ada} → Bostancı','sirket':'Şehir Hatları','note':'Ring hat',
            'hic': trips(sh['ring_don_hic'],dc,5),
            'pazar': trips(sh['ring_don_paz'],dc,5)})

    # --- MALTEPE ---
    # Gidiş: 0=Maltepe, 1=Buy, 2=Hey, 3=Bur, 4=Kın
    # Dönüş: 0=Kın, 1=Bur, 2=Hey, 3=Buy, 4=Maltepe
    for ada, gc, dc in [('Büyükada',1,3),('Heybeliada',2,2),('Burgazada',3,1),('Kınalıada',4,0)]:
        D[ada]['gidis'].append({'iskele':'Maltepe','sirket':'Şehir Hatları','note':note_malt,
            'hic': malt_trips(sh['malt_gid'],0,gc),
            'pazar': malt_paz(sh['malt_gid'],0,gc)})
        D[ada]['donus'].append({'iskele':f'{ada} → Maltepe','sirket':'Şehir Hatları','note':note_malt,
            'hic': malt_trips(sh['malt_don'],dc,4),
            'pazar': malt_paz(sh['malt_don'],dc,4)})

    # --- SEDEF & TUZLA (statik, değişmez) ---
    D['Büyükada']['gidis'].append({'iskele':'Sedef Adası','sirket':'Şehir Hatları','note':'Sedef Adası hattı',
        'hic':[{'dep':'07:35','arr':'07:50'}], 'pazar':[{'dep':'07:55','arr':'08:10'}]})
    D['Büyükada']['donus'].append({'iskele':'Büyükada → Sedef Adası','sirket':'Şehir Hatları','note':'Sedef Adası hattı',
        'hic':[{'dep':'19:45','arr':'20:00'}], 'pazar':[{'dep':'19:45','arr':'20:00'}]})
    D['Büyükada']['gidis'].append({'iskele':'Tuzla / Pendik','sirket':'Şehir Hatları',
        'note':'Cumartesi, Pazar ve Resmi Tatil günleri',
        'hic':[], 'pazar':[{'dep':'10:35','arr':'12:15'}]})
    D['Büyükada']['donus'].append({'iskele':'Büyükada → Tuzla','sirket':'Şehir Hatları',
        'note':'Cumartesi, Pazar ve Resmi Tatil günleri',
        'hic':[], 'pazar':[{'dep':'18:20','arr':'20:00'}]})

    # --- MAVİ MARMARA ---
    def mmr(rows): return parse_mm_route(rows)

    for ada in ['Büyükada','Heybeliada']:
        D[ada]['gidis'].append({'iskele':'Bostancı','sirket':'Mavi Marmara','note':note_mm,
            'hic': mmr(mm.get('bos_buy',[])), 'pazar': mm_paz(mm.get('bos_buy',[]))})

    D['Büyükada']['donus'].append({'iskele':'Büyükada → Bostancı','sirket':'Mavi Marmara','note':note_mm,
        'hic': mmr(mm.get('buy_bos',[])), 'pazar': mm_paz(mm.get('buy_bos',[]))})
    D['Heybeliada']['donus'].append({'iskele':'Heybeliada → Bostancı','sirket':'Mavi Marmara','note':note_mm,
        'hic': mmr(mm.get('buy_bos',[])), 'pazar': mm_paz(mm.get('buy_bos',[]))})

    for ada in ['Burgazada','Kınalıada']:
        D[ada]['gidis'].append({'iskele':'Bostancı','sirket':'Mavi Marmara','note':note_mm,
            'hic': mmr(mm.get('bos_bur',[])), 'pazar': mm_paz(mm.get('bos_bur',[]))})
    D['Burgazada']['donus'].append({'iskele':'Burgazada → Bostancı','sirket':'Mavi Marmara','note':note_mm,
        'hic': mmr(mm.get('bur_bos',[])), 'pazar': mm_paz(mm.get('bur_bos',[]))})
    D['Kınalıada']['donus'].append({'iskele':'Kınalıada → Bostancı','sirket':'Mavi Marmara','note':note_mm,
        'hic': mmr(mm.get('bur_bos',[])) + mmr(mm.get('kin_bur',[])),
        'pazar': mm_paz(mm.get('bur_bos',[])) + mm_paz(mm.get('kin_bur',[]))})

    D['Büyükada']['gidis'].append({'iskele':'Beşiktaş','sirket':'Mavi Marmara','note':'',
        'hic': mmr(mm.get('bes_buy',[])), 'pazar': mmr(mm.get('bes_buy',[]))})
    D['Heybeliada']['gidis'].append({'iskele':'Beşiktaş','sirket':'Mavi Marmara','note':'',
        'hic': mmr(mm.get('bes_hey',[])), 'pazar': mmr(mm.get('bes_hey',[]))})
    D['Büyükada']['donus'].append({'iskele':'Büyükada → Kabataş','sirket':'Mavi Marmara','note':'',
        'hic': mmr(mm.get('buy_kab',[])), 'pazar': mmr(mm.get('buy_kab',[]))})
    D['Heybeliada']['donus'].append({'iskele':'Heybeliada → Kabataş','sirket':'Mavi Marmara','note':'',
        'hic': mmr(mm.get('hey_kab',[])), 'pazar': mmr(mm.get('hey_kab',[]))})
    D['Büyükada']['gidis'].append({'iskele':'Eminönü','sirket':'Mavi Marmara','note':'',
        'hic': mmr(mm.get('emi_buy',[])), 'pazar': mmr(mm.get('emi_buy',[]))})
    D['Heybeliada']['gidis'].append({'iskele':'Eminönü','sirket':'Mavi Marmara','note':'',
        'hic': mmr(mm.get('emi_hey',[])), 'pazar': mmr(mm.get('emi_hey',[]))})

    # --- PRENSTUR ---
    if pr:
        note_pr = '★ işaretli sefer Pazar ve Resmi Tatil günleri yapılmaz'
        buy_gid = [{'dep': s['dep'], 'arr': s.get('buy_arr','')} for s in pr.get('gidis',[])]
        hey_gid = [{'dep': s['dep'], 'arr': s.get('hey_arr','')} for s in pr.get('gidis',[])]
        hey_don = [{'dep': s.get('hey_dep',''), 'arr': s.get('arr','')} for s in pr.get('donus',[])]
        buy_don = [{'dep': s.get('buy_dep',''), 'arr': s.get('arr','')} for s in pr.get('donus',[])]
        def pr_paz(lst): return [t for t in lst if '★' not in t['dep'] and '★' not in t.get('arr','')]
        D['Büyükada']['gidis'].append({'iskele':'Kartal','sirket':'Prenstur','note':note_pr,
            'hic': buy_gid, 'pazar': pr_paz(buy_gid)})
        D['Heybeliada']['gidis'].append({'iskele':'Kartal','sirket':'Prenstur','note':note_pr,
            'hic': hey_gid, 'pazar': pr_paz(hey_gid)})
        D['Büyükada']['donus'].append({'iskele':'Büyükada → Kartal','sirket':'Prenstur','note':note_pr,
            'hic': buy_don, 'pazar': pr_paz(buy_don)})
        D['Heybeliada']['donus'].append({'iskele':'Heybeliada → Kartal','sirket':'Prenstur','note':note_pr,
            'hic': hey_don, 'pazar': pr_paz(hey_don)})

    return D


# ================================================================
# HTML BUILD
# ================================================================

def build_html(D, template_path, output_path):
    with open(template_path, encoding='utf-8') as f:
        content = f.read()
    D_json = json.dumps(D, ensure_ascii=False, separators=(',', ':'))
    # Güncelleme tarihini de ekle
    import datetime
    tarih = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime('%d.%m.%Y %H:%M')
    D_json_with_meta = D_json  # Tarihi JS tarafında göstermek için
    new_content = re.sub(r'const D=\{.*?\};', f'const D={D_json_with_meta};', content, flags=re.DOTALL)
    # Güncelleme tarihini HTML'ye ekle
    new_content = re.sub(
        r'(Şehir Hatları · Mavi Marmara · Prenstur)',
        f'\\1 · Güncellendi: {tarih}',
        new_content
    )
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print(f"\nOluşturuldu: {output_path}  ({len(D_json)} karakter)")


# ================================================================
# ANA PROGRAM
# ================================================================

if __name__ == '__main__':
    template = os.environ.get('TEMPLATE_HTML', 'Adalar_fetched_pages.HTML')
    output   = os.environ.get('OUTPUT_HTML', 'docs/index.html')

    if not os.path.exists(template):
        print(f"HATA: Şablon dosyası bulunamadı: {template}")
        sys.exit(1)

    os.makedirs(os.path.dirname(output) or '.', exist_ok=True)

    # Crawl
    sh_raw  = crawl_sh()
    mm_raw  = crawl_mm()
    pr_data = crawl_prenstur_ocr()

    # Dönüştür
    sh = build_sh(sh_raw)
    mm = mm_raw

    # D yapısı oluştur
    D = build_D(sh, mm, pr_data)

    # Özet
    print("\n=== Özet ===")
    for ada in D:
        print(f"  {ada}: {len(D[ada]['gidis'])} gidiş, {len(D[ada]['donus'])} dönüş hattı")

    # HTML yaz
    build_html(D, template, output)
