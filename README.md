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

Es gibt drei Wege zu Verbrauchsdaten — eigene CSV hochladen, einen vorhandenen
Beispiel-Datensatz wählen, oder ein Verbrauchsszenario zusammenstellen — danach führt
die Anwendung durch dieselben weiteren Schritte:

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

### Oder: Verbrauchsszenario zusammenstellen

Wer weder eigene Messdaten noch einen passenden Beispiel-Haushalt hat, stellt sich
stattdessen ein Szenario aus einer vorberechneten Profilbibliothek zusammen (Haushaltstyp,
Jahresverbrauch, E-Auto, Wärmepumpe, PV, verschiebbare Lasten) — siehe eigener Abschnitt
[„Verbrauchsszenario"](#verbrauchsszenario-dritte-datenquelle-neben-upload-und-beispiel-haushalt)
weiter unten. Auch dieser Weg überspringt Schritt 1+2.

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

### Datensatz spenden

Wurde eine eigene CSV importiert (nicht bei Auswahl eines Beispiel-Haushalts), erscheint
nach Schritt 1 ein Button „Datensatz spenden“. Damit lässt sich der bereits auf
Stundenwerte verdichtete, anonymisierte Verbrauch (keine Namen o.ä.) zusammen mit den
sieben Haushaltseigenschaften per E-Mail an Lukas schicken. Jede Spende wird von Hand
geprüft und erst danach über `scripts/process_examples.py` regulär aufgenommen — siehe
[„E-Mail-Versand für Datenspenden einrichten"](#e-mail-versand-für-datenspenden-einrichten-resend)
weiter unten.

## Verbrauchsszenario (dritte Datenquelle neben Upload und Beispiel-Haushalt)

Direkt unter „Oder: vorhandenen Datensatz wählen“ gibt es einen dritten Weg zu
Verbrauchsdaten: **„Oder: Verbrauchsszenario zusammenstellen“**. Wer weder eigene
Messdaten noch einen passenden Beispiel-Haushalt hat, wählt hier stattdessen einen
Haushaltstyp aus einer vorberechneten Profilbibliothek, passt Jahresverbrauch,
Zusatzverbraucher (E-Auto, Wärmepumpe, PV) und den Anteil verschiebbarer Lasten an und
klickt „Dieses Szenario verwenden“. Danach läuft der Wizard **exakt wie bei einem
CSV-Import oder Beispiel-Haushalt weiter**: Übersicht über die getroffene Auswahl,
Schritt 3 (Tarife konfigurieren), Schritt 4 (Ergebnis mit echten aWATTar-Preisen).

### Architektur

- Die eigentlichen Verbrauchs-/Erzeugungsprofile (Haushaltstypen, PV, Wärmepumpe,
  E-Auto) liegen als **vorberechnete, statische JSON-Dateien** unter `static/data/` —
  erzeugt von den Offline-Skripten unter `tools/` (siehe unten), nicht zur Laufzeit.
- `app/scenario/builder.py` liest diese Dateien beim Aufruf von `POST
  /api/scenario/build` vom Server-Dateisystem, kombiniert sie gemäß der gewählten
  Parameter zu einer **stundengenauen Verbrauchsreihe für ein reales, abgeschlossenes
  Kalenderjahr** (aktuell das letzte volle Kalenderjahr) und legt sie in der Session ab
  — identisch zu dem, was `import_routes.py`/`examples_routes.py` für Upload bzw.
  Beispiel-Haushalt tun. Ab hier gibt es serverseitig keinen Unterschied mehr: `POST
  /api/calculate` holt für den Zeitraum ganz normal echte aWATTar-Preise und vergleicht
  die konfigurierten Tarife (`calculation/cost.py`, unverändert).
- Damit bekommt das Szenario automatisch alle bestehenden Ergebnis-Ansichten (Kennzahlen,
  bester/schlechtester Tag, Monats-/Tages-Chart) ohne jeden zusätzlichen Code.
- Je Haushaltstyp gibt es 3 unterschiedlich simulierte Varianten ("Seeds") aus der
  Profilbibliothek — für den konkreten Tarifvergleich wird daraus ein einzelner,
  gemittelter Verlauf gebildet (kein Bandbreiten-Konzept mehr, da das bestehende
  Ergebnis-UI auf einem einzelnen Verbrauch pro Tarifvergleich aufbaut).

### Bekannte vereinfachende Annahmen

- PV-Überschuss wird **nicht vergütet** (nur Eigenverbrauch reduziert die Stromrechnung).
- E-Auto-Verbrauch: pauschal 0,18 kWh/km.
- Verschiebbare Lasten und preisgesteuertes E-Auto-Laden werden pauschal in die
  Nachtstunden 00–06 Uhr verlagert (generische Annäherung an „günstige Stunden“) — zum
  Zeitpunkt der Szenario-Erstellung ist noch kein Tarif gewählt, eine echte
  Preisoptimierung ist hier also nicht möglich. Ob sich die Verlagerung auszahlt, zeigt
  der anschließende Tarifvergleich mit dem dynamischen Tarif in Schritt 3/4.
- Wärmepumpen-Profil basiert auf einer vereinfachten Gradtagszahl-Logik mit einem
  synthetischen Temperaturjahr, nicht auf einem echten TRY-Datensatz.
- Das Verbrauchsmuster ist ein *generisches* synthetisches Jahr, das nur positionsweise
  (Stunde des Jahres) auf das reale Vergleichsjahr gelegt wird — nicht wochentagsgenau
  kalibriert. Für einen kalendergenauen historischen Vergleich mit echten eigenen
  Messdaten bleiben CSV-Upload bzw. Beispiel-Haushalt das richtige Werkzeug.

### Die Profil-Pipeline lokal ausführen

Alle Generierungs-Skripte liegen unter `tools/` und laufen **nicht** auf Render — sie
erzeugen einmalig die Dateien unter `static/data/`, die dann ganz normal mit committet
und deployed werden.

```
tools/
  profile_shared.py                          Gemeinsames Format (15-Min-Raster, Normierung auf 1000 kWh/Jahr, JSON-Export)
  household_types.py                          Die 7 Haushaltstypen + Metadaten (Anzeigename, Vorschlagsverbrauch)
  generate_household_profiles_placeholder.py  Haushaltsprofile, SYNTHETISCH (einzige Quelle für Haushaltsprofile)
  generate_addon_profiles.py                   PV (PVGIS), Wärmepumpe (Gradtagszahl-Logik), E-Auto (ungesteuert/Platzhalter)
```

**Aktueller Stand:** `static/data/profiles/*.json` enthält **synthetische Platzhalterprofile**
(erzeugt von `generate_household_profiles_placeholder.py`) — plausible, unterscheidbare
Tagesverläufe je Haushaltstyp, handmodelliert, keine echte verhaltensbasierte Simulation. Die
Zusatzprofile (`static/data/addons/`) sind bereits mit echten PVGIS-Daten (PV) befüllt.

Um die Zusatzprofile neu zu erzeugen (z.B. für einen anderen PV-Standort):

```bash
python tools/generate_addon_profiles.py
```

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

## E-Mail-Versand für Datenspenden einrichten (Resend)

Der „Datensatz spenden"-Button verschickt eine E-Mail über [Resend](https://resend.com)
(kostenloser Tarif reicht). Ohne Konfiguration meldet der Button einen klaren Fehler,
die restliche App funktioniert davon unabhängig weiter.

1. Kostenlosen Account auf [resend.com](https://resend.com) anlegen (die Adresse, mit
   der man sich registriert, ist automatisch als Empfänger im Sandbox-Modus nutzbar —
   keine Domain-Verifizierung nötig, solange nur an diese eine Adresse verschickt wird).
2. Im Resend-Dashboard einen **API-Key** erstellen.
3. Folgende Umgebungsvariablen setzen (lokal vor dem Start exportieren, auf Render unter
   „Environment" im Dashboard des Service eintragen — **niemals** in den Code oder nach
   git committen):
   - `RESEND_API_KEY` — der erstellte API-Key.
   - `DONATION_EMAIL_TO` — die Empfänger-Adresse (i.d.R. die eigene Resend-Konto-Adresse).
   - `DONATION_EMAIL_FROM` — optional, Standard ist `onboarding@resend.dev` (Resends
     Test-Absender, funktioniert ohne eigene Domain).

Lokal zum Testen (Git Bash):
```bash
export RESEND_API_KEY="re_xxx"
export DONATION_EMAIL_TO="deine@adresse.de"
uvicorn app.main:app --reload
```

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
  scenario/
    builder.py              Baut aus den Profilen unter static/data/ eine reale Stundenreihe fürs Szenario
  pricing/
    awattar.py             aWATTar-API-Client
  calculation/
    cost.py                 Kostenvergleich, Tages-/Extremtag-Auswertung
  notifications/
    email.py                Versand gespendeter Datensätze per E-Mail (Resend-API)
  routes/
    import_routes.py        POST /api/import/upload, /api/import/confirm
    calculate_routes.py      POST /api/calculate
    examples_routes.py        GET /api/examples, POST /api/examples/{id}/select
    scenario_routes.py         GET /api/scenario/households, POST /api/scenario/build
    donation_routes.py        POST /api/donate
examples/
  raw/                      private CSV-Rohexporte (nicht committed)
  processed/                 registry.csv + data/<id>.csv (committed, bereits aggregiert)
scripts/
  process_examples.py        privates Offline-Skript (nicht committed)
tools/                        Offline-Profilpipeline fürs Verbrauchsszenario, läuft NICHT auf Render (siehe eigener Abschnitt oben)
static/
  index.html                Frontend-Markup (Upload/Beispiel/Szenario -> Mapping -> Tarife -> Ergebnis)
  css/style.css              Styling (hell/dunkel automatisch je nach Systemeinstellung)
  js/app.js                  Wizard-Logik, API-Calls, Ergebnis-Rendering
  js/charts.js                Chart.js-Aufbau für das Kosten-Säulendiagramm
  vendor/chart.umd.min.js      lokal eingebundenes Chart.js (kein CDN nötig)
  data/                       vorberechnete, statische Profile, von app/scenario/builder.py gelesen (siehe oben)
    profiles_index.json          Metadaten der Haushaltstypen
    profiles/<typ>__seed<n>.json  Haushaltsverbrauch, 15-Min-Raster, normiert auf 1000 kWh/Jahr
    addons/                        PV, Wärmepumpe, E-Auto (ungesteuert/Platzhalter für gesteuert)
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
  id="tarifcheck-iframe"
  src="https://DEINE-BACKEND-ADRESSE"
  style="width:100%; max-width:960px; border:0;"
  loading="lazy"
  title="Dynamischer Tarif Check">
</iframe>
<script>
  window.addEventListener('message', function (event) {
    if (!event.data || event.data.source !== 'dynamischer-tarif-check') return;
    var iframe = document.getElementById('tarifcheck-iframe');
    if (!iframe) return;
    if (event.data.height) iframe.style.height = event.data.height + 'px';
    if (event.data.action === 'scrollIntoView') {
      iframe.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
</script>
```

- `src` durch die tatsächliche Adresse aus Variante A oder B ersetzen.
- Eine feste `height` wird bewusst **nicht** gesetzt: `static/js/app.js` meldet die
  aktuelle Inhaltshöhe der Seite per `postMessage` an die Elternseite (bei jeder
  Größenänderung, z.B. neuer Schritt eingeblendet oder Ergebnis mit Chart geladen), das
  kleine Script oben übernimmt sie dann auf das `<iframe>` — es wächst/schrumpft also
  automatisch mit dem Inhalt, keine Scrollleiste im iframe nötig.
- Bei jedem Schrittwechsel (z.B. Klick auf „Beispiel-Haushalt wählen“) schickt die App
  zusätzlich eine `scrollIntoView`-Nachricht, da `scrollIntoView()` innerhalb des iframes
  selbst nichts bewirkt, wenn das iframe (wie hier) keinen eigenen Scrollbereich hat --
  das Script oben scrollt dann stattdessen die Elternseite zum iframe.
- Sind mehrere Instanzen des iframes auf derselben Seite eingebunden, braucht jedes eine
  eigene `id`, und das Script oben entsprechend einmal pro `id` (oder per
  `event.source === iframe.contentWindow`-Abgleich statt fester `id`, falls dynamisch
  mehrere iframes vorkommen).
- Die Seite, die das iframe einbindet, muss ebenfalls über HTTPS laufen, sonst blockieren
  Browser die Einbindung als „Mixed Content“.

## Bekannte Grenzen (bewusst außerhalb des Umfangs)

- Kein Tibber- oder sonstiger Anbieter-Support, nur CSV-Import.
- Kein direkter Live-Abruf von einem Shelly-Gerät (nur CSV-Export).
- Keine Nutzerkonten/Authentifizierung. Sessions sind zufällige IDs ohne Login, was für
  eine kleine öffentlich eingebettete App ausreicht; Uploads sind auf 25 MB begrenzt, es
  gibt aber (noch) kein Rate-Limiting gegen absichtlichen Missbrauch.
