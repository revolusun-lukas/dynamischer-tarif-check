/* Wizard-Logik: Upload -> Mapping bestätigen -> Tarife -> Ergebnis. */

const state = {
  sessionId: null,
  dataSource: null, // 'upload' | 'example' | 'scenario' -- steuert, ob das Spenden-Angebot erscheint
  comparePair: [], // die zwei im Ergebnis angeklickten Tarifnamen für den Tagesvergleich
  compareDays: { a: null, b: null }, // Datum des besten Tages je Tarif des Paars
};

const el = (id) => document.getElementById(id);

// Escaped Werte, die per Template-Literal in innerHTML landen (CSV-Inhalte, Tarifnamen) --
// ohne das koennte z.B. eine CSV-Spaltenueberschrift wie "<img src=x onerror=...>" als
// echtes HTML-Element gerendert werden statt als Text angezeigt zu werden.
function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/* ---------- Wizard-Schritte -- alle direkt auf der Seite als Kachel, kein Popup mehr
   (einziges "Fenster" ist noch der native Datei-Auswahl-Dialog des Browsers beim CSV-Upload),
   damit sich die Anwendung später auch sauber in ein Iframe einbetten lässt. ---------- */

const STEP_IDS = ['step-entry', 'modal-upload', 'modal-help', 'modal-examples', 'modal-scenario', 'modal-mapping', 'modal-tariffs', 'modal-results', 'modal-day-detail'];

function showStep(id) {
  STEP_IDS.forEach((s) => { el(s).hidden = (s !== id); });
  const target = el(id);
  // preventScroll, weil scrollIntoView direkt danach gezielter scrollt (z.B. bei sehr
  // hohen Kacheln reicht reines focus() sonst nicht, um den Anfang sichtbar zu machen).
  target.focus({ preventScroll: true });
  target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  // scrollIntoView wirkt nur innerhalb des eigenen Dokuments -- eingebettet in ein iframe
  // ohne eigenen Scrollbereich (siehe Höhen-Meldung weiter unten) scrollt das die
  // Elternseite nicht mit. Die Elternseite kann optional auf diese Nachricht reagieren.
  if (window.parent !== window) {
    window.parent.postMessage({ source: 'dynamischer-tarif-check', action: 'scrollIntoView' }, '*');
  }
}

document.querySelectorAll('[data-back-to]').forEach((btn) => {
  btn.addEventListener('click', () => showStep(btn.dataset.backTo));
});

/* ---------- AGB-Zustimmung (schaltet nur den CSV-Upload-Button frei -- Beispiel-Haushalt
   und Szenario nutzen keine eigenen hochgeladenen Daten und brauchen daher keine Zustimmung) ---------- */

el('agb-consent').addEventListener('change', () => {
  const accepted = el('agb-consent').checked;
  el('btn-open-upload').disabled = !accepted;
  el('btn-open-upload').title = accepted ? '' : 'Bitte zuerst den AGB oben zustimmen';
  el('upload-locked-note').hidden = accepted;
});

el('btn-open-upload').addEventListener('click', () => showStep('modal-upload'));
el('btn-open-help').addEventListener('click', () => showStep('modal-help'));

function showError(message) {
  const banner = el('error-banner');
  banner.textContent = message;
  banner.hidden = false;
  banner.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function clearError() {
  const banner = el('error-banner');
  banner.hidden = true;
  banner.textContent = '';
}

// Zeigt einen Lade-Spinner + Text im Button an, solange eine Anfrage läuft (Preisabruf
// bei aWATTar & Co. können ein paar Sekunden dauern) und stellt danach den Originaltext
// wieder her.
function setButtonLoading(button, isLoading, loadingText) {
  if (isLoading) {
    if (button.dataset.originalText === undefined) {
      button.dataset.originalText = button.textContent;
    }
    button.disabled = true;
    button.innerHTML = `<span class="btn-spinner"></span>${loadingText}`;
  } else {
    button.disabled = false;
    button.textContent = button.dataset.originalText ?? button.textContent;
  }
}

async function apiRequest(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch (networkErr) {
    throw new Error('Server nicht erreichbar. Läuft die Anwendung noch?');
  }
  if (!response.ok) {
    let detail = `Fehler (${response.status})`;
    try {
      const body = await response.json();
      if (body && body.detail) detail = body.detail;
    } catch (_) {
      /* ignore parse failure, keep generic message */
    }
    throw new Error(detail);
  }
  return response.json();
}

/* ---------- Beispiel-Haushalte (Alternative zum eigenen Upload) ---------- */

const EXAMPLE_PROPERTY_LABELS = {
  balkonkraftwerk: 'Balkonkraftwerk',
  pv: 'PV auf dem Dach',
  speicher: 'Batteriespeicher',
  waermepumpe: 'Wärmepumpe',
  durchlauferhitzer: 'Durchlauferhitzer',
  elektroauto: 'Elektroauto',
};

let allExamples = [];
let examplesLoaded = false;

async function loadExamples() {
  try {
    const data = await apiRequest('/api/examples', { method: 'GET' });
    allExamples = data.examples;
  } catch (err) {
    allExamples = [];
  }
  renderExampleResults();
}

el('btn-open-examples').addEventListener('click', async () => {
  showStep('modal-examples');
  if (!examplesLoaded) {
    examplesLoaded = true;
    await loadExamples();
  }
});

function renderExampleResults() {
  const container = el('example-results');

  if (allExamples.length === 0) {
    container.innerHTML =
      '<p class="example-empty-note">Noch keine Beispiel-Haushalte hinterlegt — bitte oben eigene Verbrauchsdaten hochladen.</p>';
    return;
  }

  container.innerHTML = allExamples
    .map((e) => {
      const trueProperties = Object.entries(EXAMPLE_PROPERTY_LABELS)
        .filter(([key]) => e[key])
        .map(([, label]) => `<li>${label}</li>`)
        .join('');
      return `
        <div class="example-card">
          <div class="example-card-title">Haushalt mit ${e.haushaltsgroesse} ${e.haushaltsgroesse === 1 ? 'Person' : 'Personen'}</div>
          <ul class="example-card-list">${trueProperties}</ul>
          <div class="example-card-meta">${formatDateOnly(e.start_date.slice(0, 10))} – ${formatDateOnly(e.end_date.slice(0, 10))} · ${e.total_kwh.toLocaleString('de-DE')} kWh</div>
          <button type="button" class="btn btn-secondary" data-example-id="${e.id}">Diesen verwenden</button>
        </div>`;
    })
    .join('');

  container.querySelectorAll('button[data-example-id]').forEach((btn) => {
    btn.addEventListener('click', () => useExample(btn.dataset.exampleId, btn));
  });
}

async function useExample(exampleId, btn) {
  clearError();
  setButtonLoading(btn, true, 'Wird geladen…');
  try {
    const data = await apiRequest(`/api/examples/${exampleId}/select`, { method: 'POST' });
    state.sessionId = data.session_id;
    state.dataSource = 'example';
    showImportSummary(data);
    el('btn-back-to-source').dataset.backTo = 'modal-examples';
    showStep('modal-tariffs');
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
}

/* ---------- Verbrauchsszenario (Alternative zu Upload/Beispiel-Haushalt) ---------- */

let scenarioHouseholds = [];
let scenarioHouseholdsLoaded = false;

async function loadScenarioHouseholds() {
  try {
    const data = await apiRequest('/api/scenario/households', { method: 'GET' });
    scenarioHouseholds = data.households;
  } catch (err) {
    scenarioHouseholds = [];
  }
  const select = el('scenario-household');
  select.innerHTML = scenarioHouseholds.map((h) => `<option value="${h.id}">${h.display_name}</option>`).join('');
  select.selectedIndex = scenarioHouseholds.length ? 0 : -1;
  updateScenarioHouseholdHint();
}

function selectedScenarioHousehold() {
  return scenarioHouseholds.find((h) => h.id === el('scenario-household').value);
}

function scenarioUsesOwnKwh() {
  return document.querySelector('input[name="scenario-kwh-source"]:checked')?.value === 'own';
}

function updateScenarioHouseholdHint() {
  const household = selectedScenarioHousehold();
  if (!household) return;
  el('scenario-household-description').textContent = household.description;
  el('scenario-typical-kwh').textContent = `${formatNum(household.typical_annual_kwh, 0)} kWh/Jahr`;
  // Ein selbst eingetragener Verbrauch bleibt beim Wechsel des Haushaltstyps erhalten.
  if (!scenarioUsesOwnKwh()) el('scenario-annual-kwh').value = household.typical_annual_kwh;
  updateScenarioSum();
}

el('scenario-household').addEventListener('change', updateScenarioHouseholdHint);

function updateScenarioKwhSource() {
  const own = scenarioUsesOwnKwh();
  el('scenario-own-kwh-row').classList.toggle('is-disabled', !own);
  el('scenario-annual-kwh').disabled = !own;
  if (own) el('scenario-annual-kwh').focus();
  else if (selectedScenarioHousehold()) el('scenario-annual-kwh').value = selectedScenarioHousehold().typical_annual_kwh;
  updateScenarioSum();
}
document.querySelectorAll('input[name="scenario-kwh-source"]').forEach((r) => r.addEventListener('change', updateScenarioKwhSource));

// Die Haushaltstypen werden erst beim Öffnen des Fensters geladen (nicht schon vorher
// in den noch versteckten Container hinein), damit das <select> nicht in einigen
// Browsern mit leerer Vorauswahl gerendert wird.
el('btn-open-scenario').addEventListener('click', async () => {
  showStep('modal-scenario');
  if (!scenarioHouseholdsLoaded) {
    scenarioHouseholdsLoaded = true;
    await loadScenarioHouseholds();
    updateScenarioKwhSource();
  }
});

function toggleScenarioParams(toggleId, paramsId) {
  const update = () => { el(paramsId).classList.toggle('is-disabled', !el(toggleId).checked); };
  el(toggleId).addEventListener('change', update);
  update();
}
toggleScenarioParams('scenario-toggle-ev', 'scenario-params-ev');
toggleScenarioParams('scenario-toggle-heatpump', 'scenario-params-heatpump');
toggleScenarioParams('scenario-toggle-pv', 'scenario-params-pv');
toggleScenarioParams('scenario-toggle-balcony', 'scenario-params-balcony');

el('scenario-flex').addEventListener('input', () => {
  el('scenario-flex-value').textContent = el('scenario-flex').value;
});

/* ---------- PV-Standort (für die PV-Erzeugung aus echten Wetterdaten) ---------- */

let scenarioLocation = { name: 'Deutschland-Mitte', latitude: 51.0, longitude: 10.0 };

function formatCoord(value, pos, neg) {
  return `${formatNum(Math.abs(value), 2)}° ${value >= 0 ? pos : neg}`;
}

function setScenarioLocation(location) {
  scenarioLocation = location;
  el('scenario-location-name').textContent = location.name;
  el('scenario-location-coords').textContent =
    `(${formatCoord(location.latitude, 'N', 'S')}, ${formatCoord(location.longitude, 'O', 'W')})`;
  el('scenario-location-results').innerHTML = '';
  updateScenarioSum();
}

async function searchScenarioLocation() {
  const query = el('scenario-location-query').value.trim();
  const box = el('scenario-location-results');
  if (query.length < 2) {
    box.textContent = 'Bitte mindestens 2 Zeichen eingeben.';
    return;
  }
  box.textContent = 'Suche…';
  try {
    const data = await apiRequest(`/api/scenario/geocode?q=${encodeURIComponent(query)}`, { method: 'GET' });
    if (!data.results.length) {
      box.textContent = 'Kein Ort gefunden. Bitte den Ortsnamen prüfen (Postleitzahlen werden nicht erkannt).';
      return;
    }
    box.innerHTML = data.results
      .map((r, i) => `<button type="button" class="location-option" data-index="${i}">${escapeHtml(r.name)}` +
        `<span>${escapeHtml(r.region)}</span></button>`)
      .join('');
    box.querySelectorAll('.location-option').forEach((btn) => {
      btn.addEventListener('click', () => {
        const r = data.results[Number(btn.dataset.index)];
        setScenarioLocation({ name: r.region ? `${r.name} (${r.region})` : r.name, latitude: r.latitude, longitude: r.longitude });
      });
    });
  } catch (err) {
    box.textContent = err.message;
  }
}

el('btn-scenario-location-search').addEventListener('click', searchScenarioLocation);
el('scenario-location-query').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    searchScenarioLocation();
  }
});

function scenarioPayload() {
  const household = selectedScenarioHousehold();
  return {
    household_id: el('scenario-household').value,
    location: scenarioLocation,
    annual_kwh: scenarioUsesOwnKwh() ? parseFloat(el('scenario-annual-kwh').value) : household?.typical_annual_kwh,
    flex_percent: parseFloat(el('scenario-flex').value),
    flex_target: document.querySelector('input[name="scenario-flex-target"]:checked')?.value || 'cheap',
    ev: {
      enabled: el('scenario-toggle-ev').checked,
      km_per_year: parseFloat(el('scenario-ev-km').value) || 0,
      kwh_per_100km: parseFloat(el('scenario-ev-consumption').value) || 18,
      mode: document.querySelector('input[name="scenario-ev-mode"]:checked')?.value || 'uncontrolled',
    },
    heatpump: {
      enabled: el('scenario-toggle-heatpump').checked,
      annual_kwh: parseFloat(el('scenario-heatpump-kwh').value) || 0,
    },
    pv: {
      enabled: el('scenario-toggle-pv').checked,
      kwp: parseFloat(el('scenario-pv-kwp').value) || 0,
      orientation: el('scenario-pv-orientation').value,
      tilt: parseFloat(el('scenario-pv-tilt').value) || 0,
    },
    balcony: {
      enabled: el('scenario-toggle-balcony').checked,
      kwp: parseFloat(el('scenario-balcony-kwp').value) || 0,
      orientation: el('scenario-balcony-orientation').value,
    },
  };
}

/* ---------- Live-Summe: Haushaltsstrom + Verbraucher − PV-Eigenverbrauch = Netzbezug ----------
   Haushaltsstrom, E-Auto und Wärmepumpe sind sofort bekannt; der PV-Eigenverbrauch hängt
   vom stündlichen Verlauf ab und kommt (entprellt) von /api/scenario/preview. */

let scenarioPreviewTimer = null;
let scenarioPreviewRequestId = 0;

function formatKwh(value) {
  return `${formatNum(Math.round(value), 0)} kWh`;
}

function solarState(p) {
  const pv = p.pv.enabled && p.pv.kwp > 0;
  const balcony = p.balcony.enabled && p.balcony.kwp > 0;
  return { pv, balcony, any: pv || balcony };
}

// solar: {self, production, pvSelf, balconySelf} in kWh (self/production = PV + Balkonkraftwerk
// zusammen, pvSelf/balconySelf = Anteil je Anlage) -- null, solange die
// Vorschau vom Server noch aussteht.
function renderScenarioSum(p, solar) {
  const solarSelf = solar ? solar.self : null;
  const household = p.annual_kwh > 0 ? p.annual_kwh : 0;
  const ev = p.ev.enabled ? (p.ev.km_per_year * p.ev.kwh_per_100km) / 100 : 0;
  const hp = p.heatpump.enabled ? p.heatpump.annual_kwh : 0;
  const total = household + ev + hp;
  const on = solarState(p);

  el('scenario-amount-ev').textContent = p.ev.enabled ? `+ ${formatKwh(ev)}` : '';
  el('scenario-amount-heatpump').textContent = p.heatpump.enabled ? `+ ${formatKwh(hp)}` : '';
  // Je Anlage ihr Anteil am selbst genutzten Solarstrom (senkt den Netzbezug).
  const solarAmount = (enabled, value) => (!enabled ? '' : value == null ? '− … kWh' : `− ${formatKwh(value)} Netzbezug`);
  el('scenario-amount-pv').textContent = solarAmount(on.pv, solar?.pvSelf);
  el('scenario-amount-balcony').textContent = solarAmount(on.balcony, solar?.balconySelf);

  const source = scenarioUsesOwnKwh() ? 'eigener Wert' : 'typischer Wert';
  const rows = [['', `Haushaltsstrom (${source})`, formatKwh(household)]];
  if (p.ev.enabled) rows.push(['+', `E-Auto (${formatNum(p.ev.km_per_year, 0)} km × ${formatNum(p.ev.kwh_per_100km, 1)} kWh/100 km)`, formatKwh(ev)]);
  if (p.heatpump.enabled) rows.push(['+', 'Wärmepumpe', formatKwh(hp)]);
  const sumRows = [['=', 'Verbrauch gesamt', formatKwh(total), 'subtotal']];
  if (on.any) {
    const sources = [];
    if (on.pv) sources.push(`PV ${formatNum(p.pv.kwp, 1)} kWp`);
    if (on.balcony) sources.push(`Balkonkraftwerk ${formatNum(p.balcony.kwp, 2)} kWp`);
    sumRows.push(['−', `selbst genutzter Solarstrom (${sources.join(' + ')})`, solarSelf == null ? 'wird berechnet…' : formatKwh(solarSelf)]);
  }
  sumRows.push(['=', 'Netzbezug (wird im Tarifvergleich bezahlt)', on.any && solarSelf == null ? '…' : formatKwh(total - (on.any ? solarSelf : 0)), 'total']);

  el('scenario-sum-table').innerHTML = [...rows, ...sumRows]
    .map(([op, label, value, cls]) =>
      `<tr${cls ? ` class="${cls}"` : ''}><td class="op">${op}</td><td>${escapeHtml(label)}</td><td class="num">${value}</td></tr>`)
    .join('');
  renderSolarBalance(on.any && solar && solar.production > 0 ? solar : null, total);
}

// Solarbilanz getrennt von der Verbrauchsrechnung: wohin die erzeugte Energie geht und wie viel
// des Verbrauchs sie deckt. Sonst wirkt "6.686 kWh erzeugt, 836 kWh genutzt" wie ein Rechenfehler.
function renderSolarBalance(solar, totalConsumption) {
  const box = el('scenario-solar-balance');
  box.hidden = !solar;
  if (!solar) return;
  const exported = Math.max(0, solar.production - solar.self);
  const usedShare = (solar.self / solar.production) * 100;
  const coverage = totalConsumption > 0 ? (solar.self / totalConsumption) * 100 : 0;
  box.innerHTML =
    '<h4>Solarbilanz</h4>' +
    '<table class="scenario-sum-table">' +
    `<tr><td class="op"></td><td>Solarstrom erzeugt</td><td class="num">${formatKwh(solar.production)}</td></tr>` +
    `<tr><td class="op">→</td><td>selbst genutzt (${formatNum(usedShare, 0)} %)</td><td class="num">${formatKwh(solar.self)}</td></tr>` +
    `<tr><td class="op">→</td><td>ins Netz eingespeist, ohne Vergütung (${formatNum(100 - usedShare, 0)} %)</td><td class="num">${formatKwh(exported)}</td></tr>` +
    '</table>' +
    `<p class="field-hint">Der Solarstrom deckt <strong>${formatNum(coverage, 0)} % deines Verbrauchs</strong>. ` +
    'Er fällt nur tagsüber und vor allem im Sommer an – abends, nachts und im Winter kommt der Strom ' +
    'trotzdem aus dem Netz. Ohne Batteriespeicher geht der Überschuss ins Netz.</p>';
}

// "Sonnige Stunden" ist nur mit PV-Anlage oder Balkonkraftwerk sinnvoll -- sonst zurück auf
// "günstige Stunden". Der Standort-Block erscheint nur, wenn er gebraucht wird.
function updateScenarioSolarControls() {
  const solarOn = el('scenario-toggle-pv').checked || el('scenario-toggle-balcony').checked;
  el('scenario-location-box').hidden = !solarOn;
  const sunny = document.querySelector('input[name="scenario-flex-target"][value="sunny"]');
  sunny.disabled = !solarOn;
  el('scenario-flex-sunny-option').classList.toggle('is-disabled', !solarOn);
  el('scenario-flex-sunny-hint').hidden = solarOn;
  if (!solarOn && sunny.checked) document.querySelector('input[name="scenario-flex-target"][value="cheap"]').checked = true;
}

// Jahresertrag im Vergleichsjahr (echtes Wetter am Standort), absolut und je kWp -- getrennt
// für PV-Anlage und Balkonkraftwerk. preview = null: Berechnung läuft noch.
function renderSolarYield(boxId, enabled, kwp, productionKwh, preview) {
  const box = el(boxId);
  if (!enabled) {
    box.textContent = '';
    return;
  }
  if (!preview) {
    box.textContent = 'Jahresertrag wird berechnet…';
    return;
  }
  box.innerHTML =
    `Jahresertrag ${preview.reference_year}: <strong>${formatKwh(productionKwh)}</strong> ` +
    `<span class="field-hint">(${formatNum(Math.round(productionKwh / kwp), 0)} kWh je kWp)</span>`;
}

function renderSolarYields(p, preview) {
  const on = solarState(p);
  renderSolarYield('scenario-pv-yield', on.pv, p.pv.kwp, preview?.pv_production_kwh, preview);
  renderSolarYield('scenario-balcony-yield', on.balcony, p.balcony.kwp, preview?.balcony_production_kwh, preview);
}

function updateScenarioSum() {
  updateScenarioSolarControls();
  const p = scenarioPayload();
  renderSolarYields(p, null);
  if (!p.household_id) return;
  const on = solarState(p);
  renderScenarioSum(p, on.any ? null : { self: 0, production: 0 });
  if (!on.any || !(p.annual_kwh > 0)) return;

  clearTimeout(scenarioPreviewTimer);
  scenarioPreviewTimer = setTimeout(async () => {
    const requestId = ++scenarioPreviewRequestId;
    try {
      const preview = await apiRequest('/api/scenario/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p),
      });
      if (requestId !== scenarioPreviewRequestId) return;
      renderScenarioSum(p, {
        self: preview.pv_self_consumption_kwh,
        pvSelf: preview.pv_only_self_consumption_kwh,
        balconySelf: preview.balcony_self_consumption_kwh,
        production: preview.pv_production_kwh + preview.balcony_production_kwh,
      });
      renderSolarYields(p, preview);
    } catch {
      // Vorschau ist nur Komfort -- beim Erstellen wird ohnehin exakt gerechnet.
    }
  }, 300);
}

// Eingaben im Ortssuchfeld ändern das Szenario nicht (erst die Auswahl eines Treffers) --
// sonst würde jeder Tastendruck eine neue Vorschau beim Server anfragen.
function onScenarioInput(e) {
  if (e.target.id === 'scenario-location-query') return;
  updateScenarioSum();
}
el('modal-scenario').addEventListener('input', onScenarioInput);
el('modal-scenario').addEventListener('change', onScenarioInput);

el('btn-use-scenario').addEventListener('click', async () => {
  clearError();

  const payload = scenarioPayload();

  if (!payload.household_id || Number.isNaN(payload.annual_kwh) || payload.annual_kwh <= 0) {
    showError('Bitte einen Haushaltstyp wählen und einen gültigen Jahresverbrauch angeben.');
    return;
  }

  const btn = el('btn-use-scenario');
  setButtonLoading(btn, true, 'Szenario wird aufgebaut…');
  try {
    const data = await apiRequest('/api/scenario/build', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.sessionId = data.session_id;
    state.dataSource = 'scenario';
    showImportSummary(data);
    el('btn-back-to-source').dataset.backTo = 'modal-scenario';
    showStep('modal-tariffs');
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
});

/* ---------- Schritt 1: Upload ---------- */

el('btn-upload').addEventListener('click', async () => {
  clearError();
  const fileInput = el('csv-file');
  if (!fileInput.files.length) {
    showError('Bitte zuerst eine CSV-Datei auswählen.');
    return;
  }
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  const btn = el('btn-upload');
  setButtonLoading(btn, true, 'Wird hochgeladen und analysiert…');
  try {
    const data = await apiRequest('/api/import/upload', { method: 'POST', body: formData });
    state.sessionId = data.session_id;
    populateMappingStep(data);
    showStep('modal-mapping');
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
});

/* ---------- Schritt 2: Mapping ---------- */

function populateMappingStep(data) {
  const tsSelect = el('select-timestamp-col');
  const valSelect = el('select-value-col');
  tsSelect.innerHTML = '';
  valSelect.innerHTML = '';
  data.columns.forEach((col) => {
    tsSelect.appendChild(new Option(col, col));
    valSelect.appendChild(new Option(col, col));
  });

  if (data.suggested_timestamp_column) tsSelect.value = data.suggested_timestamp_column;
  if (data.suggested_value_column) valSelect.value = data.suggested_value_column;
  if (data.suggested_value_type) el('select-value-type').value = data.suggested_value_type;
  el('select-timezone').value = data.suggested_timezone || 'Europe/Berlin';

  const warningsBox = el('mapping-warnings');
  if (data.warnings && data.warnings.length) {
    warningsBox.hidden = false;
    warningsBox.innerHTML = '<strong>Hinweise:</strong><ul>' + data.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('') + '</ul>';
  } else {
    warningsBox.hidden = true;
    warningsBox.innerHTML = '';
  }

  renderPreviewTable(data.columns, data.preview_rows);
}

function renderPreviewTable(columns, rows) {
  const table = el('preview-table');
  const thead = '<thead><tr>' + columns.map((c) => `<th>${escapeHtml(c)}</th>`).join('') + '</tr></thead>';
  const tbody =
    '<tbody>' +
    rows
      .map((row) => '<tr>' + columns.map((c) => `<td>${escapeHtml(row[c] ?? '')}</td>`).join('') + '</tr>')
      .join('') +
    '</tbody>';
  table.innerHTML = thead + tbody;
}

el('btn-confirm-mapping').addEventListener('click', async () => {
  clearError();
  const payload = {
    session_id: state.sessionId,
    timestamp_column: el('select-timestamp-col').value,
    value_column: el('select-value-col').value,
    value_type: el('select-value-type').value,
    timezone: el('select-timezone').value,
  };

  const btn = el('btn-confirm-mapping');
  setButtonLoading(btn, true, 'Stundenwerte werden berechnet…');
  try {
    const data = await apiRequest('/api/import/confirm', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    state.dataSource = 'upload';
    showImportSummary(data);
    el('btn-back-to-source').dataset.backTo = 'modal-mapping';
    showStep('modal-tariffs');
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
});

/* ---------- Datensatz spenden (nur nach eigenem Upload, nicht bei Beispiel-Auswahl) ---------- */

// Wird erst zusammen mit dem Ergebnis gezeigt (nicht schon nach dem Import) und nur,
// wenn die Daten aus einem eigenen Upload stammen -- ein bereits gespendeter/kuratierter
// Beispiel-Haushalt muss nicht erneut angeboten werden.
function updateDonateSectionVisibility() {
  const section = el('donate-section');
  if (state.dataSource !== 'upload') {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  el('donate-form').hidden = true;
  el('btn-show-donate-form').hidden = false;
  el('donate-result').hidden = true;
  el('donate-consent').checked = false;
  el('btn-submit-donate').disabled = true;
}

el('btn-show-donate-form').addEventListener('click', () => {
  el('donate-form').hidden = false;
  el('btn-show-donate-form').hidden = true;
});

el('donate-consent').addEventListener('change', () => {
  const accepted = el('donate-consent').checked;
  el('btn-submit-donate').disabled = !accepted;
  el('btn-submit-donate').title = accepted ? '' : 'Bitte zuerst der Veröffentlichung oben zustimmen';
});

el('btn-submit-donate').addEventListener('click', async () => {
  clearError();
  if (!el('donate-consent').checked) {
    showError('Bitte zuerst der Veröffentlichung der Daten zustimmen.');
    return;
  }
  const payload = {
    session_id: state.sessionId,
    haushaltsgroesse: parseInt(el('donate-haushaltsgroesse').value, 10),
    balkonkraftwerk: el('donate-balkonkraftwerk').value === 'true',
    pv: el('donate-pv').value === 'true',
    speicher: el('donate-speicher').value === 'true',
    waermepumpe: el('donate-waermepumpe').value === 'true',
    durchlauferhitzer: el('donate-durchlauferhitzer').value === 'true',
    elektroauto: el('donate-elektroauto').value === 'true',
  };

  if (Number.isNaN(payload.haushaltsgroesse) || payload.haushaltsgroesse < 1) {
    showError('Bitte eine gültige Haushaltsgröße angeben.');
    return;
  }

  const btn = el('btn-submit-donate');
  setButtonLoading(btn, true, 'Wird gesendet…');
  try {
    const data = await apiRequest('/api/donate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    el('donate-form').hidden = true;
    const resultEl = el('donate-result');
    resultEl.textContent = data.message;
    resultEl.hidden = false;
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
});

function showImportSummary(data) {
  el('summary-total-kwh').textContent = `${data.total_kwh.toLocaleString('de-DE')} kWh`;
  el('summary-meta').textContent =
    `Zeitraum ${formatDateTime(data.start_date)} – ${formatDateTime(data.end_date)} (${data.hours_count} Stunden)`;

  const warningsBox = el('summary-warnings');
  if (data.warnings && data.warnings.length) {
    warningsBox.innerHTML = '<ul>' + data.warnings.map((w) => `<li>${escapeHtml(w)}</li>`).join('') + '</ul>';
  } else {
    warningsBox.innerHTML = '';
  }

  const scenarioBox = el('summary-scenario-details');
  const checkHint = el('summary-check-hint');
  if (data.summary_lines && data.summary_lines.length) {
    el('summary-scenario-list').innerHTML = data.summary_lines.map((line) => `<li>${escapeHtml(line)}</li>`).join('');
    scenarioBox.hidden = false;
    checkHint.hidden = true; // Prüfhinweis (Vergleich mit eigener Stromrechnung) passt nicht bei einem Modell-Szenario
  } else {
    scenarioBox.hidden = true;
    checkHint.hidden = false;
  }
}

function formatDateTime(isoString) {
  const d = new Date(isoString);
  return d.toLocaleString('de-DE', { dateStyle: 'medium', timeStyle: 'short' });
}

/* ---------- Schritt 3: Tarife & Berechnung ---------- */

// 8 = Anzahl der Kategorial-Farben in style.css (--series-1..--series-8); mehr Tarife
// hätten keine eigene Chart-Farbe mehr.
const MAX_TARIFFS = 8;
// Muss zu SafeName in app/schemas.py passen (max_length + verbotene Zeichen).
const TARIFF_NAME_MAX_LENGTH = 40;
const UNSAFE_NAME_CHARS_RE = /[<>"'`]/;
const DEFAULT_TARIFF_NAMES = { fix: 'Fixtarif', dynamic: 'Dynamischer Tarif' };

// autoName = Name ist noch ein vom Programm vergebener Standardname und darf beim
// Typwechsel mitwandern. Sobald der Nutzer den Namen selbst editiert, bleibt er fest.
let tariffs = [
  { uid: 1, type: 'fix', name: 'Fixtarif', autoName: true, arbeitspreis_ct_kwh: 30.38, grundgebuehr_eur_monat: 11.90 },
  { uid: 2, type: 'dynamic', name: 'Dynamischer Tarif', autoName: true, mwst_percent: 19, anbietergebuehr_ct_kwh: 2.0, fixanteil_ct_kwh: 17.46, aufschlag_ct_kwh: 19.46, grundgebuehr_eur_monat: 10.13 },
  { uid: 3, type: 'fix', name: 'Grundtarif', autoName: false, arbeitspreis_ct_kwh: 37.93, grundgebuehr_eur_monat: 14.39 },
];
// Aus den Startdaten ableiten, damit neue Tarife nie eine bereits vergebene uid (und
// damit doppelte DOM-IDs) bekommen.
let tariffUidCounter = Math.max(...tariffs.map((t) => t.uid));

function normalizeTariffName(name) {
  return String(name ?? '').trim().toLowerCase();
}

// Liefert base, "base 2", "base 3", ... -- den ersten Namen, den kein anderer Tarif nutzt.
function uniqueTariffName(base, ownUid = null) {
  const taken = new Set(
    tariffs.filter((t) => t.uid !== ownUid).map((t) => normalizeTariffName(t.name)),
  );
  if (!taken.has(normalizeTariffName(base))) return base;
  for (let i = 2; ; i += 1) {
    const candidate = `${base} ${i}`;
    if (!taken.has(normalizeTariffName(candidate))) return candidate;
  }
}

// Gibt eine Fehlermeldung zurück oder null, wenn der Name gültig ist.
function tariffNameError(t) {
  const name = String(t.name ?? '').trim();
  if (!name) return 'Bitte einen Namen vergeben.';
  if (name.length > TARIFF_NAME_MAX_LENGTH) return `Maximal ${TARIFF_NAME_MAX_LENGTH} Zeichen.`;
  if (UNSAFE_NAME_CHARS_RE.test(name)) return 'Die Zeichen < > " \' ` sind nicht erlaubt.';
  const duplicate = tariffs.some(
    (other) => other.uid !== t.uid && normalizeTariffName(other.name) === normalizeTariffName(name),
  );
  if (duplicate) return 'Dieser Name wird schon von einem anderen Tarif verwendet.';
  return null;
}

// Zeigt die Namensfehler direkt unter dem jeweiligen Namensfeld an und liefert den
// ersten Fehler (für das Fehlerbanner beim Berechnen) oder null.
function updateTariffNameErrors() {
  let first = null;
  tariffs.forEach((t) => {
    const message = tariffNameError(t);
    const errorEl = el(`tariff-${t.uid}-name-error`);
    errorEl.textContent = message ?? '';
    errorEl.hidden = !message;
    el(`tariff-${t.uid}-name`).setAttribute('aria-invalid', message ? 'true' : 'false');
    if (message && !first) first = `Tarif „${String(t.name).trim() || '(ohne Namen)'}“: ${message}`;
  });
  return first;
}

/* Preismodell (muss zu calculation/cost.py passen): Alle Werte, mit denen gerechnet wird, sind
   brutto. Dynamischer Tarif: Arbeitspreis(h) = Börsenpreis(h) netto × (1 + MwSt.) + Aufschlag
   brutto. Der Aufschlag enthält alles außer dem Börsenpreis (Netzentgelt, Stromsteuer, Umlagen,
   Konzessionsabgabe, Anbietermarge -- jeweils inkl. MwSt.).
   Einfache Ansicht: Aufschlag = Anbietergebühr (je Anbieter verschieden) + fixer Anteil
   (Netzentgelt, Steuern, Umlagen -- für alle Anbieter an derselben Adresse gleich). Den fixen
   Anteil kann man aus dem "geschätzten Arbeitspreis" eines Angebots herausrechnen lassen.
   In der erweiterten Ansicht werden diese Bestandteile netto eingegeben und hier in den
   Brutto-Aufschlag bzw. die Brutto-Grundgebühr umgerechnet; ans Backend gehen immer nur die
   Brutto-Summen. */
const DEFAULT_MWST_PERCENT = 19;
const STROMSTEUER_CT_KWH = 2.05; // Regelsatz Stromsteuer, netto
const EXAMPLE_SPOT_CT_KWH = 10; // Beispiel-Börsenpreis für die Live-Vorschau

const DYN_ENERGY_PARTS = [
  { key: 'anbieter_ct_kwh', label: 'Anbieteraufschlag / Marge (ct/kWh)' },
  { key: 'netzentgelt_ct_kwh', label: 'Netzentgelt Arbeitspreis (ct/kWh)' },
  { key: 'stromsteuer_ct_kwh', label: 'Stromsteuer (ct/kWh)' },
  { key: 'umlagen_ct_kwh', label: 'Umlagen & Konzessionsabgabe (ct/kWh)' },
];
const DYN_BASE_PARTS = [
  { key: 'grund_anbieter_eur_monat', label: 'Grundgebühr Anbieter (€/Monat)' },
  { key: 'grund_netz_eur_monat', label: 'Netz-Grundpreis & Messstellenbetrieb (€/Monat)' },
];
const DYN_ADVANCED_KEYS = ['mwst_percent', ...DYN_ENERGY_PARTS.map((p) => p.key), ...DYN_BASE_PARTS.map((p) => p.key)];

// Leere Felder der Aufschlüsselung zählen als 0 -- nicht jeder Anbieter weist jeden Posten aus.
function partValue(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : 0;
}

function round2(v) {
  return Math.round(v * 100) / 100;
}

function mwstFactor(t) {
  return 1 + partValue(t.mwst_percent ?? DEFAULT_MWST_PERCENT) / 100;
}

function dynAdvancedTotals(t) {
  const sum = (parts) => parts.reduce((acc, p) => acc + partValue(t[p.key]), 0);
  return {
    aufschlag: round2(sum(DYN_ENERGY_PARTS) * mwstFactor(t)),
    grundgebuehr: round2(sum(DYN_BASE_PARTS) * mwstFactor(t)),
  };
}

// Beim Öffnen der Aufschlüsselung die Bestandteile so vorbelegen, dass die Summe den bisherigen
// Brutto-Werten entspricht: Die übrigen Posten bleiben wie sie sind (bzw. Standardwerte), der
// Rest landet beim Anbieteraufschlag bzw. der Anbieter-Grundgebühr.
function prefillDynAdvanced(t) {
  t.mwst_percent ??= DEFAULT_MWST_PERCENT;
  t.netzentgelt_ct_kwh ??= 0;
  t.stromsteuer_ct_kwh ??= STROMSTEUER_CT_KWH;
  t.umlagen_ct_kwh ??= 0;
  t.grund_netz_eur_monat ??= 0;
  const factor = mwstFactor(t);
  // Anbietergebühr -> Anbieteraufschlag (netto); der fixe Anteil landet nach Abzug von
  // Stromsteuer und Umlagen beim Netzentgelt, damit die Summe gleich bleibt.
  t.anbieter_ct_kwh = round2(partValue(t.anbietergebuehr_ct_kwh) / factor);
  t.netzentgelt_ct_kwh = round2(Math.max(0,
    partValue(t.fixanteil_ct_kwh) / factor - partValue(t.stromsteuer_ct_kwh) - partValue(t.umlagen_ct_kwh)));
  t.grund_anbieter_eur_monat = round2(Math.max(0, partValue(t.grundgebuehr_eur_monat) / factor - partValue(t.grund_netz_eur_monat)));
}

function formatCt(value) {
  return `${value.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ct/kWh`;
}

function dynPreviewText(t) {
  const aufschlag = parseFloat(t.aufschlag_ct_kwh);
  if (!Number.isFinite(aufschlag)) return '';
  const mwst = partValue(t.mwst_percent ?? DEFAULT_MWST_PERCENT);
  const price = EXAMPLE_SPOT_CT_KWH * mwstFactor(t) + aufschlag;
  return `Beispiel: Börsenpreis ${formatCt(EXAMPLE_SPOT_CT_KWH)} netto → Arbeitspreis ` +
    `${formatCt(price)} brutto (Börsenpreis + ${mwst.toLocaleString('de-DE')} % MwSt. + Aufschlag)`;
}

function numberInput(id, value, { readonly = false, step = '0.01' } = {}) {
  return `<input type="number" id="${id}" step="${step}" min="0" value="${escapeHtml(value ?? '')}"${readonly ? ' readonly tabindex="-1"' : ''}>`;
}

function dynFieldsHtml(t) {
  const adv = Boolean(t.advanced);
  const advancedHtml = !adv ? '' : `
    <div class="tariff-advanced" id="tariff-${t.uid}-advanced">
      <p class="field-hint">Netto-Beträge laut Preisblatt von Anbieter bzw. Netzbetreiber. Leere Felder zählen als 0.</p>
      ${DYN_ENERGY_PARTS.map((p) => `<label>${p.label}${numberInput(`tariff-${t.uid}-${p.key}`, t[p.key])}</label>`).join('')}
      ${DYN_BASE_PARTS.map((p) => `<label>${p.label}${numberInput(`tariff-${t.uid}-${p.key}`, t[p.key])}</label>`).join('')}
      <label>MwSt. (%)${numberInput(`tariff-${t.uid}-mwst_percent`, t.mwst_percent, { step: '0.1' })}</label>
    </div>`;

  const simpleEnergyHtml = adv ? `
    <label>Aufschlag brutto (ct/kWh)
      ${numberInput(`tariff-${t.uid}-aufschlag`, t.aufschlag_ct_kwh, { readonly: true })}
      <span class="field-hint">Wird aus der Aufschlüsselung berechnet.</span>
    </label>` : `
    <label>Anbietergebühr brutto (ct/kWh)
      ${numberInput(`tariff-${t.uid}-anbietergebuehr`, t.anbietergebuehr_ct_kwh)}
      <span class="field-hint">Was der Anbieter pro kWh zusätzlich zum Börsenpreis verlangt
        (z.B. „Arbeitspreis Anbietergebühr“).</span>
    </label>
    <label>Netzentgelt, Steuern &amp; Umlagen brutto (ct/kWh)
      ${numberInput(`tariff-${t.uid}-fixanteil`, t.fixanteil_ct_kwh)}
      <span class="field-hint">Fix – für alle Anbieter an deiner Adresse gleich.</span>
      <button type="button" class="btn-link" id="tariff-${t.uid}-estimate-toggle" aria-expanded="${Boolean(t.estimateOpen)}">
        ${t.estimateOpen ? '▴ Rechner schließen' : '▾ Aus geschätztem Arbeitspreis des Angebots berechnen'}
      </button>
    </label>
    ${t.estimateOpen ? `
    <div class="tariff-estimate">
      <label>Geschätzter Arbeitspreis laut Angebot, brutto (ct/kWh)
        ${numberInput(`tariff-${t.uid}-estimate`, t.estimate_ct_kwh)}
        <span class="field-hint">Ohne Anbietergebühr, z.B. „geschätzter Arbeitspreis/kWh brutto“.</span>
      </label>
      <p class="field-hint" id="tariff-${t.uid}-estimate-spot">Ø-Börsenpreis der letzten 12 Monate wird geladen…</p>
      <button type="button" class="btn btn-secondary" id="tariff-${t.uid}-estimate-apply" disabled>Übernehmen</button>
    </div>` : ''}
    <p class="tariff-aufschlag-sum" id="tariff-${t.uid}-aufschlag-sum"></p>`;

  return `
    ${simpleEnergyHtml}
    <label>Grundgebühr brutto (€/Monat)
      ${numberInput(`tariff-${t.uid}-grundgebuehr`, t.grundgebuehr_eur_monat ?? 5, { readonly: adv })}
      <span class="field-hint">${adv ? 'Wird aus der Aufschlüsselung berechnet.' : 'Anbieter-Grundgebühr + Netz-Grundpreis/Messstelle — inkl. MwSt. Jahresbetrag ÷ 12.'}</span>
    </label>
    <label>Bonus/Rabatt (€, einmalig)
      ${numberInput(`tariff-${t.uid}-bonus`, t.bonus_eur ?? 0)}
      <span class="field-hint">z.B. Grundpreisrabatt im 1. Jahr; wird auf 12 Monate verteilt.</span>
    </label>
    <p class="tariff-preview" id="tariff-${t.uid}-preview">${escapeHtml(dynPreviewText(t))}</p>
    <button type="button" class="btn-link" id="tariff-${t.uid}-advanced-toggle" aria-expanded="${adv}">
      ${adv ? '▴ Aufschlüsselung schließen' : '▾ Erweitert: Preisbestandteile einzeln eingeben'}
    </button>
    ${advancedHtml}`;
}

function tariffRowHtml(t) {
  const canRemove = tariffs.length > 2;
  const fixFields = `
    <label>Arbeitspreis brutto (ct/kWh)
      ${numberInput(`tariff-${t.uid}-arbeitspreis`, t.arbeitspreis_ct_kwh ?? 30)}
    </label>
    <label>Grundgebühr brutto (€/Monat)
      ${numberInput(`tariff-${t.uid}-grundgebuehr`, t.grundgebuehr_eur_monat ?? 8)}
    </label>
    <label>Bonus (€, einmalig)
      ${numberInput(`tariff-${t.uid}-bonus`, t.bonus_eur ?? 0)}
      <span class="field-hint">Neukunden- + Sofortbonus zusammen. Gilt fürs erste Vertragsjahr und
        wird auf 12 Monate verteilt; bei kürzerem Zeitraum anteilig.</span>
    </label>`;

  return `
    <fieldset class="tariff-box" data-uid="${t.uid}">
      <legend>
        <input type="text" id="tariff-${t.uid}-name" class="tariff-name-input" value="${escapeHtml(t.name)}"
          maxlength="${TARIFF_NAME_MAX_LENGTH}" aria-label="Tarifname" aria-describedby="tariff-${t.uid}-name-error">
        ${canRemove ? `<button type="button" id="tariff-${t.uid}-remove" class="btn-remove-tariff" title="Tarif entfernen">✕</button>` : ''}
      </legend>
      <p class="field-error" id="tariff-${t.uid}-name-error" role="alert" hidden></p>
      <label>Typ
        <select id="tariff-${t.uid}-type">
          <option value="fix" ${t.type === 'fix' ? 'selected' : ''}>Fixtarif</option>
          <option value="dynamic" ${t.type === 'dynamic' ? 'selected' : ''}>Dynamischer Tarif</option>
        </select>
      </label>
      ${t.type === 'fix' ? fixFields : dynFieldsHtml(t)}
    </fieldset>`;
}

// Die Eingabefelder im DOM sind die "Wahrheit" während der Bearbeitung. Vor jedem
// strukturellen Rerender (Tarif hinzufügen/entfernen/Typ wechseln) müssen die aktuell
// eingegebenen Werte zuerst zurück ins tariffs-Array geschrieben werden, sonst gehen
// sie beim Neuaufbau des HTML verloren.
function syncTariffFromDom(t) {
  t.name = el(`tariff-${t.uid}-name`).value;
  if (t.type === 'fix') {
    t.arbeitspreis_ct_kwh = el(`tariff-${t.uid}-arbeitspreis`).value;
    t.grundgebuehr_eur_monat = el(`tariff-${t.uid}-grundgebuehr`).value;
    t.bonus_eur = el(`tariff-${t.uid}-bonus`).value;
  } else if (t.advanced) {
    DYN_ADVANCED_KEYS.forEach((key) => { t[key] = el(`tariff-${t.uid}-${key}`).value; });
    const totals = dynAdvancedTotals(t);
    t.aufschlag_ct_kwh = totals.aufschlag;
    t.grundgebuehr_eur_monat = totals.grundgebuehr;
  } else {
    t.anbietergebuehr_ct_kwh = el(`tariff-${t.uid}-anbietergebuehr`).value;
    t.fixanteil_ct_kwh = el(`tariff-${t.uid}-fixanteil`).value;
    const bothEmpty = t.anbietergebuehr_ct_kwh === '' && t.fixanteil_ct_kwh === '';
    t.aufschlag_ct_kwh = bothEmpty ? '' : round2(partValue(t.anbietergebuehr_ct_kwh) + partValue(t.fixanteil_ct_kwh));
    t.grundgebuehr_eur_monat = el(`tariff-${t.uid}-grundgebuehr`).value;
    if (t.estimateOpen) t.estimate_ct_kwh = el(`tariff-${t.uid}-estimate`).value;
  }
  if (t.type === 'dynamic') t.bonus_eur = el(`tariff-${t.uid}-bonus`).value;
}

function syncTariffsFromDom() {
  tariffs.forEach(syncTariffFromDom);
}

// Live-Aktualisierung ohne Rerender (Fokus/Cursor bleiben erhalten): berechnete Brutto-
// Felder der Aufschlüsselung und die Beispiel-Vorschau.
function refreshDynDerivedFields(t) {
  if (t.type !== 'dynamic') return;
  syncTariffFromDom(t);
  if (t.advanced) {
    el(`tariff-${t.uid}-aufschlag`).value = t.aufschlag_ct_kwh;
    el(`tariff-${t.uid}-grundgebuehr`).value = t.grundgebuehr_eur_monat;
  } else {
    const aufschlag = parseFloat(t.aufschlag_ct_kwh);
    el(`tariff-${t.uid}-aufschlag-sum`).textContent = Number.isFinite(aufschlag)
      ? `= Aufschlag gesamt ${formatCt(aufschlag)} (alles außer dem Börsenpreis)` : '';
  }
  el(`tariff-${t.uid}-preview`).textContent = dynPreviewText(t);
}

/* ---------- Fixen Anteil aus dem geschätzten Arbeitspreis eines Angebots berechnen ----------
   Angebote nennen oft einen "geschätzten Arbeitspreis", der einen angenommenen Börsenpreis
   bereits enthält. Fixer Anteil = geschätzter Arbeitspreis − Ø-Börsenpreis × (1 + MwSt.).
   Als Börsenpreis dient der Ø der letzten 12 Monate (Annahme des Anbieters ggf. abweichend). */

let spotAverage12m = null; // Promise, einmal pro Seitenaufruf geladen

function loadSpotAverage12m() {
  spotAverage12m ??= apiRequest('/api/prices/average-12m', { method: 'GET' }).catch((err) => {
    spotAverage12m = null; // beim nächsten Öffnen erneut versuchen
    throw err;
  });
  return spotAverage12m;
}

async function initEstimateHelper(t) {
  const info = el(`tariff-${t.uid}-estimate-spot`);
  const apply = el(`tariff-${t.uid}-estimate-apply`);
  let spot;
  try {
    spot = await loadSpotAverage12m();
  } catch (err) {
    info.textContent = `Ø-Börsenpreis konnte nicht geladen werden: ${err.message}`;
    return;
  }
  if (!document.body.contains(apply)) return; // inzwischen neu gerendert
  info.textContent = `Abgezogen wird der Ø-Börsenpreis ${formatCt(spot.avg_ct_kwh_netto)} netto ` +
    `(${formatDateOnly(spot.start_date)} – ${formatDateOnly(spot.end_date)}) zzgl. MwSt. ` +
    'Nennt das Angebot einen anderen angenommenen Börsenpreis, den fixen Anteil danach von Hand anpassen.';
  apply.disabled = false;
  apply.addEventListener('click', () => {
    syncTariffFromDom(t);
    const estimate = parseFloat(t.estimate_ct_kwh);
    if (!Number.isFinite(estimate)) {
      info.textContent = 'Bitte zuerst den geschätzten Arbeitspreis eintragen.';
      return;
    }
    t.fixanteil_ct_kwh = round2(Math.max(0, estimate - spot.avg_ct_kwh_netto * mwstFactor(t)));
    t.estimateOpen = false;
    renderTariffList();
  });
}

function renderTariffList() {
  el('tariff-list').innerHTML = tariffs.map(tariffRowHtml).join('');

  tariffs.forEach((t) => {
    el(`tariff-${t.uid}-name`).addEventListener('input', (e) => {
      t.name = e.target.value;
      t.autoName = false;
      updateTariffNameErrors();
    });
    el(`tariff-${t.uid}-type`).addEventListener('change', (e) => {
      syncTariffsFromDom();
      t.type = e.target.value;
      if (t.autoName) t.name = uniqueTariffName(DEFAULT_TARIFF_NAMES[t.type], t.uid);
      renderTariffList();
    });
    if (t.type === 'dynamic') {
      document.querySelector(`.tariff-box[data-uid="${t.uid}"]`).addEventListener('input', (e) => {
        if (e.target.type === 'number') refreshDynDerivedFields(t);
      });
      el(`tariff-${t.uid}-advanced-toggle`).addEventListener('click', () => {
        syncTariffsFromDom();
        t.advanced = !t.advanced;
        if (t.advanced) {
          prefillDynAdvanced(t);
        } else {
          // Zurück in die einfache Ansicht: Anbietergebühr aus dem Anbieteraufschlag, der Rest
          // des (aus der Aufschlüsselung berechneten) Aufschlags ist der fixe Anteil.
          t.anbietergebuehr_ct_kwh = round2(partValue(t.anbieter_ct_kwh) * mwstFactor(t));
          t.fixanteil_ct_kwh = round2(Math.max(0, partValue(t.aufschlag_ct_kwh) - t.anbietergebuehr_ct_kwh));
        }
        renderTariffList();
      });
      if (!t.advanced) {
        el(`tariff-${t.uid}-estimate-toggle`).addEventListener('click', () => {
          syncTariffsFromDom();
          t.estimateOpen = !t.estimateOpen;
          renderTariffList();
        });
        if (t.estimateOpen) initEstimateHelper(t);
      }
      refreshDynDerivedFields(t);
    }
    const removeBtn = document.getElementById(`tariff-${t.uid}-remove`);
    if (removeBtn) {
      removeBtn.addEventListener('click', () => {
        syncTariffsFromDom();
        tariffs = tariffs.filter((row) => row.uid !== t.uid);
        renderTariffList();
      });
    }
  });

  el('btn-add-tariff').disabled = tariffs.length >= MAX_TARIFFS;
  updateTariffNameErrors();
}

el('btn-add-tariff').addEventListener('click', () => {
  if (tariffs.length >= MAX_TARIFFS) return;
  syncTariffsFromDom();
  tariffUidCounter += 1;
  // Netzentgelt, Steuern & Umlagen sind für alle Anbieter an derselben Adresse gleich -- vom
  // ersten dynamischen Tarif übernehmen, dann muss nur noch die Anbietergebühr angepasst werden.
  const template = tariffs.find((t) => t.type === 'dynamic');
  const fixanteil = template ? partValue(template.fixanteil_ct_kwh ?? template.aufschlag_ct_kwh) : 17.46;
  tariffs.push({
    uid: tariffUidCounter,
    type: 'dynamic',
    name: uniqueTariffName(DEFAULT_TARIFF_NAMES.dynamic),
    autoName: true,
    mwst_percent: DEFAULT_MWST_PERCENT,
    anbietergebuehr_ct_kwh: 2.0,
    fixanteil_ct_kwh: fixanteil,
    aufschlag_ct_kwh: round2(2.0 + fixanteil),
    grundgebuehr_eur_monat: template ? template.grundgebuehr_eur_monat : 10,
  });
  renderTariffList();
});

renderTariffList();

el('btn-calculate').addEventListener('click', async () => {
  clearError();
  syncTariffsFromDom();

  const nameError = updateTariffNameErrors();
  if (nameError) {
    showError(nameError);
    return;
  }

  const payloadTariffs = [];
  for (const t of tariffs) {
    const name = t.name.trim();
    const entry = t.type === 'fix'
      ? {
          type: 'fix',
          name,
          arbeitspreis_ct_kwh: parseFloat(t.arbeitspreis_ct_kwh),
          grundgebuehr_eur_monat: parseFloat(t.grundgebuehr_eur_monat),
          // Leeres Bonusfeld = kein Bonus.
          bonus_eur: t.bonus_eur === '' || t.bonus_eur == null ? 0 : parseFloat(t.bonus_eur),
        }
      : {
          type: 'dynamic',
          name,
          mwst_percent: parseFloat(t.mwst_percent ?? DEFAULT_MWST_PERCENT),
          aufschlag_ct_kwh: parseFloat(t.aufschlag_ct_kwh),
          grundgebuehr_eur_monat: parseFloat(t.grundgebuehr_eur_monat),
          bonus_eur: t.bonus_eur === '' || t.bonus_eur == null ? 0 : parseFloat(t.bonus_eur),
        };

    if (Object.values(entry).some((v) => typeof v === 'number' && Number.isNaN(v))) {
      showError(`Bitte alle Felder von "${name}" mit gültigen Zahlen ausfüllen.`);
      return;
    }
    const advancedNegative = t.type === 'dynamic' && t.advanced && DYN_ADVANCED_KEYS.some((key) => partValue(t[key]) < 0);
    if (advancedNegative || Object.values(entry).some((v) => typeof v === 'number' && v < 0)) {
      showError(`"${name}": Preisangaben dürfen nicht negativ sein.`);
      return;
    }
    payloadTariffs.push(entry);
  }

  const payload = { session_id: state.sessionId, tariffs: payloadTariffs };

  const btn = el('btn-calculate');
  setButtonLoading(btn, true, 'Preise werden abgerufen und Kosten berechnet…');
  try {
    const data = await apiRequest('/api/calculate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    // Erst sichtbar machen, dann rendern: Chart.js berechnet beim Aufbau die Canvas-Größe
    // aus dem Container -- waere der Container noch per [hidden] versteckt (display:none),
    // bekaeme der Chart eine 0x0-Ausgangsgröße.
    showStep('modal-results');
    renderResults(data);
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
});

/* ---------- Schritt 4: Ergebnis ---------- */

function formatEur(value) {
  return value.toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
}

function formatDateOnly(isoDate) {
  const d = new Date(isoDate + 'T00:00:00');
  return d.toLocaleDateString('de-DE', { dateStyle: 'medium' });
}

function formatNum(value, digits) {
  return value.toLocaleString('de-DE', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

// Rohdaten des letzten Berechnungsergebnisses, damit der Kosten-Chart lokal zwischen
// Monats-/Tagesansicht umschalten kann, ohne erneut /api/calculate aufzurufen.
let resultDailyRaw = [];
let resultTariffNames = [];
let resultTariffTypes = {}; // Name -> 'fix' | 'dynamic'
let resultTariffs = []; // data.tariffs der letzten Berechnung (Summen je Tarif)
let resultTotalKwh = 0;
let chartGranularity = 'month';
let selectedMonthKey = null; // nur relevant, wenn chartGranularity === 'day'

function getAvailableMonths(daily) {
  const months = new Set(daily.map((d) => d.date.slice(0, 7)));
  return Array.from(months).sort();
}

function renderMonthTabs(months, selected) {
  const container = el('chart-month-tabs');
  container.innerHTML = months
    .map(
      (m) =>
        `<button type="button" class="month-tab-btn ${m === selected ? 'active' : ''}" data-month="${m}">${formatMonthLabel(m)}</button>`
    )
    .join('');
  container.querySelectorAll('.month-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('active')) return;
      selectedMonthKey = btn.dataset.month;
      renderDailyChartForGranularity();
    });
  });
}

function renderDailyChartForGranularity() {
  const tabsContainer = el('chart-month-tabs');

  if (chartGranularity === 'day') {
    const months = getAvailableMonths(resultDailyRaw);
    if (!selectedMonthKey || !months.includes(selectedMonthKey)) {
      selectedMonthKey = months[0];
    }
    renderMonthTabs(months, selectedMonthKey);
    tabsContainer.hidden = false;

    const items = resultDailyRaw.filter((d) => d.date.slice(0, 7) === selectedMonthKey);
    renderDailyChart(items, resultTariffNames, 'day');
  } else {
    tabsContainer.hidden = true;
    const items = aggregateCostsByMonth(resultDailyRaw, resultTariffNames);
    renderDailyChart(items, resultTariffNames, 'month');
  }
}

document.querySelectorAll('#chart-granularity-toggle .granularity-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.classList.contains('active')) return;
    document.querySelectorAll('#chart-granularity-toggle .granularity-btn').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    chartGranularity = btn.dataset.granularity;
    renderDailyChartForGranularity();
  });
});

function renderResults(data) {
  const names = data.tariffs.map((t) => t.name);

  const statGrid = el('stat-grid-tariffs');
  statGrid.innerHTML = data.tariffs
    .map(
      (t, i) => `
      <button type="button" class="stat-tile tariff-pick" data-index="${i}" aria-pressed="false">
        <span class="pick-badge">✓ im Vergleich</span>
        <div class="stat-label">${escapeHtml(t.name)} gesamt</div>
        <div class="stat-value">${formatEur(t.total_eur)}</div>
        <div class="stat-breakdown">
          Ø Arbeitspreis ${formatCt(t.avg_price_ct_kwh)}<br>
          Energie ${formatEur(t.energy_cost_eur)} + Grundgebühr ${formatEur(t.base_fee_eur)}${
            t.bonus_eur > 0 ? ` − Bonus ${formatEur(t.bonus_eur)}` : ''}
        </div>
      </button>`
    )
    .join('');
  statGrid.querySelectorAll('.tariff-pick').forEach((tile) => {
    tile.addEventListener('click', () => selectCompareTariff(names[Number(tile.dataset.index)]));
  });

  el('stat-period').textContent = `${Math.round(data.period_days)} Tage`;
  el('stat-cheapest').textContent = data.cheapest_name;

  const savingsEl = el('stat-savings');
  const savingsPctEl = el('stat-savings-pct');
  savingsEl.textContent = formatEur(data.savings_vs_most_expensive_eur);
  savingsPctEl.textContent = `${data.savings_vs_most_expensive_percent.toFixed(1)} % günstiger als ${data.most_expensive_name}`;
  savingsPctEl.className = 'stat-delta positive';

  const missingBox = el('missing-price-note');
  if (data.hours_missing_price > 0) {
    missingBox.hidden = false;
    missingBox.textContent = `${data.hours_missing_price} von ${data.hours_total} Stunden hatten keine aWATTar-Preisdaten und wurden bei allen Tarifen aus dem Vergleich ausgeschlossen.`;
  } else {
    missingBox.hidden = true;
  }

  resultDailyRaw = data.daily;
  resultTariffNames = names;
  resultTariffTypes = Object.fromEntries(data.tariffs.map((t) => [t.name, t.type]));
  resultTariffs = data.tariffs;
  resultTotalKwh = data.total_kwh;
  state.comparePair = [names[0], names[1]];
  renderComparePair();
  renderDailyChartForGranularity();

  updateDonateSectionVisibility();
}

function aggregateCostsByMonth(daily, names) {
  const buckets = new Map();
  daily.forEach((d) => {
    const monthKey = d.date.slice(0, 7); // YYYY-MM
    if (!buckets.has(monthKey)) {
      const initial = {};
      names.forEach((n) => (initial[n] = 0));
      buckets.set(monthKey, initial);
    }
    const bucket = buckets.get(monthKey);
    names.forEach((n) => {
      bucket[n] += d.costs[n] ?? 0;
    });
  });

  return Array.from(buckets.entries())
    .sort(([a], [b]) => (a < b ? -1 : 1))
    .map(([monthKey, costs]) => ({ date: monthKey, costs }));
}

/* ---------- Tagesvergleich zweier frei gewählter Tarife ----------
   Die Tageswerte (resultDailyRaw) sind absolute Kosten inkl. Grundgebühr-Anteil (siehe
   calculation/cost.py). Für das gewählte Paar A/B wird je Tarif der Tag gesucht, an dem er
   gegenüber dem anderen am besten abschneidet -- symmetrisch, ohne feste Reihenfolge. */

// Klick auf einen noch nicht gewählten Tarif ersetzt den länger gewählten; es bleiben immer genau 2.
function selectCompareTariff(name) {
  if (state.comparePair.includes(name)) return;
  state.comparePair = [state.comparePair[1], name];
  renderComparePair();
}

// Tag mit dem größten Kostenvorteil von `name` gegenüber `other` (kann auch der Tag sein, an
// dem `name` am wenigsten teurer war, falls er nie günstiger ist).
function bestDayFor(name, other) {
  return resultDailyRaw.reduce((best, d) => {
    const advantage = d.costs[other] - d.costs[name];
    return !best || advantage > best.advantage ? { date: d.date, advantage, costs: d.costs } : best;
  }, null);
}

function renderDayCompareItem(slot, name, other) {
  const day = bestDayFor(name, other);
  state.compareDays[slot] = day.date;
  const nameSafe = escapeHtml(name);
  const otherSafe = escapeHtml(other);
  const cheaper = day.advantage >= 0;

  el(`day-${slot}-heading`).innerHTML = `Bester Tag für ${nameSafe}`;
  // War der Tarif an keinem Tag (mind. 1 Cent) günstiger, gibt es keinen "besten Tag" -- der
  // Tag mit dem kleinsten Nachteil wäre irreführend.
  const neverCheaper = day.advantage < 0.005;
  el(`btn-day-${slot}-detail`).hidden = neverCheaper;
  if (neverCheaper) {
    el(`day-${slot}-title`).innerHTML = `${nameSafe} war an keinem Tag günstiger als ${otherSafe}.`;
    return;
  }
  el(`day-${slot}-title`).innerHTML =
    `${formatDateOnly(day.date)}: ${nameSafe} war ` +
    `<span class="${cheaper ? 'positive' : 'negative'}">${formatEur(Math.abs(day.advantage))} ${cheaper ? 'günstiger' : 'teurer'}</span> ` +
    `als ${otherSafe} (${nameSafe}: ${formatEur(day.costs[name])} · ${otherSafe}: ${formatEur(day.costs[other])}, jeweils inkl. Grundgebühr)`;
}

function renderComparePair() {
  const [a, b] = state.comparePair;
  document.querySelectorAll('#stat-grid-tariffs .tariff-pick').forEach((tile) => {
    const selected = state.comparePair.includes(resultTariffNames[Number(tile.dataset.index)]);
    tile.classList.toggle('selected', selected);
    tile.setAttribute('aria-pressed', String(selected));
  });
  el('day-compare-pair').innerHTML = pairBannerHtml(a, b);
  renderDayCompareItem('a', a, b);
  renderDayCompareItem('b', b, a);
  renderPairAnalysis();
}

/* ---------- Paarvergleich über den gesamten Zeitraum ----------
   Kennzahlen und Monatsbilanz kommen aus den bereits geladenen Tageswerten (inkl.
   Grundgebühr); Tagesprofil und Profilfaktor brauchen Stundendaten und kommen von
   /api/pair-analysis. */

function countWins(items, a, b) {
  return items.reduce(
    (acc, it) => {
      const diff = it.costs[b] - it.costs[a];
      if (Math.abs(diff) < 0.005) acc.equal += 1;
      else if (diff > 0) acc.a += 1;
      else acc.b += 1;
      return acc;
    },
    { a: 0, b: 0, equal: 0 },
  );
}

function statTileHtml(label, value, deltaHtml = '', id = '') {
  return `<div class="stat-tile"${id ? ` id="${id}"` : ''}><div class="stat-label">${label}</div>` +
    `<div class="stat-value">${value}</div>${deltaHtml ? `<div class="stat-delta">${deltaHtml}</div>` : ''}</div>`;
}

function winsText(wins, a, b, unit) {
  const parts = [`${escapeHtml(a)}: ${wins.a}`, `${escapeHtml(b)}: ${wins.b}`];
  if (wins.equal) parts.push(`gleich: ${wins.equal}`);
  return `${parts.join(' · ')} ${unit}`;
}

let pairAnalysisRequestId = 0;

// Preisverlaufs-Charts sind nur mit mindestens einem dynamischen Tarif aussagekräftig --
// zwei Fixtarife ergäben nur zwei flache Linien.
function pairHasDynamic(names) {
  return names.some((n) => resultTariffTypes[n] === 'dynamic');
}

// Farbe folgt dem Tarif (Position in der Tarifliste) -- siehe charts.js.
function chartPair(names) {
  return names.map((name) => ({ name, colorIndex: resultTariffNames.indexOf(name) }));
}

// "Chip vs. Chip" mit Tariffarbe, Typ und Gesamtkosten -- macht sichtbar, welches Paar gerade
// in Paar- und Tagesvergleich gegenübergestellt wird.
function pairBannerHtml(a, b) {
  const chip = (name) => {
    const t = resultTariffs.find((row) => row.name === name);
    const color = seriesColor(resultTariffNames.indexOf(name));
    const type = t.type === 'dynamic' ? 'dynamisch' : 'fix';
    return `<span class="pair-chip" style="border-color:${color}">` +
      `<span class="legend-swatch" style="background:${color}"></span>` +
      `<span class="pair-chip-name">${escapeHtml(name)}</span>` +
      `<span class="pair-chip-meta">${type} · ${formatEur(t.total_eur)}</span></span>`;
  };
  return `${chip(a)}<span class="pair-vs">vs.</span>${chip(b)}`;
}

async function renderPairAnalysis() {
  const [a, b] = state.comparePair;
  const ta = resultTariffs.find((t) => t.name === a);
  const tb = resultTariffs.find((t) => t.name === b);
  const [winner, loser] = ta.total_eur <= tb.total_eur ? [ta, tb] : [tb, ta];
  const diff = loser.total_eur - winner.total_eur;
  const diffPct = loser.total_eur ? (diff / loser.total_eur) * 100 : 0;
  const diffPerKwh = resultTotalKwh ? (diff / resultTotalKwh) * 100 : 0;
  const months = aggregateCostsByMonth(resultDailyRaw, [a, b]);
  const dayWins = countWins(resultDailyRaw, a, b);
  const monthWins = countWins(months, a, b);
  const winnerWins = (wins) => (winner.name === a ? wins.a : wins.b);

  el('pair-title').innerHTML = pairBannerHtml(a, b);
  el('pair-kpis').innerHTML =
    statTileHtml(
      'Günstiger im Gesamtzeitraum',
      escapeHtml(winner.name),
      `<span class="positive">${formatEur(diff)} (${formatNum(diffPct, 1)} %)</span> günstiger als ${escapeHtml(loser.name)}`,
    ) +
    statTileHtml(
      'Differenz je kWh',
      formatCt(diffPerKwh),
      `So viel müsste ${escapeHtml(loser.name)} je kWh günstiger sein, um gleichzuziehen`,
    ) +
    statTileHtml(`Tage, an denen ${escapeHtml(winner.name)} günstiger war`, `${winnerWins(dayWins)} von ${resultDailyRaw.length}`, winsText(dayWins, a, b, 'Tage')) +
    statTileHtml(`Monate, in denen ${escapeHtml(winner.name)} günstiger war`, `${winnerWins(monthWins)} von ${months.length}`, winsText(monthWins, a, b, 'Monate')) +
    [a, b]
      .filter((n) => resultTariffTypes[n] === 'dynamic')
      .map((n, i) => statTileHtml(`Profilfaktor ${escapeHtml(n)}`, '…', 'wird berechnet', `pair-profile-${i}`))
      .join('');

  const first = resultDailyRaw[0].date;
  const last = resultDailyRaw[resultDailyRaw.length - 1].date;
  el('pair-period').textContent =
    `über ${resultDailyRaw.length} Tage (${formatDateOnly(first)} – ${formatDateOnly(last)})`;

  const pair = chartPair([a, b]);
  renderPairMonthsChart(months, pair);

  // Bei schnellem Umklicken nur die Antwort der letzten Anfrage rendern.
  const requestId = ++pairAnalysisRequestId;
  try {
    const analysis = await apiRequest('/api/pair-analysis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, tariff_names: [a, b] }),
    });
    if (requestId !== pairAnalysisRequestId) return;
    // Erst ein-/ausblenden, dann rendern (Chart.js misst die Containergröße).
    el('pair-prices-section').hidden = !pairHasDynamic([a, b]);
    renderPairProfileCharts(analysis.hours, pair);
    [a, b]
      .filter((n) => resultTariffTypes[n] === 'dynamic')
      .forEach((n, i) => {
        const tile = el(`pair-profile-${i}`);
        const factor = analysis.profile[n].profile_factor_ct_kwh;
        if (factor === null) return;
        const good = factor <= 0;
        tile.querySelector('.stat-value').textContent = `${factor > 0 ? '+' : ''}${formatCt(factor)}`;
        tile.querySelector('.stat-delta').innerHTML =
          `Ø bezahlt ${formatCt(analysis.profile[n].weighted_avg_ct_kwh)} vs. zeitlicher Ø ${formatCt(analysis.profile[n].time_avg_ct_kwh)} — ` +
          `<span class="${good ? 'positive' : 'negative'}">Verbrauch liegt eher in ${good ? 'günstigen' : 'teuren'} Stunden</span>`;
      });
  } catch (err) {
    if (requestId === pairAnalysisRequestId) showError(err.message);
  }
}

function formatOptionalNum(value, digits) {
  return value === null || value === undefined ? '–' : formatNum(value, digits);
}

function renderDayDetailTable(detail, [a, b], titleHtml) {
  const aSafe = escapeHtml(a);
  const bSafe = escapeHtml(b);
  el('day-detail-title').innerHTML = titleHtml;

  // Je Tarif eine Spaltengruppe. Dynamische Tarife bekommen zusätzlich den berechneten
  // Arbeitspreis der Stunde (Börsenpreis + MwSt. + Aufschlag); beim Fixtarif ist der
  // konstant und steht stattdessen im Gruppenkopf.
  const groups = [a, b].map((name) => {
    const dynamic = resultTariffTypes[name] === 'dynamic';
    const firstPrice = detail.hours.find((h) => h.prices_ct_kwh[name] != null)?.prices_ct_kwh[name];
    const subtitle = dynamic ? 'dynamisch' : `Arbeitspreis ${formatOptionalNum(firstPrice, 2)} ct/kWh`;
    return { name, dynamic, safe: escapeHtml(name), subtitle, cols: dynamic ? 3 : 2 };
  });

  const header =
    `<thead><tr><th rowspan="2">Stunde</th><th rowspan="2">Verbrauch</th>` +
    groups.map((g) => `<th colspan="${g.cols}" class="group-head">${g.safe}<span class="group-sub">${g.subtitle}</span></th>`).join('') +
    `<th rowspan="2">Vorteil<br>${aSafe}</th></tr><tr>` +
    groups.map((g) =>
      (g.dynamic ? '<th>Arbeitspreis<br>ct/kWh</th>' : '') + '<th>inkl. Grundg.*<br>ct/kWh</th><th>Kosten<br>€</th>',
    ).join('') +
    '</tr></thead>';

  const body =
    '<tbody>' +
    detail.hours
      .map((h) => {
        const advantage = h.costs_eur[b] - h.costs_eur[a];
        const cells = groups.map((g) =>
          (g.dynamic ? `<td>${formatOptionalNum(h.prices_ct_kwh[g.name], 2)}</td>` : '') +
          `<td>${formatOptionalNum(h.all_in_ct_kwh[g.name], 2)}</td><td>${formatNum(h.costs_eur[g.name], 4)}</td>`,
        ).join('');
        return `<tr><td>${h.hour}</td><td>${formatNum(h.consumption_kwh, 3)} kWh</td>${cells}` +
          `<td class="${advantage >= 0 ? 'positive' : 'negative'}">${formatNum(advantage, 4)}</td></tr>`;
      })
      .join('') +
    '</tbody>';

  // Summenzeile: Preise als verbrauchsgewichteter Tagesdurchschnitt (Ø), Kosten als Summe.
  const kwh = detail.consumption_kwh;
  const weightedAvg = (key, name) => {
    const hours = detail.hours.filter((h) => h[key][name] != null);
    const hoursKwh = hours.reduce((s, h) => s + h.consumption_kwh, 0);
    return hoursKwh > 0 ? hours.reduce((s, h) => s + h[key][name] * h.consumption_kwh, 0) / hoursKwh : null;
  };
  const dayAdvantage = detail.totals_eur[b] - detail.totals_eur[a];
  const footer =
    `<tfoot><tr class="detail-sum"><td>Summe</td><td>${formatNum(kwh, 3)} kWh</td>` +
    groups.map((g) =>
      (g.dynamic ? `<td>Ø ${formatOptionalNum(weightedAvg('prices_ct_kwh', g.name), 2)}</td>` : '') +
      `<td>Ø ${formatOptionalNum(kwh > 0 ? (detail.totals_eur[g.name] / kwh) * 100 : null, 2)}</td>` +
      `<td>${formatEur(detail.totals_eur[g.name])}</td>`,
    ).join('') +
    `<td class="${dayAdvantage >= 0 ? 'positive' : 'negative'}">${formatEur(dayAdvantage)}</td></tr></tfoot>`;

  el('table-day-detail').innerHTML = header + body + footer;
  el('day-detail-note').innerHTML =
    `<strong>Arbeitspreis</strong>: berechneter Strompreis der Stunde (Börsenpreis + MwSt. + Aufschlag), ohne Grundgebühr. ` +
    `<strong>* inkl. Grundg.</strong>: Arbeitspreis + Grundgebühr-Anteil (Monatsgrundgebühr ÷ Monatsverbrauch), abzüglich eines evtl. Bonus-Anteils. ` +
    `<strong>Kosten</strong>: absolute Kosten der Stunde inkl. Grundgebühr. ` +
    `<strong>Vorteil ${aSafe}</strong>: Kosten ${bSafe} − Kosten ${aSafe} (positiv = ${aSafe} günstiger).`;
}

async function openDayDetail(slot) {
  // Der Tarif, dessen bester Tag angezeigt wird, steht in der Tabelle vorne.
  const [a, b] = state.comparePair;
  const pair = slot === 'a' ? [a, b] : [b, a];
  const btn = el(`btn-day-${slot}-detail`);
  const titleHtml = el(`day-${slot}-title`).innerHTML;
  clearError();
  btn.disabled = true;
  try {
    const detail = await apiRequest('/api/day-detail', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: state.sessionId, date: state.compareDays[slot], tariff_names: pair }),
    });
    renderDayDetailTable(detail, pair, titleHtml);
    // Erst sichtbar machen, dann Charts bauen (Chart.js misst die Containergröße).
    showStep('modal-day-detail');
    // Bei zwei Fixtarifen ist die stündliche Bilanz nur ein Abbild des Verbrauchs und der
    // Preisverlauf zwei flache Linien -- beides ausblenden, Verbrauch bleibt.
    const hasDynamic = pairHasDynamic(pair);
    el('day-advantage-section').hidden = !hasDynamic;
    el('day-prices-section').hidden = !hasDynamic;
    renderDayCharts(detail, chartPair(pair));
  } catch (err) {
    showError(err.message);
  } finally {
    btn.disabled = false;
  }
}

el('btn-day-a-detail').addEventListener('click', () => openDayDetail('a'));
el('btn-day-b-detail').addEventListener('click', () => openDayDetail('b'));

/* ---------- Neustart ---------- */

el('btn-restart').addEventListener('click', () => {
  window.location.reload();
});

/* ---------- Iframe-Einbettung: Höhe an die Elternseite melden, damit das iframe dort
   automatisch mitwächst/-schrumpft statt eine feste Höhe mit Scrollbalken zu brauchen. ---------- */

if (window.parent !== window) {
  let lastReportedHeight = 0;
  const reportHeight = () => {
    const height = Math.ceil(document.body.getBoundingClientRect().height);
    if (height !== lastReportedHeight) {
      lastReportedHeight = height;
      window.parent.postMessage({ source: 'dynamischer-tarif-check', height }, '*');
    }
  };
  new ResizeObserver(reportHeight).observe(document.body);
  reportHeight();
}
