# Dynamischer Tarif Check

Lokale Webanwendung, um historisch zu simulieren, ob ein dynamischer Stromtarif
günstiger gewesen wäre als ein Fixtarif — auf Basis echter Day-Ahead-Börsenpreise
(aWATTar, Deutschland) und eigener Verbrauchsdaten aus einem CSV-Export (z.B. Shelly
Pro 3EM, Shelly EM oder ein anderes Smartmeter).

Alle Daten (CSV-Upload, Zwischenergebnisse) leben ausschließlich im Arbeitsspeicher
des Servers und werden nirgends dauerhaft gespeichert. Ein Neustart des Servers löscht
alles.

## Voraussetzungen

- Python 3.11 oder neuer
- Internetzugang beim Berechnen (Abruf der Börsenpreise von `api.awattar.de`)

## Installation

```bash
cd "Dynamischer Tarif Check"
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Starten

```bash
uvicorn app.main:app --reload
```

Danach im Browser öffnen: **http://localhost:8000**

`--reload` ist nur beim Entwickeln nötig (lädt Code-Änderungen automatisch neu); für
den normalen Gebrauch reicht `uvicorn app.main:app`.

## Bedienung

Es gibt zwei Wege zu Verbrauchsdaten — eigene CSV hochladen oder einen vorhandenen
Beispiel-Datensatz wählen — danach führt die Anwendung durch dieselben weiteren Schritte:

### 1. Verbrauchsdaten importieren

CSV-Datei hochladen. Die Spaltenstruktur muss nicht bekannt sein — die Anwendung
schlägt automatisch vor, welche Spalte den Zeitstempel enthält und welche den
Verbrauchswert.

### Oder: vorhandenen Datensatz wählen

Direkt unter dem Upload-Bereich werden alle kuratierten Beispiel-Haushalte angezeigt,
mit Haushaltsgröße und den vorhandenen Eigenschaften (Balkonkraftwerk, PV, Speicher,
Wärmepumpe, Durchlauferhitzer, Elektroauto — angezeigt wird jeweils nur, was zutrifft).
Kein Filtern/Matching — einfach den anklicken, der am ehesten passt, um mit dessen
Verbrauchsdaten weiterzurechnen und Schritt 1+2 zu überspringen. Diese Beispiel-Haushalte
werden von Lukas separat gepflegt, siehe
[„Beispiel-Haushalte pflegen"](#beispiel-haushalte-pflegen) weiter unten.

### 2. Spaltenzuordnung prüfen

Die Vorschläge aus Schritt 1 werden angezeigt und können korrigiert werden:

- **Zeitstempel-Spalte** — unterstützt ISO 8601, deutsches Format (`DD.MM.YYYY HH:mm[:ss]`)
  und Unix-Timestamps (Sekunden oder Millisekunden).
- **Werte-Spalte** — die Spalte mit den eigentlichen Messwerten.
- **Bedeutung der Werte-Spalte**, eine von vier Möglichkeiten:
  - *Momentanleistung (W)* — z.B. Shellys `Power`-Spalte.
  - *Energie pro Intervall (Wh)* oder *(kWh)* — Verbrauch seit der letzten Zeile.
  - *Kumulierter Zählerstand (kWh)* — ein aufsteigender Zählerwert; die Anwendung bildet
    selbst die Differenz zwischen den Zeilen und ignoriert Reset-Sprünge (z.B. bei
    Zählerwechsel).
- **Zeitzone** — wie die Zeitstempel zu interpretieren sind, falls sie keine
  Zeitzoneninfo enthalten (Standard: Europe/Berlin). Unix-Timestamps sind davon nicht
  betroffen, die sind immer eindeutig UTC.

Die Rohdaten werden unabhängig vom ursprünglichen Messintervall auf volle Stunden
aggregiert (anteilig verteilt, falls ein Messintervall eine Stundengrenze überschreitet).

Nach dem Bestätigen wird der ermittelte **Gesamtverbrauch groß angezeigt** — dieser Wert
sollte mit der eigenen Stromrechnung oder einer Zählerablesung für denselben Zeitraum
verglichen werden. Wirkt er nicht plausibel, oben einfach eine andere Spalte oder eine
andere Bedeutung der Werte-Spalte wählen und erneut bestätigen.

### 3. Tarife konfigurieren

Mindestens 2, maximal 8 Tarife, beliebig kombinierbar aus:

- **Fixtarif**: Arbeitspreis (ct/kWh) + Grundgebühr (€/Monat).
- **Dynamischer Tarif**: MwSt. auf den Spotpreis (%), Aufschlag (ct/kWh) für
  Netzentgelte/Marge, Grundgebühr (€/Monat). Der Preis pro Stunde ergibt sich aus:

  ```
  preis_ct_kwh = (spotpreis_eur_mwh / 10) * (1 + mwst / 100) + aufschlag_ct_kwh
  ```

Mit „+ Tarif hinzufügen“ lassen sich weitere Tarife zum Vergleich ergänzen (z.B. um
zwei unterschiedliche Angebote gegeneinander zu testen), Name und Typ sind pro Tarif
frei wählbar.

### 4. Ergebnis

- Gesamtkosten je Tarif über den kompletten Zeitraum, günstigster Tarif und Ersparnis
  gegenüber dem teuersten.
- **Bester/schlechtester Tag**: Vergleich der Kosten des *ersten* und *zweiten*
  konfigurierten Tarifs (Stunde für Stunde), immer aus Sicht des zweiten Tarifs —
  günstiger wird grün, teurer rot dargestellt.
- **Kosten im Vergleich**: Säulendiagramm, standardmäßig nach Monaten geclustert. Über
  „Tag“ lässt sich auf Tagesgranularität umschalten; dabei erscheinen Monats-Reiter, um
  durch die einzelnen Monate zu blättern.

Stunden, für die aWATTar keine Preisdaten liefert (z.B. weit in der Zukunft liegende
Zeiträume), werden bei allen Tarifen aus dem Vergleich ausgeschlossen und als Hinweis
ausgewiesen, damit alle Tarife auf derselben Verbrauchsbasis verglichen werden.

## Beispiel-Haushalte pflegen

Die Beispiel-Haushalte (Schritt 0) sind **kein** automatisches Feature — sie werden von
Hand über ein privates Offline-Skript gepflegt, das eigene (oder anderweitig verfügbare)
CSV-Exporte zu anonymisierten Beispielen verarbeitet.

- `examples/raw/` — hier eigene CSV-Rohexporte ablegen. Bleibt lokal, wird **nicht**
  committet (schon vorhandene `*.csv`-Regel in `.gitignore` greift hier zusätzlich zu
  einer expliziten `examples/raw/`-Ausnahme).
- `scripts/process_examples.py` — ebenfalls **nicht** committet (`.gitignore`). Wird
  lokal ausgeführt:
  ```bash
  python scripts/process_examples.py examples/raw/mein_export.csv
  ```
  Fragt Spaltenzuordnung (mit denselben automatischen Vorschlägen wie das Web-UI) und
  die sieben Haushaltseigenschaften interaktiv ab, rechnet den Verbrauch auf Stundenbasis
  um (identische Logik wie das Web-Backend) und zeigt den Gesamtverbrauch zur Kontrolle
  an, bevor gespeichert wird.
- Ergebnis landet in `examples/processed/` — **das** wird committet, da es keine
  Rohdaten mehr enthält, sondern nur noch aggregierte Stundenwerte + die sieben
  Eigenschaften:
  - `examples/processed/registry.csv` — eine Zeile pro Beispiel-Haushalt.
  - `examples/processed/data/<id>.csv` — Stundenwerte (`timestamp_utc,kwh`) je Haushalt.

Läuft die App, ohne dass `examples/processed/registry.csv` existiert (z.B. direkt nach
dem ersten Deployment), zeigt Schritt 0 einfach „noch keine Beispiel-Haushalte
hinterlegt" — der Upload-Weg funktioniert davon unabhängig immer.

## Projektstruktur

```
app/
  main.py                 FastAPI-App, bindet Router ein, liefert das Frontend aus
  schemas.py              Pydantic-Modelle für die API
  session_store.py        In-Memory-Sessions (kein Disk-Persist), TTL 2h
  importer/
    parsing.py            CSV einlesen, Spalten-/Typ-Erkennung, Zeitstempel-Parsing
    aggregation.py         Umrechnung in kWh + Verteilung auf Stundenraster
    examples.py             Lädt die kuratierten Beispiel-Haushalte (registry + Stundenwerte)
  pricing/
    awattar.py             aWATTar-API-Client
  calculation/
    cost.py                 Kostenvergleich, Tages-/Extremtag-Auswertung
  routes/
    import_routes.py        POST /api/import/upload, /api/import/confirm
    calculate_routes.py      POST /api/calculate
    examples_routes.py        GET /api/examples, POST /api/examples/{id}/select
examples/
  raw/                      private CSV-Rohexporte (nicht committed)
  processed/                 registry.csv + data/<id>.csv (committed, bereits aggregiert)
scripts/
  process_examples.py        privates Offline-Skript (nicht committed)
static/
  index.html                Frontend-Markup (Upload -> Mapping -> Tarife -> Ergebnis)
  css/style.css              Styling (hell/dunkel automatisch je nach Systemeinstellung)
  js/app.js                  Wizard-Logik, API-Calls, Ergebnis-Rendering
  js/charts.js                Chart.js-Aufbau für das Kosten-Säulendiagramm
  vendor/chart.umd.min.js      lokal eingebundenes Chart.js (kein CDN nötig)
Dockerfile                     für Deployment auf einem Python-fähigen Host (siehe unten)
```

## Deployment (z.B. für die Einbindung in WordPress per iframe)

WordPress selbst kann keinen Python-Code ausführen. Damit die App auf einer echten
Webseite eingebunden werden kann, muss dieses Backend irgendwo separat laufen und über
eine eigene HTTPS-Adresse erreichbar sein — WordPress bindet sie dann nur per `<iframe>`
ein (siehe unten). Zwei Wege dorthin:

### Variante A: eigener (V)Server mit SSH-Zugang

Falls der Hosting-Tarif SSH-Zugriff bietet (prüfen im Kundenmenü des Hosters, Stichwort
„SSH-Zugang“ oder „Root-Server“):

1. Projekt auf den Server kopieren (z.B. `git clone` nach dem Hochladen zu GitHub, oder
   per `scp`/FTP).
2. Dort wie unter „Installation“ beschrieben `venv` + `pip install -r requirements.txt`.
3. Dauerhaft laufen lassen, z.B. als `systemd`-Service:
   ```
   uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
4. Per nginx/Apache-Reverse-Proxy unter einer (Sub-)Domain erreichbar machen, z.B.
   `https://tarifcheck.deine-domain.de` → `http://127.0.0.1:8000`. Das übernimmt in der
   Regel automatisch auch das benötigte HTTPS-Zertifikat.

Falls Docker verfügbar ist, geht es einfacher über das mitgelieferte `Dockerfile`:

```bash
docker build -t dynamischer-tarif-check .
docker run -d -p 8000:8000 --name tarifcheck dynamischer-tarif-check
```
(Das Image wurde in dieser Umgebung nicht selbst gebaut/getestet, da hier kein Docker
verfügbar war — Dockerfile folgt aber dem Standardmuster für FastAPI/uvicorn und sollte
unverändert funktionieren.)

### Variante B: separater kostenloser/günstiger Python-Host

Falls der Hosting-Tarif nur klassisches Webhosting ist (PHP/MySQL, kein SSH, kein
eigener Prozess möglich — bei vielen günstigen Tarifen der Fall), läuft das Backend
stattdessen bei einem Anbieter, der Python-Apps direkt unterstützt, z.B. **Render**,
**Fly.io**, **Railway** oder **PythonAnywhere** (alle haben kostenlose oder sehr
günstige Einstiegsstufen für eine so kleine App). WordPress bleibt dabei komplett
unangetastet — das iframe zeigt einfach auf die dort vergebene Adresse
(z.B. `https://dynamischer-tarif-check.onrender.com`). Die meisten dieser Anbieter
erkennen das mitgelieferte `Dockerfile` automatisch und benötigen keine weitere
Konfiguration außer dem verknüpften Git-Repository.

### Einbindung in WordPress

Sobald das Backend unter einer HTTPS-Adresse erreichbar ist, in WordPress einen
„Benutzerdefiniertes HTML“-Block (oder den Code-Editor eines Beitrags/einer Seite)
einfügen:

```html
<iframe
  src="https://DEINE-BACKEND-ADRESSE"
  style="width:100%; max-width:960px; height:1400px; border:0;"
  loading="lazy"
  title="Dynamischer Tarif Check">
</iframe>
```

- `src` durch die tatsächliche Adresse aus Variante A oder B ersetzen.
- `height` ist ein fester Wert, da iframes sich nicht von selbst an ihren Inhalt
  anpassen. 1400px deckt die App bis zum vollständigen Ergebnis inkl. Chart ab; auf
  kleinen Bildschirmen entsteht dann innerhalb des iframes eine Scrollleiste. Wer ein
  automatisch mitwachsendes iframe möchte, kann später die kleine Bibliothek
  [iframe-resizer](https://github.com/davidjbradshaw/iframe-resizer) ergänzen — das ist
  bewusst nicht Teil dieser ersten Version, um die Komplexität gering zu halten.
- Die Seite, die das iframe einbindet, muss ebenfalls über HTTPS laufen, sonst blockieren
  Browser die Einbindung als „Mixed Content“.

## Bekannte Grenzen (bewusst außerhalb des Umfangs)

- Kein Tibber- oder sonstiger Anbieter-Support, nur CSV-Import.
- Kein direkter Live-Abruf von einem Shelly-Gerät (nur CSV-Export).
- Keine Nutzerkonten/Authentifizierung. Sessions sind zufällige IDs ohne Login, was für
  eine kleine öffentlich eingebettete App ausreicht; Uploads sind auf 25 MB begrenzt, es
  gibt aber (noch) kein Rate-Limiting gegen absichtlichen Missbrauch.
