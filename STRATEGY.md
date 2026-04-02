# Claw Code — Product Strategy & Roadmap

## Vision

Bu repo (claw-code), Claude Code'un agent harness mimarisinin Python'a portlanmis hali.
Icindeki 32 alt sistem, 180 komut ve 150 arac envanteri, agent sistemlerinin nasil
calistigini anlamak icin essiz bir veri kaynagi.

Bu strateji dokumani, bu veri ve mimari uzerine insa edilebilecek **3 urun** icin
yol haritasi ciziyor.

---

## Urun 1: HarnessKit (Acik Kaynak)

**Tek cumle:** No-code arayuzle kendi AI agent harness'ini kur.

### Problem
Herkes kendi AI agent'ini kurmak istiyor ama harness muhendisligi (tool wiring,
permission, session management, bootstrap) cok teknik. Teknik olmayan insanlar
bu karmasiklikla bas edemiyor.

### Cozum
Kullanici bir konfigurasyon akisindan geciyor:
- Hangi araclara erisebilsin? (tools.py envanterinden sec)
- Hangi izinler olsun? (permissions.py modelinden tanimla)
- Nasil baslasin? (bootstrap_graph.py asamalarindan sec)
- Hangi model kullansin? (Claude, GPT, Gemini, vb.)

Sistem bu cevaplardan calisan bir agent konfigurasyon dosyasi uretiyor.

### Repodaki Temel Parcalar
| Repo Dosyasi | HarnessKit'teki Rolu |
|---|---|
| `src/tools.py` + `reference_data/tools_snapshot.json` | Arac katalogu — kullanici buradan secer |
| `src/commands.py` + `reference_data/commands_snapshot.json` | Komut katalogu — kullanici buradan secer |
| `src/permissions.py` | Izin sablonu — deny-list tabanli erisim kontrolu |
| `src/bootstrap_graph.py` | Baslangic asamalari — kullanici pipeline'ini tasarlar |
| `src/tool_pool.py` | Arac havuzu montaji — simple_mode, mcp secenekleri |
| `src/models.py` | Veri modelleri — Subsystem, PortingModule yapilari |
| `src/port_manifest.py` | Manifest uretici — konfigurasyon ciktisi sablonu |

### Yol Haritasi
**Faz 1 — Temel (Hafta 1-2)**
- [ ] Tool ve command katalogunu JSON API olarak sunma
- [ ] Basit bir CLI wizard: `harnesskit init` komutuyla interaktif kurulum
- [ ] Cikan konfigurasyon dosyasini YAML/JSON olarak export etme
- [ ] GitHub'da acik kaynak olarak yayinlama, README + ornekler

**Faz 2 — Web Arayuzu (Hafta 3-4)**
- [ ] Basit bir web UI (Streamlit, Gradio veya Next.js)
- [ ] Drag-and-drop tool secimi
- [ ] Bootstrap pipeline gorsel editoru
- [ ] Permission rule builder

**Faz 3 — Topluluk (Hafta 5-8)**
- [ ] Kullanicilarin kendi konfigurasyon sablonlarini paylasabildigi "template gallery"
- [ ] GitHub Actions entegrasyonu — repo'ya push edince agent otomatik deploy
- [ ] Discord toplulugu + dokumantasyon sitesi

### Gelir Modeli
Acik kaynak (ucretsiz). Itibar ve topluluk kazanimi.
Premium ozellikler (hosted deployment, team management) ileriki fazlarda eklenir.

---

## Urun 2: AgentBlackBox (SaaS)

**Tek cumle:** AI agent'larinin kara kutusu — her karari kaydet, analiz et, raporla.

### Problem
Sirketler AI agent kullaniyor ama "agent neden bu karari verdi?" sorusuna cevap
veremiyorlar. Compliance, audit ve guvenlik ekipleri icin bu buyuk bir kara delik.

### Cozum
Agent'in her hareketini kaydeden ve sonradan analiz edilebilir hale getiren bir sistem:
- Hangi araclar mevcuttu o anda?
- Hangi komut zincirinden gecti?
- Permission reddedildi mi? Nerede?
- Kac token harcandi?
- Kullanici ne sordu, agent ne anladi?

Sonra bunlari dashboard'da gosteriyor: timeline gorunumu, maliyet dagilimi,
hata analizi, permission ihlalleri.

### Repodaki Temel Parcalar
| Repo Dosyasi | AgentBlackBox'taki Rolu |
|---|---|
| `src/transcript.py` | Mesaj gecmisi kaydi — append, compact, replay |
| `src/history.py` | Oturum olay kaydi — HistoryEvent, milestone tracking |
| `src/cost_tracker.py` | Token/maliyet muhasebesi |
| `src/costHook.py` | Maliyet hook'u — her islemde maliyet yakala |
| `src/permissions.py` | Izin ihlali kaydi — neye izin verildi, ne reddedildi |
| `src/session_store.py` | Oturum saklama — JSON persistance |
| `src/execution_registry.py` | Komut/arac calisma kaydi — ne ne zaman calistirildi |
| `src/query.py` | Istek/cevap veri yapisi |

### Yol Haritasi
**Faz 1 — Kayit Motoru (Hafta 1-3)**
- [ ] transcript.py ve history.py'i birlestiren unified log formati
- [ ] Agent-agnostik SDK: Claude Code, Cursor, Codex CLI icin adapter'lar
- [ ] Her olay icin zaman damgasi, token sayisi, arac adi, sonuc kaydi

**Faz 2 — Dashboard (Hafta 4-6)**
- [ ] Web dashboard: timeline gorunumu, filtreler, arama
- [ ] Oturum bazli maliyet dagilimi grafikleri
- [ ] Permission ihlali uyarilari
- [ ] "Bu oturumda ne oldu?" tek sayfa ozeti

**Faz 3 — Analiz ve Raporlama (Hafta 7-10)**
- [ ] "Agent neden bu karari verdi?" soru-cevap motoru (kayitlar uzerinde LLM analizi)
- [ ] Haftalik/aylik rapor uretimi (PDF/email)
- [ ] Anomali tespiti — beklenmedik davranislari otomatik isaretleme
- [ ] Compliance export (SOC2, ISO uyumlu format)

### Gelir Modeli
- Free tier: 100 oturum/ay kayit
- Pro ($29/ay): Sinirsiz kayit + dashboard
- Enterprise ($199/ay): Analiz motoru + compliance raporlar + team management

---

## Urun 3: MirrorMode (AaaS — Agent as a Service)

**Tek cumle:** Bir agent'taki is akisini yakalayip baska bir agent'ta calistir.

### Problem
Takimlarda farkli insanlar farkli AI araclari kullaniyor (Claude Code, Cursor,
Codex CLI, Aider). Ayni is akisini her aracta sifirdan kurmak zaman kaybi.
Agent lock-in buyuk bir problem.

### Cozum
1. Kaynak agent'taki is akisini yakala (ornegin Claude Code'da bir refactoring akisi)
2. Adimlarini soyutla: "dosya oku → analiz et → degistir → test calistir → commit at"
3. Hedef agent'in diline cevir (Cursor'daki karsilik gelen araclar ve komutlar)
4. Ayni is akisini hedef agent'ta calistir

### Repodaki Temel Parcalar
| Repo Dosyasi | MirrorMode'daki Rolu |
|---|---|
| `src/commands.py` + `reference_data/commands_snapshot.json` | Komut sozlugu — kaynak taraf |
| `src/tools.py` + `reference_data/tools_snapshot.json` | Arac sozlugu — kaynak taraf |
| `src/command_graph.py` | Komut segmentasyonu — builtin/plugin/skill ayirimi |
| `src/execution_registry.py` | Calisma kaydi — hangi arac/komut ne zaman cagrildi |
| `src/transcript.py` | Akis kaydi — sirasiyla ne yapildi |
| `src/runtime.py` | Calisma motoru — route_prompt, bootstrap_session |
| `src/parity_audit.py` | Eslesme denetimi — iki sistem arasi kapsam karsilastirmasi |
| `src/remote_runtime.py` | Uzak calisma — farkli ortamlara baglanma |

### Yol Haritasi
**Faz 1 — Ceviri Sozlugu (Hafta 1-4)**
- [ ] Claude Code arac/komut envanterini referans olarak yapilandirma (zaten var)
- [ ] Cursor, Codex CLI, Aider icin ayni formatta envanter cikarma
- [ ] Araclar arasi eslestirme tablosu: "BashTool (Claude) = Terminal (Cursor) = Shell (Codex)"
- [ ] Eslestirme yuzdesini gosteren parity skoru

**Faz 2 — Akis Yakalama (Hafta 5-8)**
- [ ] Transcript formatini agent-agnostik hale getirme
- [ ] "Record" modu: calisan bir agent oturumunu yakalama
- [ ] Yakalanan akisi soyut adimlara donusturme (tool-agnostik temsil)

**Faz 3 — Akis Calistirma (Hafta 9-14)**
- [ ] Soyut akisi hedef agent diline cevirme
- [ ] "Play" modu: cevrilen akisi hedef agent'ta calistirma
- [ ] Basarisiz adimlarda fallback stratejisi
- [ ] API olarak sunma (AaaS)

### Gelir Modeli
- API bazli fiyatlandirma: her akis cevirisi icin kredi
- Free tier: 10 ceviri/ay
- Pro ($49/ay): 500 ceviri + oncelikli destek
- Enterprise: Ozel agent adapter gelistirme + SLA

---

## Urunler Arasi Sinerji

```
HarnessKit (Acik Kaynak)
    |
    | topluluk + itibar + kullanici tabani
    v
AgentBlackBox (SaaS)
    |
    | kayit verisi + agent davranis anlayisi
    v
MirrorMode (AaaS)
    |
    | agent-agnostik is akisi ekosistemi
    v
Platform vizyonu: Agent islemlerinin "ortak dili"
```

**Akis:**
1. HarnessKit ile acik kaynak topluluk olustur → itibar + erken kullanicilar
2. Topluluktan gelen geri bildirimle AgentBlackBox'i sat → gelir baslar
3. BlackBox'taki kayit verisiyle MirrorMode'un ceviri motorunu besle → buyuk vizyon

---

## Ilk Adim: Yarin Ne Yapilir?

1. Bu repoyu duzenle: README'ye HarnessKit vizyonunu ekle
2. `src/tools.py` ve `src/commands.py`'daki kataloglari API-ready JSON olarak sun
3. Basit bir `harnesskit init` CLI wizard'i yaz
4. GitHub'da acik kaynak olarak yayinla
5. Twitter/X'te paylasim yap, topluluk toplamaya basla

---

*Bu doküman claw-code reposunun mevcut yapisini analiz ederek olusturulmustur.*
*Son guncelleme: 2026-04-01*
