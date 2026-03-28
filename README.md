# Adalar Vapur Seferleri 🚢

İstanbul Adaları vapur sefer saatlerini gösteren, her gün otomatik güncellenen web uygulaması.

**→ [adalar-seferleri.github.io](https://YOUR_USERNAME.github.io/adalar-seferleri)**

---

## Kurulum

### 1. Repoyu oluştur

GitHub'da yeni bir repo oluşturun (örn. `adalar-seferleri`).

### 2. Dosyaları yükle

```
adalar-seferleri/
├── Adalar_fetched_pages.HTML     ← UI şablonu
├── crawl_and_build.py            ← Ana script
├── .github/
│   └── workflows/
│       └── update_adalar.yml     ← GitHub Actions workflow
└── docs/
    └── index.html                ← Oluşturulan HTML (otomatik)
```

### 3. GitHub Pages'i etkinleştir

- Repo → **Settings** → **Pages**
- Source: **Deploy from a branch**
- Branch: `main`, klasör: `/docs`
- **Save**'e tıkla

### 4. Anthropic API key ekle (Prenstur OCR için)

- Repo → **Settings** → **Secrets and variables** → **Actions**
- **New repository secret**
- Name: `ANTHROPIC_API_KEY`
- Value: Anthropic API key'iniz

### 5. İlk çalıştırma

- Repo → **Actions** → **Adalar Vapur Seferleri - Günlük Güncelleme**
- **Run workflow** → **Run workflow**

---

## Nasıl çalışır?

```
Her gece 05:00 (İstanbul)
        │
        ▼
GitHub Actions tetiklenir
        │
        ├── Şehir Hatları sitesini crawl eder
        │   └── Kabataş, Beşiktaş, Bostancı Ring, Maltepe sayfaları
        │
        ├── Mavi Marmara sitesini crawl eder
        │   └── Bostancı, Beşiktaş, Eminönü, Kabataş hatları
        │
        ├── Prenstur tarife resmini indirir
        │   └── Claude Vision ile OCR yaparak sefer saatlerini çıkarır
        │
        ├── Tüm veriyi birleştirip docs/index.html oluşturur
        │
        └── GitHub Pages'e otomatik yayınlar
```

## Kaynaklar

| Şirket | Site |
|--------|------|
| Şehir Hatları | sehirhatlari.istanbul |
| Mavi Marmara | mavimarmara.net |
| Prenstur | prenstur.net |

## Lokal çalıştırma

```bash
pip install requests beautifulsoup4 anthropic
export ANTHROPIC_API_KEY=your_key_here
python3 crawl_and_build.py
```
# adalar-seferleri
