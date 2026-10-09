/*
 * Carte Lovelace « Solenso » : le panneau sert de jauge.
 * Chaque cellule = un micro-onduleur, éclairée selon sa puissance.
 * Livrée avec l'intégration Solenso (aucune ressource à ajouter à la main).
 */
const CARD_VERSION = "0.4.1";
const DOMAIN = "solenso";

const I18N = {
  fr: {
    today: "Aujourd'hui",
    month: "Ce mois",
    total: "Total",
    updated: (t) => `mis à jour ${t}`,
    asleep: (t) => `en veille depuis ${t}`,
    no_station: "Aucune centrale Solenso trouvée. Ajoutez l'intégration Solenso, puis choisissez la centrale dans les options de la carte.",
    panels: (n) => `${n} panneau${n > 1 ? "x" : ""}`,
    name: "Panneau solaire",
    description: "Centrale Solenso : le panneau s'éclaire selon la production de chaque micro-onduleur.",
    f_device: "Centrale",
    f_columns: "Colonnes",
    f_peak: "Puissance crête par panneau (W)",
    f_show_values: "Afficher les watts sur chaque panneau",
    f_show_panels: "Un panneau par micro-onduleur",
    f_name: "Titre",
  },
  en: {
    today: "Today",
    month: "This month",
    total: "Total",
    updated: (t) => `updated ${t}`,
    asleep: (t) => `asleep since ${t}`,
    no_station: "No Solenso station found. Add the Solenso integration, then pick the station in the card options.",
    panels: (n) => `${n} panel${n > 1 ? "s" : ""}`,
    name: "Solar panel",
    description: "Solenso station: the panel lights up with each micro-inverter's output.",
    f_device: "Station",
    f_columns: "Columns",
    f_peak: "Peak power per panel (W)",
    f_show_values: "Show watts on each panel",
    f_show_panels: "One panel per micro-inverter",
    f_name: "Title",
  },
};

const t = (hass) => I18N[(hass?.locale?.language || hass?.language || "en").slice(0, 2)] || I18N.en;

const ident = (device, prefix) =>
  (device.identifiers || []).some(([d, id]) => d === DOMAIN && (prefix ? String(id).startsWith(prefix) : /^\d+$/.test(String(id))));

const naturalSort = (a, b) => a.localeCompare(b, undefined, { numeric: true, sensitivity: "base" });

function findStation(hass, deviceId) {
  const devices = Object.values(hass.devices || {});
  const stations = devices.filter((d) => ident(d));
  const station = (deviceId && hass.devices[deviceId]) || stations[0];
  if (!station) return null;
  const entries = new Set(station.config_entries || []);
  const micros = devices
    .filter((d) => ident(d, "micro_") && (d.config_entries || []).some((e) => entries.has(e)))
    .map((d) => ({ device: d, name: d.name_by_user || d.name || "" }))
    .sort((a, b) => naturalSort(a.name, b.name));

  const byDevice = {};
  for (const ent of Object.values(hass.entities || {})) {
    if (ent.platform !== DOMAIN || !ent.device_id || !ent.translation_key) continue;
    (byDevice[ent.device_id] ||= {})[ent.translation_key] = ent.entity_id;
  }
  return {
    device: station,
    name: station.name_by_user || station.name,
    entities: byDevice[station.id] || {},
    micros: micros.map((m) => ({ ...m, entities: byDevice[m.device.id] || {} })),
  };
}

const num = (hass, entityId) => {
  const v = parseFloat(hass.states[entityId]?.state);
  return Number.isFinite(v) ? v : null;
};

function fmt(hass, entityId, fallbackDigits = 1) {
  const st = hass.states[entityId];
  if (!st || st.state === "unavailable" || st.state === "unknown") return { value: "—", unit: "" };
  if (hass.formatEntityState) {
    const full = hass.formatEntityState(st);
    const unit = st.attributes.unit_of_measurement || "";
    if (unit && full.endsWith(unit)) return { value: full.slice(0, -unit.length).trim(), unit };
    return { value: full, unit: "" };
  }
  const v = parseFloat(st.state);
  return {
    value: v.toLocaleString(hass.locale?.language, { maximumFractionDigits: fallbackDigits }),
    unit: st.attributes.unit_of_measurement || "",
  };
}

function relTime(hass, iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const diff = Math.round((d - Date.now()) / 60000);
  const rtf = new Intl.RelativeTimeFormat(hass.locale?.language || "en", { numeric: "auto" });
  if (Math.abs(diff) < 60) return rtf.format(diff, "minute");
  const sameDay = new Date().toDateString() === d.toDateString();
  return sameDay
    ? d.toLocaleTimeString(hass.locale?.language, { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleString(hass.locale?.language, { weekday: "short", hour: "2-digit", minute: "2-digit" });
}

// Couleur d'une cellule : silicium éteint -> bleu éclairé, selon le ratio de production.
const OFF = [22, 33, 56];
const LIT = [86, 170, 255];
const PEAK = [196, 232, 255];
function cellColor(ratio) {
  const r = Math.max(0, Math.min(1, ratio || 0));
  const a = r < 0.7 ? OFF.map((c, i) => c + (LIT[i] - c) * (r / 0.7)) : LIT.map((c, i) => c + (PEAK[i] - c) * ((r - 0.7) / 0.3));
  return `rgb(${a.map(Math.round).join(",")})`;
}

const STYLE = `
  :host { display: block; }
  ha-card { padding: 16px 16px 14px; overflow: hidden; }
  .head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
  .title { font-size: 1rem; font-weight: 500; color: var(--primary-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub { font-size: .8rem; color: var(--secondary-text-color); margin-top: 2px; }
  .power { text-align: right; font-variant-numeric: tabular-nums; cursor: pointer; flex: none; }
  .power .v { font-size: 2rem; font-weight: 300; line-height: 1; color: var(--primary-text-color); letter-spacing: -0.02em; }
  .power .u { font-size: 1rem; color: var(--secondary-text-color); margin-left: 3px; }
  svg { display: block; width: 100%; height: auto; }
  .cell { cursor: pointer; transition: fill .8s ease; outline: none; }
  .cell:focus-visible { stroke: var(--primary-color); stroke-width: 3; }
  .cellv { font-size: 13px; font-variant-numeric: tabular-nums; pointer-events: none; text-anchor: middle; }
  .plate {
    margin-top: 14px; display: grid; grid-template-columns: repeat(3, 1fr);
    border: 1px solid color-mix(in srgb, var(--primary-text-color) 16%, transparent);
    border-radius: 4px;
    background: color-mix(in srgb, var(--primary-text-color) 4%, transparent);
  }
  .plate > div { padding: 8px 10px; cursor: pointer; min-width: 0; }
  .plate > div + div { border-left: 1px solid color-mix(in srgb, var(--primary-text-color) 12%, transparent); }
  .plate dt { font-size: .72rem; color: var(--secondary-text-color); }
  .plate dd { margin: 2px 0 0; font-size: 1rem; font-variant-numeric: tabular-nums; color: var(--primary-text-color); white-space: nowrap; }
  .plate dd small { font-size: .75rem; color: var(--secondary-text-color); margin-left: 2px; }
  .empty { color: var(--secondary-text-color); font-size: .9rem; line-height: 1.4; }
  @media (prefers-reduced-motion: reduce) { .cell { transition: none; } }
`;

class SolensoCard extends HTMLElement {
  static getConfigForm() {
    return {
      schema: [
        { name: "device_id", selector: { device: { filter: { integration: DOMAIN, model: "Centrale photovoltaïque" } } } },
        { name: "name", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "columns", selector: { number: { min: 1, max: 16, mode: "box" } } },
            { name: "peak_power", selector: { number: { min: 50, max: 2000, step: 10, mode: "box", unit_of_measurement: "W" } } },
          ],
        },
        { name: "show_panels", selector: { boolean: {} } },
        { name: "show_values", selector: { boolean: {} } },
      ],
      computeLabel: (s) => {
        const tr = t(document.querySelector("home-assistant")?.hass);
        return tr["f_" + s.name] || s.name;
      },
    };
  }

  static getStubConfig(hass) {
    const station = findStation(hass);
    return station ? { device_id: station.device.id } : {};
  }

  setConfig(config) {
    this._config = { show_panels: true, show_values: true, peak_power: 350, ...config };
    this._sig = null;
    if (this._hass) this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 5;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  _moreInfo(entityId) {
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }

  _autoCols(n) {
    const cols = this._config.columns || (n <= 4 ? n : n <= 8 ? 4 : n <= 16 ? Math.ceil(n / 2) : 8);
    return Math.max(1, Math.min(cols, n));
  }

  // Position de chaque panneau : disposition réelle du toit (attributs layout_* fournis par
  // l'intégration), sinon grille automatique dans l'ordre des noms.
  _placement(station, hass) {
    const perMicro = this._config.show_panels && station.micros.length > 0;
    if (!perMicro) return { slots: [{ i: 0, r: 0, c: 0, sep: 0 }], rows: 1, cols: 1, seps: 0, perMicro };
    const n = station.micros.length;
    const pos = station.micros.map((m) => {
      const a = hass.states[m.entities.power]?.attributes || {};
      return Number.isInteger(a.layout_row) && Number.isInteger(a.layout_column)
        ? { r: a.layout_row, c: a.layout_column, g: a.layout_array ?? 0 }
        : null;
    });
    const useLayout = !this._config.columns && pos.some(Boolean);
    const slots = [];
    let rows = 0, cols = 0, seps = 0;
    if (useLayout) {
      // Un bloc par champ de panneaux, empilés avec une rangée d'écart.
      const groups = [...new Set(pos.filter(Boolean).map((p) => p.g))].sort((a, b) => a - b);
      for (const g of groups) {
        const inGroup = pos.map((p, i) => (p && p.g === g ? { ...p, i } : null)).filter(Boolean);
        const r0 = Math.min(...inGroup.map((p) => p.r)), c0 = Math.min(...inGroup.map((p) => p.c));
        if (rows) seps++;
        const offset = rows;
        for (const p of inGroup) slots.push({ i: p.i, r: offset + p.r - r0, c: p.c - c0, sep: seps });
        rows = offset + Math.max(...inGroup.map((p) => p.r - r0)) + 1;
        cols = Math.max(cols, ...inGroup.map((p) => p.c - c0 + 1));
      }
    }
    // Onduleurs sans position (ou grille imposée par « columns ») : à la suite, ligne par ligne.
    const rest = station.micros.map((_, i) => i).filter((i) => !useLayout || !pos[i]);
    if (rest.length) {
      const per = useLayout ? Math.max(cols, 1) : this._autoCols(n);
      if (rows) seps++;
      const offset = rows;
      rest.forEach((i, k) => slots.push({ i, r: offset + Math.floor(k / per), c: k % per, sep: seps }));
      rows = offset + Math.ceil(rest.length / per);
      cols = Math.max(cols, Math.min(per, rest.length));
    }
    return { slots, rows, cols, seps, perMicro };
  }

  _build(station, tr, placement) {
    const root = this.shadowRoot || this.attachShadow({ mode: "open" });
    const cfg = this._config;
    const { slots, rows, cols, seps, perMicro } = placement;

    // Géométrie du panneau : cellules portrait, cadre aluminium.
    const W = perMicro ? 64 : 360, H = perMicro ? 96 : 210, G = perMicro ? 5 : 0, F = 7;
    const vw = cols * W + (cols - 1) * G + 2 * F;
    const S = 22; // écart entre deux champs de panneaux
    const vh = rows * H + (rows - 1) * G + seps * S + 2 * F;
    let cells = "";
    for (const { i, r, c, sep } of slots) {
      const x = F + c * (W + G), y = F + r * (H + G) + sep * S;
      const label = perMicro ? station.micros[i].name : station.name;
      const lines = perMicro
        ? [1, 2].map((k) => `<line x1="${x + (W * k) / 3}" y1="${y}" x2="${x + (W * k) / 3}" y2="${y + H}"/>`).join("")
        : Array.from({ length: 9 }, (_, k) => `<line x1="${x + (W * (k + 1)) / 10}" y1="${y}" x2="${x + (W * (k + 1)) / 10}" y2="${y + H}"/>`).join("") +
          Array.from({ length: 5 }, (_, k) => `<line x1="${x}" y1="${y + (H * (k + 1)) / 6}" x2="${x + W}" y2="${y + (H * (k + 1)) / 6}"/>`).join("");
      cells += `<g><rect class="cell" data-i="${i}" x="${x}" y="${y}" width="${W}" height="${H}" rx="1.5" tabindex="0" role="button"><title>${label}</title></rect>
        <g stroke="rgba(255,255,255,.14)" stroke-width="${perMicro ? 0.8 : 0.6}" pointer-events="none">${lines}</g>
        ${perMicro && cfg.show_values ? `<text class="cellv" data-i="${i}" x="${x + W / 2}" y="${y + H - 9}"></text>` : ""}</g>`;
    }

    root.innerHTML = `<style>${STYLE}</style>
      <ha-card>
        <div class="head">
          <div style="min-width:0">
            <div class="title"></div>
            <div class="sub"></div>
          </div>
          <div class="power" tabindex="0" role="button"><span class="v"></span><span class="u"></span></div>
        </div>
        <svg viewBox="0 0 ${vw} ${vh}" role="img">
          <defs><linearGradient id="frame" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stop-color="#d9dde3"/><stop offset="1" stop-color="#9aa2ad"/></linearGradient></defs>
          <rect x="0" y="0" width="${vw}" height="${vh}" rx="5" fill="url(#frame)"/>
          <rect x="${F - 1.5}" y="${F - 1.5}" width="${vw - 2 * F + 3}" height="${vh - 2 * F + 3}" fill="#0c1424"/>
          ${cells}
        </svg>
        <dl class="plate">
          <div data-k="energy_today" role="button" tabindex="0"><dt>${tr.today}</dt><dd></dd></div>
          <div data-k="energy_month" role="button" tabindex="0"><dt>${tr.month}</dt><dd></dd></div>
          <div data-k="energy_total" role="button" tabindex="0"><dt>${tr.total}</dt><dd></dd></div>
        </dl>
      </ha-card>`;

    const activate = (el, fn) => {
      el.addEventListener("click", fn);
      el.addEventListener("keydown", (e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), fn()));
    };
    activate(root.querySelector(".power"), () => this._moreInfo(this._station?.entities.power));
    root.querySelectorAll(".plate > div").forEach((el) => activate(el, () => this._moreInfo(this._station?.entities[el.dataset.k])));
    root.querySelectorAll(".cell").forEach((el) =>
      activate(el, () => {
        const s = this._station;
        const i = +el.dataset.i;
        this._moreInfo(s && s.micros.length && this._config.show_panels ? s.micros[i]?.entities.power : s?.entities.power);
      })
    );
    this._els = {
      title: root.querySelector(".title"),
      sub: root.querySelector(".sub"),
      v: root.querySelector(".power .v"),
      u: root.querySelector(".power .u"),
      // Indexés par numéro d'onduleur (l'ordre du DOM suit le plan, pas la liste).
      cells: [...root.querySelectorAll(".cell")].reduce((a, el) => ((a[+el.dataset.i] = el), a), []),
      texts: [...root.querySelectorAll(".cellv")].reduce((a, el) => ((a[+el.dataset.i] = el), a), []),
      plate: [...root.querySelectorAll(".plate dd")],
    };
  }

  _render() {
    const hass = this._hass;
    if (!hass || !this._config) return;
    const tr = t(hass);
    const station = findStation(hass, this._config.device_id);
    this._station = station;

    if (!station) {
      const root = this.shadowRoot || this.attachShadow({ mode: "open" });
      if (this._sig !== "empty") root.innerHTML = `<style>${STYLE}</style><ha-card><div class="empty">${tr.no_station}</div></ha-card>`;
      this._sig = "empty";
      return;
    }

    const placement = this._placement(station, hass);
    const sig = [
      station.device.id,
      station.micros.map((m) => m.device.id + m.name).join(","),
      placement.slots.map((s) => `${s.i}:${s.r}:${s.c}`).join(","),
      JSON.stringify(this._config),
      tr === I18N.fr,
    ].join("|");
    if (sig !== this._sig) {
      this._build(station, tr, placement);
      this._sig = sig;
    }
    const els = this._els;
    const cfg = this._config;

    els.title.textContent = cfg.name || station.name;
    const p = fmt(hass, station.entities.power, 0);
    els.v.textContent = p.value;
    els.u.textContent = p.unit;

    // Ligne d'état : veille si la puissance est nulle et la dernière remontée ancienne.
    const lastIso = hass.states[station.entities.last_update]?.state;
    const power = num(hass, station.entities.power);
    const asleep = power === 0 && lastIso && Date.now() - new Date(lastIso) > 60 * 60000;
    const parts = [];
    if (station.micros.length) parts.push(tr.panels(station.micros.length));
    if (lastIso && !isNaN(new Date(lastIso))) parts.push(asleep ? tr.asleep(relTime(hass, lastIso)) : tr.updated(relTime(hass, lastIso)));
    els.sub.textContent = parts.join(", ");

    const perMicro = cfg.show_panels && station.micros.length > 0;
    if (perMicro) {
      station.micros.forEach((m, i) => {
        const w = num(hass, m.entities.power);
        const ratio = w == null ? 0 : w / (cfg.peak_power || 350);
        els.cells[i]?.setAttribute("fill", cellColor(ratio));
        const txt = els.texts[i];
        if (txt) {
          txt.textContent = w == null ? "" : `${Math.round(w)} W`;
          txt.setAttribute("fill", ratio > 0.55 ? "#0c1424" : "rgba(255,255,255,.92)");
        }
        const title = els.cells[i]?.querySelector("title");
        if (title) title.textContent = `${m.name}: ${w == null ? "—" : Math.round(w) + " W"}`;
      });
    } else {
      const peak = (cfg.peak_power || 350) * Math.max(1, station.micros.length);
      els.cells[0]?.setAttribute("fill", cellColor(power == null ? 0 : power / peak));
    }

    ["energy_today", "energy_month", "energy_total"].forEach((k, i) => {
      const f = fmt(hass, station.entities[k]);
      els.plate[i].innerHTML = "";
      els.plate[i].append(f.value);
      if (f.unit) {
        const s = document.createElement("small");
        s.textContent = f.unit;
        els.plate[i].append(s);
      }
    });
  }
}

if (!customElements.get("solenso-card")) {
  customElements.define("solenso-card", SolensoCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "solenso-card",
    name: "Solenso",
    description: t(document.querySelector("home-assistant")?.hass).description,
    preview: true,
    documentationURL: "https://github.com/pismache/ha-solenso",
  });
  console.info(`%c SOLENSO-CARD %c ${CARD_VERSION} `, "color:#0c1424;background:#56aaff;font-weight:600", "color:#56aaff");
}
