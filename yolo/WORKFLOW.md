# Robot Workflow

Bu dosya robotun mevcut calisma akisini net ve guncel haliyle ozetler.

## Genel Mimari

Sistem 3 ana parcadan olusur:

1. `yolo/detect.py`
   Kamera goruntusunu alir, hedef objeyi tespit eder ve hareket komutu uretir.
2. `esp32/CameraWebServer/CameraWebServer.ino`
   Hem kamera yayini saglar hem de Python ile Arduino arasinda kopru olur.
3. `arduino/arduino.ino`
   Motorlari ve ultrasonik mesafe sensorunu yonetir.

Kisaca veri akisi:

- ESP32-CAM kameradan goruntuyu yayina verir.
- `detect.py` bu yayini izler ve YOLO ile hedef objeyi arar.
- `detect.py` komutu TCP ile ESP32'ye gonderir.
- ESP32 gelen komutu seri hat uzerinden Arduino'ya iletir.
- Arduino motorlari surer.
- Arduino mesafe engeli varsa bunu `<B1>` olarak geri yollar.
- Engel kalkinca `<B0>` yollar.
- ESP32 bu geri bildirimi tekrar Python tarafina iletir.

## Kullanilan Komutlar

- `F`: ileri git
- `L`: sola don
- `R`: saga don
- `T`: arama donusu yap
- `S`: dur

Arduino tarafinda `T`, sabit hizli arama icin sola donus olarak uygulanir.

## 1. Baslangic

`detect.py` calistiginda:

- YOLO modeli yuklenir.
- ESP32 komut soketine baglanilir.
- Kamera stream'i acilir.
- Web arayuzunden hedef sinif ve confidence degeri okunur.

Varsayilan hedef sinif `bottle`'dir.

## 2. Hedef Gorunmuyorsa: Arama Modu

Robot hedef objeyi gormuyorsa arama moduna girer.

Arama davranisi kesiklidir:

- Bir sure doner.
- Bir sure durur.
- Dururken yeni frame'i kontrol eder.
- Hala hedef yoksa tekrar doner.

Bu davranis iki nedenle var:

- Donus hizi daha kontrol edilebilir olur.
- YOLO'nun temiz frame gormesi kolaylasir.

Ana parametreler:

- `YOLO_SEARCH_TURN_SECONDS = 0.35`
- `YOLO_SEARCH_PAUSE_SECONDS = 0.25`

## 3. Hedef Gorulurse: Ortalama Modu

Hedef obje gorulunce en buyuk uygun bounding box secilir.

Sonra obje merkezi ile frame merkezi karsilastirilir:

- Obje sola kacmis ise `L`
- Obje saga kacmis ise `R`
- Yeterince merkezde ise ileri gitmeye aday

Yatay merkez toleransi su anda:

- `YOLO_CENTER_TOLERANCE_X_RATIO = 0.18`

Bu, goruntunun orta bolgesinde yaklasik `%36`lik toplam bir kabul alani demektir.

Dikey tolerans:

- `YOLO_CENTER_TOLERANCE_Y_RATIO = 0.16`

Eger obje goruntude asiri asagidaysa sistem bunu "fazla yakin olabilir" gibi yorumlayip ileri gitmek yerine durabilir.

## 4. Merkez Onayi

Robot objeyi bir frame'de merkezde gordu diye hemen ileri gitmez. Kisa bir merkez onayi yapar.

Mevcut mantik:

- Son `5` frame icinde merkezde sayilan frame'ler tutulur.
- Bunlardan en az `3` tanesi merkezde ise obje yeterince ortalandi kabul edilir.

Parametreler:

- `YOLO_CENTER_CONFIRM_WINDOW = 5`
- `YOLO_CENTER_CONFIRM_FRAMES = 3`

Bu kisim yalanci merkezlenmeleri azaltir.

## 5. Ileri Gitme

Merkez onayi alindiginda `F` komutu gonderilir.

Bu noktadan sonra:

- Robot objeye dogru ilerler.
- Obje kamerada buyuyup kadrajdan tasssa bile robot hemen aramaya donmez.
- Ultrasonik sensor durdurana kadar ileri gitmeye devam edebilir.

Bu davranis `approach_locked` mantigi ile yapilir.

Ama bu kilit su durumlarda sifirlanir:

- Arduino mesafe engeli bildirirse
- Robot yeniden ciddi sekilde saga/sola duzeltme ihtiyaci gorurse

## 6. Ortalarken Obje Kaybolursa

En kritik kisimlardan biri budur.

Eskiden robot objeyi ortalamaya calisirken obje birkac frame kaybolunca hemen aramaya geciyordu. Bu da gereksiz donuse neden oluyordu.

Su anki davranis:

1. Hedef yeni kaybolduysa hemen aramaya gecmez.
2. Kisa bir sure durup objenin yeniden gorunmesini bekler.
3. Gerekirse son gorulen konuma gore minicik bir hafiza duzeltmesi yapar.
4. Obje geri gelirse tekrar ortalamaya devam eder.
5. Hala gorunmezse normal arama moduna duser.

Parametreler:

- `YOLO_TARGET_REACQUIRE_HOLD_SECONDS = 0.45`
- `YOLO_REACQUIRE_NUDGE_SECONDS = 0.08`

Buradaki mantik:

- `REACQUIRE HOLD`: bir anlik kayipta bekle
- `REACQUIRE NUDGE`: son gorulen yone cok kisa ters/duzeltme hareketi yap

Ornek:

- Robot saga donerek ariyordu.
- Objeyi gordu ama biraz fazla dondu.
- Obje son anda frame'in solunda kaldi.
- Sistem cok kisa bir `L` verip tekrar objeyi yakalamaya calisir.

## 7. Donus Tersine Donerse

Robot bir anda `L`'den `R`'ye veya `R`'den `L`'ye atlamasin diye bir filtre vardir.

Bu filtre:

- Yeni yonu birkac frame boyunca gormeyi bekler.
- Kisa bir duraklama ister.
- Dogrulanmadan yon degistirmez.

Parametreler:

- `YOLO_TURN_REVERSAL_CONFIRM_FRAMES = 3`
- `YOLO_TURN_REVERSAL_STOP_SECONDS = 0.15`

Bu sayede tek frame'lik hatalar ani yon degisimi yaratmaz.

## 8. Track Donusleri Nasil Calisiyor

Objeyi sola veya saga alirken donus de kesiklidir:

- Kisa sure don
- Kisa sure dur
- Yeni frame'e bak

Parametreler:

- `YOLO_TRACK_TURN_SECONDS = 0.12`
- `YOLO_TRACK_PAUSE_SECONDS = 0.15`

Bu davranis, robot hareket halindeyken bulanık frame yuzunden objeyi kacirmamaya yardim eder.

## 9. Mesafe Sensoru Her Seyden Once Gelir

Arduino uzerindeki HC-SR04 sensoru guvenlik katmanidir.

Arduino:

- Mesafeyi surekli olcer.
- Mesafe `20 cm` ve altina inerse engel var kabul eder.
- Motorlari durdurur.
- Python tarafina `<B1>` gonderir.

Mesafe tekrar guvenli seviyeye ciktiginda:

- `25 cm` ustune cikarsa engel kalkmis sayilir.
- Arduino `<B0>` yollar.

Parametreler:

- `stopDistanceCm = 20.0`
- `resumeDistanceCm = 25.0`

Onemli nokta:

- Hedef hala gorunuyor olsa bile mesafe esigi gecildiysa robot durur.
- Python tarafi da bunu gorunce ileri gitme kilidini ve merkez bilgisini sifirlar.

## 10. Komut Onceligi

Pratikte komut onceligi su sekildedir:

1. Mesafe engeli varsa `S`
2. Hedef ortalanmis ve yaklasma kilidi aktifse `F`
3. Hedef gorunuyorsa `L` veya `R` ile ortalama
4. Hedef yeni kaybolduysa `REACQUIRE HOLD` veya `REACQUIRE NUDGE`
5. Hedef uzun sure yoksa `T` ile arama

## 11. ESP32'nin Gorevi

ESP32-CAM iki is yapar:

- Kamera stream'ini verir
- Python ile Arduino arasinda seri/TCP koprusu olur

Kopru mantigi basittir:

- TCP'den gelen byte'i `Serial` ile Arduino'ya yollar
- Arduino'dan gelen byte'i TCP istemcisine geri yollar

Yani karar mantigi ESP32'de degil, Python ve Arduino tarafindadir.

## 12. Arduino'nun Gorevi

Arduino karar vermez, uygulama ve guvenlik katmani gibi davranir.

Yaptigi isler:

- Gelen `F/L/R/S/T` komutunu uygular
- Motor hizlarini ayarlar
- Mesafe sensorunu okur
- Engel varsa motoru keser
- Bu bilgiyi geri bildirir

Mevcut hizlar:

- `forwardSpeed = 120`
- `searchTurnSpeed = 110`
- `trackTurnSpeed = 110`

## 13. Sistemin Ozet Davranisi

Tek cumlede sistemin mantigi:

"Robot once objeyi arar, bulunca makul sekilde ortalar, yeterince ortaladiginda ileri gider, objeyi kisa sure kaybederse hemen panik donusu yapmaz, ama mesafe sensoru tehlike derse her seyi birakir ve durur."

## 14. Ince Ayar Icin En Onemli Parametreler

Davranisi en cok etkileyen parametreler bunlardir:

- `YOLO_CENTER_TOLERANCE_X_RATIO`
- `YOLO_CENTER_CONFIRM_FRAMES`
- `YOLO_CENTER_CONFIRM_WINDOW`
- `YOLO_TRACK_TURN_SECONDS`
- `YOLO_TRACK_PAUSE_SECONDS`
- `YOLO_SEARCH_TURN_SECONDS`
- `YOLO_SEARCH_PAUSE_SECONDS`
- `YOLO_TARGET_REACQUIRE_HOLD_SECONDS`
- `YOLO_REACQUIRE_NUDGE_SECONDS`
- `stopDistanceCm`
- `resumeDistanceCm`

## 15. Sahada Gorulebilecek Tipik Problemler

### Robot objeyi gorur gormez ileri gidiyor

Muhtemel nedenler:

- Merkez toleransi fazla genistir
- Merkez onayi fazla zayiftir

### Robot objeyi ortalarken kaybediyor

Muhtemel nedenler:

- Track turn suresi fazla uzundur
- Track pause suresi kisadir
- Reacquire bekleme suresi kucuktur

### Robot objeyi gordukten sonra ters yone kiriyor

Muhtemel nedenler:

- Son gorulen merkez ciddi sekilde kaymistir
- Donus tersine cevirme mantigi yeterli degildir
- Motor mekanigi sag ve solda esit degildir

### Robot durmasi gerekirken ileri zorlamaya devam ediyor

Kontrol edilmesi gerekenler:

- Arduino'dan `<B1>` geri bildirimi geliyor mu
- ESP32 bu bilgiyi Python'a geri geciyor mu
- Ultrasonik sensor dogru mesafe olcuyor mu

