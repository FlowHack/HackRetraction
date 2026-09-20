/* HackRetraction UI — логика: форма, превью, генерация, настройки. */
"use strict";

/* Ссылка поддержки (заменить на реальную страницу при публикации). */
var SUPPORT_URL = "https://github.com/FlowHack/HackRetraction";

var state = {
  params: {},
  settings: {},
  ui: null,
  gcode: "",
  view: "top"
};

/* --- Мост с Python --- */
function post(msg) {
  if (typeof orca !== "undefined" && orca.postMessage) {
    orca.postMessage(msg);
  }
}

/* --- Локализация --- */
function text(key) {
  if (state.ui && state.ui.texts && state.ui.texts[key]) {
    return state.ui.texts[key];
  }
  return key;
}

function applyTexts() {
  var nodes = document.querySelectorAll("[data-text]");
  for (var i = 0; i < nodes.length; i++) {
    nodes[i].textContent = text(nodes[i].getAttribute("data-text"));
  }
  document.title = text("window_title");
}

/* --- Тема и шрифт --- */
function applyTheme(settings) {
  var theme = (settings && settings.theme) || "auto";
  document.body.setAttribute("data-theme", theme);
}

function applyFont(settings) {
  var size = (settings && settings.font_size) || 14;
  var style = (settings && settings.font_style) || "system";
  document.body.style.fontSize = size + "px";
  document.body.style.fontFamily =
    style === "mono" ? "var(--font-mono)" : "var(--font)";
}

/* --- Форма параметров --- */
function buildForm(ui, params) {
  var panel = document.getElementById("params-panel");
  var html = "";
  var sections = ui.sections || [];
  for (var s = 0; s < sections.length; s++) {
    var secKey = sections[s][0];
    var keys = sections[s][1];
    html += '<div class="sec" data-sec="' + secKey + '">';
    html += '<div class="sec-head"><span class="chevron">&#9660;</span><span>' +
      text(secKey) + "</span></div>";
    html += '<div class="sec-body">';
    for (var k = 0; k < keys.length; k++) {
      var key = keys[k];
      var label = ui.labels["p." + key] || key;
      var tip = ui.tips["t." + key] || "";
      var unit = ui.units[key] || "";
      var type = ui.types[key] || "number";
      var value = params[key] !== undefined ? params[key] : "";
      html += '<div class="field">';
      html += '<label title="' + esc(label) + '">' + esc(label) + "</label>";
      if (tip) {
        html += '<span class="tip" tabindex="0">?<span class="tip-text">' +
          esc(tip) + "</span></span>";
      }
      if (type === "textarea") {
        html += '<textarea data-param="' + key + '">' + esc(value) + "</textarea>";
      } else {
        html += '<input type="number" step="any" data-param="' + key +
          '" value="' + esc(value) + '">';
        if (unit) {
          html += '<span class="unit">' + esc(unit) + "</span>";
        }
      }
      html += "</div>";
    }
    html += "</div></div>";
  }
  panel.innerHTML = html;
}

function esc(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function collectParams() {
  var params = {};
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var key = el.getAttribute("data-param");
    var raw = el.value.trim();
    if (el.tagName === "TEXTAREA" || el.tagName === "textarea") {
      params[key] = el.value;
    } else if (raw !== "") {
      params[key] = Number(raw);
    }
  }
  return params;
}

function setFormValues(params) {
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var key = el.getAttribute("data-param");
    if (params[key] !== undefined) {
      el.value = params[key];
    }
  }
}

/* --- Превью --- */
function renderPreview(params) {
  var svg = document.getElementById("preview");
  if (state.view === "top") {
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.innerHTML = renderTop(params);
  } else {
    svg.setAttribute("viewBox", "0 0 100 100");
    svg.innerHTML = renderSide(params);
  }
}

function renderTop(p) {
  var dx = Number(p.dimensionX) || 220;
  var dy = Number(p.dimensionY) || 220;
  var srd = Number(p.startRetractiondistance) || 0;
  var ird = Number(p.incrementRetractiondistance) || 0;
  var scale = 90 / Math.max(dx, dy);
  var ox = (100 - dx * scale) / 2;
  var oy = (100 - dy * scale) / 2;
  var cx = ox + dx * scale / 2;
  var cy = oy + dy * scale / 2;
  var half = 30 * scale;

  var val = function (i) { return srd + ird * i; };
  var fmt = function (v) { return (Math.round(v * 100) / 100).toString(); };

  var h = "";
  h += '<rect x="' + ox + '" y="' + oy + '" width="' + dx * scale +
    '" height="' + dy * scale + '" fill="var(--panel)" stroke="var(--border)" stroke-width="0.4"/>';
  h += '<rect x="' + (cx - half) + '" y="' + (cy - half) + '" width="' + half * 2 +
    '" height="' + half * 2 + '" fill="none" stroke="var(--accent)" stroke-width="0.5"/>';

  /* Нижний ряд: 0 1 2 3 */
  for (var i = 0; i < 4; i++) {
    var x = cx - half + (i + 0.5) * (half * 2 / 4);
    h += '<text x="' + x + '" y="' + (cy + half + 4) + '" text-anchor="middle" ' +
      'font-size="3.4" fill="var(--accent)">' + fmt(val(i)) + "</text>";
  }
  /* Верхний ряд: 11 10 9 8 */
  for (var j = 0; j < 4; j++) {
    var x2 = cx - half + (j + 0.5) * (half * 2 / 4);
    h += '<text x="' + x2 + '" y="' + (cy - half - 2) + '" text-anchor="middle" ' +
      'font-size="3.4" fill="var(--accent)">' + fmt(val(11 - j)) + "</text>";
  }
  /* Левая сторона: 12 13 14 15 */
  for (var k = 0; k < 4; k++) {
    var y3 = cy - half + (k + 0.5) * (half * 2 / 4);
    h += '<text x="' + (cx - half - 2) + '" y="' + (y3 + 1.2) + '" text-anchor="end" ' +
      'font-size="3.4" fill="var(--accent)">' + fmt(val(12 + k)) + "</text>";
  }
  /* Правая сторона: 7 6 5 4 */
  for (var m = 0; m < 4; m++) {
    var y4 = cy - half + (m + 0.5) * (half * 2 / 4);
    h += '<text x="' + (cx + half + 2) + '" y="' + (y4 + 1.2) + '" text-anchor="start" ' +
      'font-size="3.4" fill="var(--accent)">' + fmt(val(7 - m)) + "</text>";
  }

  /* Надпись «перед» */
  h += '<text x="' + cx + '" y="' + (cy + half + 9) + '" text-anchor="middle" ' +
    'font-size="3" fill="var(--muted)">HACKRETRACTION</text>';
  return h;
}

function renderSide(p) {
  var nt = Math.max(1, Number(p.NumTests) || 1);
  var lt = Math.max(1, Number(p.layersTest) || 1);
  var lh = Number(p.layerHeight) || 0.2;
  var srs = Number(p.startRetractionspeed) || 0;
  var irs = Number(p.incrementRetractionspeed) || 0;
  var fs = Number(p.speedFan) || 0;
  var fsi = Number(p.speedFanIncrement) || 0;
  var tsh = Number(p.tempStarthotend) || 0;
  var tih = Number(p.tempIncrementhotend) || 0;

  var maxH = lt * lh;
  var maxSpeed = srs + irs * (nt - 1);
  var maxFan = fs + fsi * (nt - 1);
  var maxTemp = tsh + tih * (nt - 1);

  var plotW = 88;
  var plotH = 60;
  var baseY = 92;
  var bw = plotW / nt;
  var hScale = plotH / (maxH > 0 ? maxH : 1);
  var speedScale = plotH / (maxSpeed > 0 ? maxSpeed : 1);
  var fanScale = plotH / (maxFan > 0 ? maxFan : 1);
  var tempScale = plotH / (maxTemp > 0 ? maxTemp : 1);

  var h = "";
  h += '<rect x="4" y="' + (baseY - plotH) + '" width="' + plotW + '" height="' + plotH +
    '" fill="none" stroke="var(--border)" stroke-width="0.4"/>';
  h += '<line x1="4" y1="' + baseY + '" x2="' + (4 + plotW) + '" y2="' + baseY +
    '" stroke="var(--border)" stroke-width="0.4"/>';

  for (var i = 0; i < nt; i++) {
    var x = 4 + i * bw;
    var bh = Math.max(1.5, lt * lh * hScale);
    var speed = srs + irs * i;
    var fan = fs + fsi * i;
    var temp = tsh + tih * i;
    h += '<rect x="' + x + '" y="' + (baseY - bh) + '" width="' + (bw - 0.6) +
      '" height="' + bh + '" fill="var(--panel-2)" stroke="var(--accent)" stroke-width="0.3"/>';
    /* Полоска обдува (синяя) */
    if (fan > 0) {
      var fh = Math.min(bh, fan * fanScale);
      h += '<rect x="' + x + '" y="' + (baseY - fh) + '" width="' + (bw - 0.6) +
        '" height="' + fh + '" fill="#4a9eff" opacity="0.55"/>';
    }
    /* Полоска температуры (оранжевая) */
    if (temp > 0) {
      var th = Math.min(bh, temp * tempScale);
      h += '<rect x="' + x + '" y="' + (baseY - th) + '" width="' + (bw - 0.6) +
        '" height="' + th + '" fill="#ff9f3d" opacity="0.55"/>';
    }
    /* Подпись скорости ретракции */
    h += '<text x="' + (x + bw / 2) + '" y="' + (baseY + 4) + '" text-anchor="middle" ' +
      'font-size="2.6" fill="var(--accent)">' + (Math.round(speed * 10) / 10) + "</text>";
  }
  return h;
}

/* --- Статус --- */
function showStatus(key, params) {
  var el = document.getElementById("status-text");
  var t = text(key);
  if (params) {
    for (var k in params) {
      t = t.replace("{" + k + "}", String(params[k]));
    }
  }
  el.textContent = t;
}

/* --- Обработка сообщений Python --- */
function onMessage(msg) {
  if (!msg) return;
  switch (msg.type) {
    case "state":
      state.ui = msg.ui;
      state.params = msg.params || {};
      state.settings = msg.settings || {};
      applyTexts();
      applyTheme(state.settings);
      applyFont(state.settings);
      buildForm(state.ui, state.params);
      renderPreview(state.params);
      break;
    case "generated":
      state.gcode = msg.gcode || "";
      showStatus("status.generated");
      break;
    case "pulled":
      state.params = msg.params || {};
      setFormValues(state.params);
      renderPreview(state.params);
      showStatus(msg.status || "status.pull_ok");
      break;
    case "reset":
      state.params = msg.params || {};
      setFormValues(state.params);
      renderPreview(state.params);
      showStatus(msg.status || "status.reset_ok");
      break;
    case "loaded":
      state.params = msg.params || {};
      setFormValues(state.params);
      renderPreview(state.params);
      showStatus("status.loaded");
      break;
    case "settings_saved":
      if (msg.settings) {
        state.settings = msg.settings;
        applyTheme(state.settings);
        applyFont(state.settings);
      }
      if (msg.ok) {
        post({ type: "get_state" });
      }
      break;
    case "status":
      showStatus(msg.key, msg.params);
      break;
    case "error":
      showStatus("status.error", { error: msg.message });
      break;
  }
}

/* --- Кнопки --- */
function bindToolbar() {
  var map = {
    "btn-pull": function () { post({ type: "pull" }); },
    "btn-reset": function () { post({ type: "reset" }); },
    "btn-generate": function () {
      post({ type: "generate", params: collectParams() });
    },
    "btn-copy": function () {
      if (!state.gcode) {
        showStatus("status.copy_empty");
        return;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(state.gcode).then(function () {
          showStatus("status.copied");
        });
      } else {
        showStatus("status.copy_failed");
      }
    },
    "btn-save": function () {
      var path = window.prompt(text("status.path_placeholder"), "");
      if (path) {
        post({ type: "save", path: path });
      }
    },
    "btn-load": function () {
      var input = document.getElementById("file-input");
      input.click();
    },
    "btn-settings": function () { openSettings(); },
    "btn-support": function () { openSupport(); }
  };
  for (var id in map) {
    var el = document.getElementById(id);
    if (el) el.addEventListener("click", map[id]);
  }
}

/* --- Загрузка gcode из файла --- */
function bindFileInput() {
  var input = document.getElementById("file-input");
  input.addEventListener("change", function () {
    var file = input.files && input.files[0];
    if (!file) return;
    if (typeof FileReader !== "undefined" && FileReader.readAsText) {
      FileReader.readAsText(file, function (text) {
        post({ type: "load_gcode", gcode: text });
      });
    } else {
      var reader = new FileReaderCompat(file);
      reader.readAsText(function (text) {
        post({ type: "load_gcode", gcode: text });
      });
    }
    input.value = "";
  });
}

/* Fallback-чтение файла, если нет нативного FileReader (для тестов). */
function FileReaderCompat(file) {
  this.file = file;
}
FileReaderCompat.prototype.readAsText = function (cb) {
  var reader = new FileReader();
  reader.onload = function (e) {
    cb(e.target.result);
  };
  reader.readAsText(this.file);
};

/* --- Секции (сворачивание) --- */
function bindSections() {
  var heads = document.querySelectorAll(".sec-head");
  for (var i = 0; i < heads.length; i++) {
    heads[i].addEventListener("click", function () {
      var sec = this.parentElement;
      sec.classList.toggle("collapsed");
    });
  }
}

/* --- Модалки --- */
function openSettings() {
  var modal = document.getElementById("settings-modal");
  var s = state.settings || {};
  setSelect("set-theme", s.theme || "auto");
  setSelect("set-font-size", String(s.font_size || 14));
  setSelect("set-font", s.font_style || "system");
  setSelect("set-language", s.language || "en");
  setSelect("set-comment-lang", s.comment_lang || "en");
  modal.classList.remove("hidden");
}

function setSelect(id, value) {
  var el = document.getElementById(id);
  if (!el) return;
  for (var i = 0; i < el.options.length; i++) {
    if (el.options[i].value === value) {
      el.selectedIndex = i;
      return;
    }
  }
}

function closeSettings() {
  var modal = document.getElementById("settings-modal");
  modal.classList.add("hidden");
  var settings = {
    theme: getSelect("set-theme"),
    font_size: Number(getSelect("set-font-size")),
    font_style: getSelect("set-font"),
    language: getSelect("set-language"),
    comment_lang: getSelect("set-comment-lang")
  };
  post({ type: "settings", settings: settings });
}

function getSelect(id) {
  var el = document.getElementById(id);
  return el ? el.value : "";
}

function openSupport() {
  var modal = document.getElementById("support-modal");
  var link = document.getElementById("support-link");
  link.href = SUPPORT_URL;
  modal.classList.remove("hidden");
}

function bindModals() {
  document.getElementById("settings-close").addEventListener("click", closeSettings);
  document.getElementById("support-close").addEventListener("click", function () {
    document.getElementById("support-modal").classList.add("hidden");
  });
  document.getElementById("settings-modal").addEventListener("click", function (e) {
    if (e.target === this) closeSettings();
  });
  document.getElementById("support-modal").addEventListener("click", function (e) {
    if (e.target === this) this.classList.add("hidden");
  });
}

/* --- Переключение вида превью --- */
function bindPreviewTabs() {
  var tabs = document.querySelectorAll(".ptab");
  for (var i = 0; i < tabs.length; i++) {
    tabs[i].addEventListener("click", function () {
      var view = this.getAttribute("data-view");
      state.view = view;
      var all = document.querySelectorAll(".ptab");
      for (var j = 0; j < all.length; j++) {
        all[j].classList.remove("active");
      }
      this.classList.add("active");
      renderPreview(collectParams());
    });
  }
}

/* --- Инициализация --- */
function init() {
  if (typeof orca !== "undefined" && orca.onMessage) {
    orca.onMessage(onMessage);
  }
  bindToolbar();
  bindFileInput();
  bindModals();
  bindPreviewTabs();
  post({ type: "get_state" });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}