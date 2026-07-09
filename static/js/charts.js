/* Chart.js-Aufbau für die Tageskosten-Vergleichs-Chart (eine Säule pro Tarif und Tag). */

// Feste Reihenfolge, keine automatisch generierten Farben (CVD-Sicherheit) -- muss zu den
// --series-1..8 Custom Properties in style.css passen. Tarife bekommen ihre Farbe in der
// Reihenfolge, in der sie im Tarif-Schritt hinzugefügt wurden.
const SERIES_VARS = ['--series-1', '--series-2', '--series-3', '--series-4', '--series-5', '--series-6', '--series-7', '--series-8'];

let dailyChartInstance = null;

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function seriesColor(index) {
  return cssVar(SERIES_VARS[index % SERIES_VARS.length]);
}

function commonScaleOptions() {
  return {
    grid: { color: cssVar('--gridline'), drawTicks: false },
    ticks: { color: cssVar('--text-muted'), font: { size: 11 } },
    border: { color: cssVar('--baseline') },
  };
}

function renderLegend(elementId, names) {
  const el = document.getElementById(elementId);
  el.innerHTML = names
    .map(
      (name, i) =>
        `<span class="legend-item"><span class="legend-swatch" style="background:${seriesColor(i)}"></span>${name}</span>`
    )
    .join('');
}

const CHART_HEIGHT_PX = 320;

function formatMonthLabel(monthKey) {
  const [year, month] = monthKey.split('-').map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString('de-DE', { month: 'short', year: 'numeric' });
}

function formatDayLabel(dateStr) {
  const d = new Date(dateStr + 'T00:00:00');
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' });
}

/* items: [{date, costs: {tarifname: betrag}}]. granularity steuert Label-Format, Balkenbreite und Achsentitel.
   Erzeugt bei jedem Aufruf einen komplett neuen Chart (destroy + recreate), damit Breite/Höhe immer zur
   aktuellen Datenmenge passen -- sonst bleibt die Canvas-Größe vom vorherigen Rendering stehen und der
   Graph wirkt verzerrt. */
function renderDailyChart(items, tariffNames, granularity) {
  renderLegend('legend-daily', tariffNames);

  if (dailyChartInstance) {
    dailyChartInstance.destroy();
    dailyChartInstance = null;
  }

  const isDay = granularity === 'day';
  const labelFormatter = isDay ? formatDayLabel : formatMonthLabel;
  const axisTitle = isDay ? '€ / Tag' : '€ / Monat';
  const perCategoryWidth = isDay ? Math.max(18, tariffNames.length * 8) : Math.max(70, tariffNames.length * 26);

  // Größe wird auf dem Wrapper-Div gesetzt (nicht direkt auf dem Canvas) und Chart.js
  // per responsive:true/maintainAspectRatio:false darauf angesetzt -- so berechnet
  // Chart.js die Canvas-Auflösung selbst inkl. devicePixelRatio und der Graph bleibt scharf.
  const width = Math.max(480, items.length * perCategoryWidth);
  const wrap = document.getElementById('chart-daily-wrap');
  wrap.style.width = width + 'px';
  wrap.style.height = CHART_HEIGHT_PX + 'px';

  const ctx = document.getElementById('chart-daily').getContext('2d');

  const datasets = tariffNames.map((name, i) => ({
    label: name,
    data: items.map((it) => it.costs[name]),
    backgroundColor: seriesColor(i),
    borderRadius: 4,
    maxBarThickness: isDay ? 16 : 32,
    categoryPercentage: 0.8,
    barPercentage: 0.9,
  }));

  dailyChartInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: items.map((it) => labelFormatter(it.date)),
      datasets,
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { ...commonScaleOptions(), ticks: { ...commonScaleOptions().ticks, maxTicksLimit: isDay ? 20 : undefined } },
        y: {
          ...commonScaleOptions(),
          beginAtZero: true,
          title: { display: true, text: axisTitle, color: cssVar('--text-secondary') },
        },
      },
    },
  });
}
