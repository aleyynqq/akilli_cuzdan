# AkıllıCüzdan

**OCR ve Yapay Zekâ Destekli Harcama Analizi ve Bütçe Yönetim Sistemi**

## Proje Hakkında

AkıllıCüzdan, fiş ve fatura görsellerini OCR teknolojisi ile okuyarak harcama verilerine dönüştüren bir web uygulamasıdır. Okunan bilgiler kullanıcı tarafından doğrulanır ve daha sonra bütçe, gelir ve harcama analizlerinde kullanılır.

Projenin amacı, kullanıcıların günlük harcamalarını daha düzenli takip edebilmesini ve bütçelerini daha bilinçli yönetebilmesini sağlamaktır.


## Temel Özellikler

* Fiş ve fatura görseli yükleme
* Tesseract OCR ile metin çıkarma
* Yapay zekâ destekli veri düzeltme
* Kullanıcı doğrulama ekranı
* Tekrarlı fiş kontrolü
* Kategori bazlı harcama analizi
* Aylık bütçe yönetimi
* Gelir takibi
* Abonelik takibi
* AI finans asistanı
* Açık / Koyu tema desteği


## Kullanılan Teknolojiler

* Python
* Flask
* SQLite
* HTML
* CSS
* JavaScript
* OpenCV
* Tesseract OCR
* OpenAI API
* Chart.js


## Sistem Çalışma Mantığı

```text
Fiş/Fatura Görseli
        ↓
Görüntü Ön İşleme
        ↓
Tesseract OCR
        ↓
Kural Tabanlı Ayrıştırma
        ↓
Yapay Zekâ Destekli Düzeltme
        ↓
Kullanıcı Doğrulaması
        ↓
Veritabanına Kayıt
        ↓
Bütçe ve Harcama Analizi
```

Sistemde belge okuma işlemi Tesseract OCR ile başlar. Yapay zekâ ise OCR çıktısını düzenlemek, eksik veya hatalı alanları iyileştirmek, kategori tahmini yapmak ve finansal yorum üretmek amacıyla destekleyici katman olarak kullanılır.

## Güvenlik

* Kullanıcı şifreleri hashlenerek saklanır.
* Her kullanıcı yalnızca kendi verilerine erişebilir.
* API anahtarları `.env` dosyasında tutulur.

## Kurulum

Gerekli paketleri yükleyin:

```bash
pip install -r requirements.txt
```

`.env.example` dosyasını örnek alarak `.env` dosyasını oluşturun.

Uygulamayı çalıştırın:

```bash
python app.py
```

Tarayıcıdan:

```text
http://127.0.0.1:5001
```

adresine giderek uygulamayı kullanabilirsiniz.


## Test Edilen Belgeler

Sistem aşağıdaki belge türleri ile test edilmiştir:

* Market fişi
* Restoran fişi
* Elektrik faturası
* Teknoloji mağazası fişi


## Bilinen Sınırlılıklar

* OCR başarısı yüklenen görselin kalitesine bağlıdır.
* Eğik veya düşük çözünürlüklü belgelerde bazı alanlar hatalı okunabilir.
* Bu nedenle kayıt öncesinde kullanıcı doğrulama ekranı bulunmaktadır.


## Gelecek Geliştirmeler

* Ürün bazlı fiyat analizi
* PDF ve Excel raporları
* Mobil uygulama desteği
* Banka entegrasyonu
* Gelişmiş bütçe tahmin sistemi


## Sonuç

AkıllıCüzdan; OCR, yapay zekâ destekli veri işleme, bütçe yönetimi ve kişisel finans takibini tek bir platformda bir araya getiren bir web uygulamasıdır. Proje, kullanıcıların harcamalarını daha düzenli takip edebilmelerini ve finansal durumlarını daha bilinçli yönetebilmelerini amaçlamaktadır.
