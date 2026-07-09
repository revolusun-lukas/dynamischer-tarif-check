/* Wizard-Logik: Upload -> Mapping bestätigen -> Tarife -> Ergebnis. */

const state = {
  sessionId: null,
};

const el = (id) => document.getElementById(id);

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

async function loadExamples() {
  try {
    const data = await apiRequest('/api/examples', { method: 'GET' });
    allExamples = data.examples;
  } catch (err) {
    allExamples = [];
  }
  renderExampleResults();
}

function renderExampleResults() {
  const container = el('example-results');

  if (allExamples.length === 0) {
    container.innerHTML =
      '<p class="example-empty-note">Noch keine Beispiel-Haushalte hinterlegt — bitte oben eigene Verbrauchsdaten hochladen.</p>';
    return;
  }

  container.innerHTML = allExamples
    .map((e) => {
      const configRows = [
        ['Haushaltsgröße', `${e.haushaltsgroesse} ${e.haushaltsgroesse === 1 ? 'Person' : 'Personen'}`],
        ...Object.entries(EXAMPLE_PROPERTY_LABELS)
          .filter(([key]) => e[key])
          .map(([key, label]) => [label, 'Ja']),
      ]
        .map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`)
        .join('');
      return `
        <div class="example-card">
          <dl class="example-card-config">${configRows}</dl>
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
    showImportSummary(data);
    el('step-tariffs').hidden = false;
    el('step-tariffs').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
}

loadExamples();

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
    el('step-mapping').hidden = false;
    el('step-mapping').scrollIntoView({ behavior: 'smooth' });
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
    warningsBox.innerHTML = '<strong>Hinweise:</strong><ul>' + data.warnings.map((w) => `<li>${w}</li>`).join('') + '</ul>';
  } else {
    warningsBox.hidden = true;
    warningsBox.innerHTML = '';
  }

  renderPreviewTable(data.columns, data.preview_rows);
  el('import-summary').hidden = true;
}

function renderPreviewTable(columns, rows) {
  const table = el('preview-table');
  const thead = '<thead><tr>' + columns.map((c) => `<th>${c}</th>`).join('') + '</tr></thead>';
  const tbody =
    '<tbody>' +
    rows
      .map((row) => '<tr>' + columns.map((c) => `<td>${row[c] ?? ''}</td>`).join('') + '</tr>')
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
    showImportSummary(data);
    el('step-tariffs').hidden = false;
    el('step-tariffs').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    showError(err.message);
  } finally {
    setButtonLoading(btn, false);
  }
});

function showImportSummary(data) {
  el('import-summary').hidden = false;

  el('summary-total-kwh').textContent = `${data.total_kwh.toLocaleString('de-DE')} kWh`;
  el('summary-meta').textContent =
    `Zeitraum ${formatDateTime(data.start_date)} – ${formatDateTime(data.end_date)} (${data.hours_count} Stunden)`;

  const warningsBox = el('summary-warnings');
  if (data.warnings && data.warnings.length) {
    warningsBox.innerHTML = '<ul>' + data.warnings.map((w) => `<li>${w}</li>`).join('') + '</ul>';
  } else {
    warningsBox.innerHTML = '';
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
let tariffUidCounter = 2;
let tariffs = [
  { uid: 1, type: 'fix', name: 'Fixtarif', arbeitspreis_ct_kwh: 30.38, grundgebuehr_eur_monat: 11.90 },
  { uid: 2, type: 'dynamic', name: 'Dynamischer Tarif', mwst_percent: 19, aufschlag_ct_kwh: 19.46, grundgebuehr_eur_monat: 10.13 },
  { uid: 3, type: 'fix', name: 'Grundtarif', arbeitspreis_ct_kwh: 37.93, grundgebuehr_eur_monat: 14.39},
];

function tariffRowHtml(t) {
  const canRemove = tariffs.length > 2;
  const fixFields = `
    <label>Arbeitspreis (ct/kWh)
      <input type="number" id="tariff-${t.uid}-arbeitspreis" step="0.01" min="0" value="${t.arbeitspreis_ct_kwh ?? 30}">
    </label>
    <label>Grundgebühr (€/Monat)
      <input type="number" id="tariff-${t.uid}-grundgebuehr" step="0.01" min="0" value="${t.grundgebuehr_eur_monat ?? 8}">
    </label>`;
  const dynFields = `
    <label>MwSt. auf Spotpreis (%)
      <input type="number" id="tariff-${t.uid}-mwst" step="0.1" min="0" value="${t.mwst_percent ?? 19}">
    </label>
    <label>Aufschlag (ct/kWh)
      <input type="number" id="tariff-${t.uid}-aufschlag" step="0.01" min="0" value="${t.aufschlag_ct_kwh ?? 12}">
    </label>
    <label>Grundgebühr (€/Monat)
      <input type="number" id="tariff-${t.uid}-grundgebuehr" step="0.01" min="0" value="${t.grundgebuehr_eur_monat ?? 5}">
    </label>`;

  return `
    <fieldset class="tariff-box" data-uid="${t.uid}">
      <legend>
        <input type="text" id="tariff-${t.uid}-name" class="tariff-name-input" value="${t.name}">
        ${canRemove ? `<button type="button" id="tariff-${t.uid}-remove" class="btn-remove-tariff" title="Tarif entfernen">✕</button>` : ''}
      </legend>
      <label>Typ
        <select id="tariff-${t.uid}-type">
          <option value="fix" ${t.type === 'fix' ? 'selected' : ''}>Fixtarif</option>
          <option value="dynamic" ${t.type === 'dynamic' ? 'selected' : ''}>Dynamischer Tarif</option>
        </select>
      </label>
      ${t.type === 'fix' ? fixFields : dynFields}
    </fieldset>`;
}

// Die Eingabefelder im DOM sind die "Wahrheit" während der Bearbeitung. Vor jedem
// strukturellen Rerender (Tarif hinzufügen/entfernen/Typ wechseln) müssen die aktuell
// eingegebenen Werte zuerst zurück ins tariffs-Array geschrieben werden, sonst gehen
// sie beim Neuaufbau des HTML verloren.
function syncTariffsFromDom() {
  tariffs.forEach((t) => {
    t.name = el(`tariff-${t.uid}-name`).value || t.name;
    if (t.type === 'fix') {
      t.arbeitspreis_ct_kwh = el(`tariff-${t.uid}-arbeitspreis`).value;
      t.grundgebuehr_eur_monat = el(`tariff-${t.uid}-grundgebuehr`).value;
    } else {
      t.mwst_percent = el(`tariff-${t.uid}-mwst`).value;
      t.aufschlag_ct_kwh = el(`tariff-${t.uid}-aufschlag`).value;
      t.grundgebuehr_eur_monat = el(`tariff-${t.uid}-grundgebuehr`).value;
    }
  });
}

function renderTariffList() {
  el('tariff-list').innerHTML = tariffs.map(tariffRowHtml).join('');

  tariffs.forEach((t) => {
    el(`tariff-${t.uid}-type`).addEventListener('change', (e) => {
      syncTariffsFromDom();
      t.type = e.target.value;
      renderTariffList();
    });
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
}

el('btn-add-tariff').addEventListener('click', () => {
  if (tariffs.length >= MAX_TARIFFS) return;
  syncTariffsFromDom();
  tariffUidCounter += 1;
  tariffs.push({
    uid: tariffUidCounter,
    type: 'dynamic',
    name: `Tarif ${tariffs.length + 1}`,
    mwst_percent: 19,
    aufschlag_ct_kwh: 12,
    grundgebuehr_eur_monat: 5,
  });
  renderTariffList();
});

renderTariffList();

el('btn-calculate').addEventListener('click', async () => {
  clearError();
  syncTariffsFromDom();

  const names = new Set();
  const payloadTariffs = [];
  for (const t of tariffs) {
    if (names.has(t.name)) {
      showError(`Tarifname "${t.name}" wird mehrfach verwendet. Bitte eindeutige Namen vergeben.`);
      return;
    }
    names.add(t.name);

    const entry = t.type === 'fix'
      ? {
          type: 'fix',
          name: t.name,
          arbeitspreis_ct_kwh: parseFloat(t.arbeitspreis_ct_kwh),
          grundgebuehr_eur_monat: parseFloat(t.grundgebuehr_eur_monat),
        }
      : {
          type: 'dynamic',
          name: t.name,
          mwst_percent: parseFloat(t.mwst_percent),
          aufschlag_ct_kwh: parseFloat(t.aufschlag_ct_kwh),
          grundgebuehr_eur_monat: parseFloat(t.grundgebuehr_eur_monat),
        };

    if (Object.values(entry).some((v) => typeof v === 'number' && Number.isNaN(v))) {
      showError(`Bitte alle Felder von "${t.name}" mit gültigen Zahlen ausfüllen.`);
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
    renderResults(data);
    el('step-results').hidden = false;
    el('step-results').scrollIntoView({ behavior: 'smooth' });
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
      (t) => `
      <div class="stat-tile">
        <div class="stat-label">${t.name} gesamt</div>
        <div class="stat-value">${formatEur(t.total_eur)}</div>
      </div>`
    )
    .join('');

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

  renderDayDetail('best-day-title', 'table-best-day', data.best_day, 'gespart');
  renderDayDetail('worst-day-title', 'table-worst-day', data.worst_day, 'teurer');

  resultDailyRaw = data.daily;
  resultTariffNames = names;
  renderDailyChartForGranularity();
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

// reference_name/compare_name kommen vom Backend und sind immer der 1./2. konfigurierte
// Tarif (siehe calculation/cost.py) -- unabhängig davon, wie viele weitere Tarife es gibt.
function renderDayDetail(titleId, tableId, dayData, diffWord) {
  const { reference_name: refName, compare_name: cmpName, diff_eur: diff } = dayData;
  const diffClass = diff >= 0 ? 'positive' : 'negative';

  el(titleId).innerHTML =
    `– ${formatDateOnly(dayData.date)} (${cmpName} war <span class="${diffClass}">${formatEur(Math.abs(diff))} ${diffWord}</span> ` +
    `als ${refName}: ${refName} ${formatEur(dayData.cost_reference_eur)} vs. ${cmpName} ${formatEur(dayData.cost_compare_eur)})`;

  const table = el(tableId);
  const header =
    `<thead><tr><th>Stunde</th><th>Verbrauch (kWh)</th><th>Differenz (€)</th><th>${refName} (ct/kWh)</th><th>${cmpName} (ct/kWh)</th>` +
    `<th>${refName} (€)</th><th>${cmpName} (€)</th></tr></thead>`;
  const body =
    '<tbody>' +
    dayData.hours
      .map((h) => {
        const hourDiff = h.costs_eur[refName] - h.costs_eur[cmpName];
        const hourDiffClass = hourDiff >= 0 ? 'positive' : 'negative';
        return `<tr><td>${h.hour}</td><td>${formatNum(h.consumption_kwh, 3)}</td>` +
          `<td class="${hourDiffClass}">${formatNum(hourDiff, 4)}</td><td>${formatNum(h.prices_ct_kwh[refName], 2)}</td><td>${formatNum(h.prices_ct_kwh[cmpName], 2)}</td>` +
          `<td>${formatNum(h.costs_eur[refName], 4)}</td><td>${formatNum(h.costs_eur[cmpName], 4)}</td>` +
          `</tr>`;
      })
      .join('') +
    '</tbody>';
  table.innerHTML = header + body;
}

/* ---------- Neustart ---------- */

el('btn-restart').addEventListener('click', () => {
  window.location.reload();
});
