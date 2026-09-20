/* HackRetraction UI — логика: форма, превью, генерация, настройки. */
"use strict";

var state = {
  params: {},
  settings: {},
  ui: null,
  gcode: ""
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
        html += '<span class="tip" tabindex="0" data-tip="' + esc(tip) + '">?</span>';
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
  bindSections();
  bindLivePreview();
  bindTips();
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

/* --- Live-обновление превью при изменении параметров --- */
function bindLivePreview() {
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("input", function () {
      renderPreview(collectParams());
    });
  }
}

/* --- Тултипы через JS (fixed, не обрезаются панелью) --- */
function bindTips() {
  var tips = document.querySelectorAll(".tip");
  for (var i = 0; i < tips.length; i++) {
    tips[i].addEventListener("mouseenter", showTip);
    tips[i].addEventListener("mouseleave", hideTip);
    tips[i].addEventListener("focus", showTip);
    tips[i].addEventListener("blur", hideTip);
  }
}

function showTip(e) {
  var tip = e.currentTarget;
  var box = document.getElementById("tip-box");
  if (!box) return;
  box.textContent = tip.getAttribute("data-tip") || "";
  var r = tip.getBoundingClientRect();
  var left = r.right + 8;
  var top = r.top;
  if (left + 270 > window.innerWidth) {
    left = r.left - 8 - 260;
  }
  if (top + 200 > window.innerHeight) {
    top = window.innerHeight - 200;
  }
  if (top < 4) top = 4;
  box.style.left = left + "px";
  box.style.top = top + "px";
  box.classList.add("visible");
}

function hideTip() {
  var box = document.getElementById("tip-box");
  if (box) box.classList.remove("visible");
}

/* --- Превью --- */
function renderPreview(params) {
  var side = document.getElementById("preview-side");
  var top = document.getElementById("preview-top");
  if (side) {
    side.setAttribute("viewBox", "0 0 100 100");
    side.innerHTML = renderSide(params);
  }
  if (top) {
    top.setAttribute("viewBox", "0 0 100 100");
    top.innerHTML = renderTop(params);
  }
}

function fmtNum(v) {
  return (Math.round(v * 100) / 100).toString();
}

/* Вид сверху: квадратная подложка со стенками, засечки, надпись. */
function renderTop(p) {
  var dx = Number(p.dimensionX) || 220;
  var dy = Number(p.dimensionY) || 220;
  var srd = Number(p.startRetractiondistance) || 0;
  var ird = Number(p.incrementRetractiondistance) || 0;

  var scale = 78 / Math.max(dx, dy);
  var ox = (100 - dx * scale) / 2;
  var oy = (100 - dy * scale) / 2;
  var cx = ox + dx * scale / 2;
  var cy = oy + dy * scale / 2;
  var half = 30 * scale;

  var val = function (i) { return srd + ird * i; };
  var fs = 3.2;

  var h = "";
  /* Стол */
  h += '<rect x="' + ox + '" y="' + oy + '" width="' + dx * scale +
    '" height="' + dy * scale + '" fill="var(--panel)" stroke="var(--border)" stroke-width="0.4"/>';
  /* Квадратная подложка со стенками (обвести в квадрат) */
  h += '<rect x="' + (cx - half) + '" y="' + (cy - half) + '" width="' + half * 2 +
    '" height="' + half * 2 + '" fill="var(--accent-soft)" stroke="var(--accent)" stroke-width="0.6"/>';

  /* Засечки + значения: низ 0-3, верх 11-8, лево 12-15, право 7-4 */
  var tick = function (x1, y1, x2, y2, tx, ty, v, anchor) {
    h += '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 +
      '" stroke="var(--accent)" stroke-width="0.3"/>';
    h += '<text x="' + tx + '" y="' + ty + '" text-anchor="' + anchor +
      '" font-size="' + fs + '" font-family="var(--font-mono)" fill="var(--accent)">' +
      fmtNum(v) + "</text>";
  };

  /* Низ (0-3): засечка вниз от нижней стенки */
  for (var i = 0; i < 4; i++) {
    var x = cx - half + (i + 0.5) * (half * 2 / 4);
    tick(x, cy + half, x, cy + half + 3, x, cy + half + 6.5, val(i), "middle");
  }
  /* Верх (11-8): засечка вверх от верхней стенки */
  for (var j = 0; j < 4; j++) {
    var x2 = cx - half + (j + 0.5) * (half * 2 / 4);
    tick(x2, cy - half, x2, cy - half - 3, x2, cy - half - 4.5, val(11 - j), "middle");
  }
  /* Лево (12-15): засечка влево */
  for (var k = 0; k < 4; k++) {
    var y3 = cy - half + (k + 0.5) * (half * 2 / 4);
    tick(cx - half, y3, cx - half - 3, y3, cx - half - 4, y3 + 1.2, val(12 + k), "end");
  }
  /* Право (7-4): засечка вправо */
  for (var m = 0; m < 4; m++) {
    var y4 = cy - half + (m + 0.5) * (half * 2 / 4);
    tick(cx + half, y4, cx + half + 3, y4, cx + half + 4, y4 + 1.2, val(7 - m), "start");
  }

  /* Надпись «перед» под квадратом */
  h += '<text x="' + cx + '" y="' + (cy + half + 12) + '" text-anchor="middle" ' +
    'font-size="3.4" font-family="var(--font-mono)" letter-spacing="1" fill="var(--muted)">' +
    "HACKRETRACTION</text>";
  return h;
}

/* Вид сбоку (вертикальный): блоки снизу вверх, засечки, обдув/температура. */
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

  var maxH = nt * lt * lh;
  var maxSpeed = srs + irs * (nt - 1);
  var maxFan = fs + fsi * (nt - 1);
  var maxTemp = tsh + tih * (nt - 1);

  /* Масштаб с запасом: учитываем и высоту, и скорость, и температуру, и обдув. */
  var plotW = 62;
  var plotH = 78;
  var baseY = 92;
  var leftPad = 26; /* место под засечки скорости */
  var rightPad = 20; /* место под засечки температуры/обдува */
  var bw = plotW / nt;
  var hScale = plotH / Math.max(maxH, maxSpeed, maxFan, maxTemp, 1);

  var h = "";
  /* Рамка графика */
  h += '<rect x="' + (leftPad) + '" y="' + (baseY - plotH) + '" width="' + plotW +
    '" height="' + plotH + '" fill="none" stroke="var(--border)" stroke-width="0.4"/>';
  h += '<line x1="' + leftPad + '" y1="' + baseY + '" x2="' + (leftPad + plotW) +
    '" y2="' + baseY + '" stroke="var(--border)" stroke-width="0.4"/>';

  for (var i = 0; i < nt; i++) {
    var x = leftPad + i * bw;
    var bh = Math.max(1.5, lt * lh * hScale);
    var yTop = baseY - (i + 1) * bh;
    var speed = srs + irs * i;
    var fan = fs + fsi * i;
    var temp = tsh + tih * i;

    /* Блок */
    h += '<rect x="' + x + '" y="' + yTop + '" width="' + (bw - 0.6) +
      '" height="' + bh + '" fill="var(--panel-2)" stroke="var(--accent)" stroke-width="0.3"/>';
    /* Полоска обдува (синяя) */
    if (fan > 0) {
      var fh = Math.min(bh, fan * hScale);
      h += '<rect x="' + x + '" y="' + (yTop + bh - fh) + '" width="' + (bw - 0.6) +
        '" height="' + fh + '" fill="#4a9eff" opacity="0.5"/>';
    }
    /* Полоска температуры (оранжевая) */
    if (temp > 0) {
      var th = Math.min(bh, temp * hScale);
      h += '<rect x="' + x + '" y="' + (yTop + bh - th) + '" width="' + (bw - 0.6) +
        '" height="' + th + '" fill="#ff9f3d" opacity="0.5"/>';
    }

    /* Засечка скорости слева */
    var sy = yTop + bh / 2;
    h += '<line x1="' + (leftPad - 3) + '" y1="' + sy + '" x2="' + leftPad +
      '" y2="' + sy + '" stroke="var(--accent)" stroke-width="0.3"/>';
    h += '<text x="' + (leftPad - 4) + '" y="' + (sy + 1.2) + '" text-anchor="end" ' +
      'font-size="2.6" font-family="var(--font-mono)" fill="var(--accent)">' +
      (Math.round(speed * 10) / 10) + "</text>";
  }

  /* Подписи осей */
  h += '<text x="' + (leftPad + plotW / 2) + '" y="' + (baseY + 5) +
    '" text-anchor="middle" font-size="2.6" fill="var(--muted)">' +
    text("preview.side") + "</text>";
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

/* --- Копирование с fallback --- */
function copyText(value, okKey) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(function () {
      showStatus(okKey);
    }, function () {
      legacyCopy(value, okKey);
    });
  } else {
    legacyCopy(value, okKey);
  }
}

function legacyCopy(value, okKey) {
  var ta = document.createElement("textarea");
  ta.value = value;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  var ok = false;
  try {
    ok = document.execCommand("copy");
  } catch (e) {
    ok = false;
  }
  document.body.removeChild(ta);
  showStatus(ok ? okKey : "status.copy_failed");
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
    "btn-help": function () { openHelp(); },
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
      copyText(state.gcode, "status.copied");
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
    var reader = new FileReader();
    reader.onload = function (e) {
      post({ type: "load_gcode", gcode: e.target.result });
    };
    reader.readAsText(file);
    input.value = "";
  });
}

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

/* --- Настройки (применение в реальном времени) --- */
function openSettings() {
  var modal = document.getElementById("settings-modal");
  var s = state.settings || {};
  setSelect("set-theme", s.theme || "auto");
  setRange("set-font-size", s.font_size || 14);
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

function setRange(id, value) {
  var el = document.getElementById(id);
  if (!el) return;
  el.value = value;
  var val = document.getElementById("set-font-size-val");
  if (val) val.textContent = value;
}

function getSelect(id) {
  var el = document.getElementById(id);
  return el ? el.value : "";
}

function getRange(id) {
  var el = document.getElementById(id);
  return el ? Number(el.value) : 14;
}

function collectSettings() {
  return {
    theme: getSelect("set-theme"),
    font_size: getRange("set-font-size"),
    font_style: getSelect("set-font"),
    language: getSelect("set-language"),
    comment_lang: getSelect("set-comment-lang")
  };
}

/* Применение настроек в реальном времени по смене значения. */
function bindSettingsLive() {
  var ids = ["set-theme", "set-font-size", "set-font", "set-language", "set-comment-lang"];
  for (var i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    if (!el) continue;
    el.addEventListener("change", function () {
      post({ type: "settings", settings: collectSettings() });
    });
    el.addEventListener("input", function () {
      post({ type: "settings", settings: collectSettings() });
    });
  }
  var fs = document.getElementById("set-font-size");
  if (fs) {
    fs.addEventListener("input", function () {
      var val = document.getElementById("set-font-size-val");
      if (val) val.textContent = fs.value;
    });
  }
}

function closeSettings() {
  var modal = document.getElementById("settings-modal");
  modal.classList.add("hidden");
  post({ type: "settings", settings: collectSettings() });
}

/* --- Поддержка --- */
function renderDonate(donate) {
  var list = document.getElementById("donate-list");
  if (!list || !donate) return;
  var html = "";
  for (var i = 0; i < donate.length; i++) {
    var d = donate[i];
    html += '<div class="donate-card">';
    html += '<span class="d-title">' + esc(d.title) + "</span>";
    html += '<span class="d-value" title="' + esc(d.value) + '">' + esc(d.value) + "</span>";
    html += '<span class="d-actions">';
    html += '<button class="btn" data-copy="' + esc(d.value) + '">' +
      text("donate.copy") + "</button>";
    if (d.url) {
      html += '<a class="btn" href="' + esc(d.url) + '" target="_blank" rel="noopener">' +
        text("donate.open") + "</a>";
    }
    html += "</span></div>";
  }
  list.innerHTML = html;
  var btns = list.querySelectorAll("[data-copy]");
  for (var j = 0; j < btns.length; j++) {
    btns[j].addEventListener("click", function () {
      copyText(this.getAttribute("data-copy"), "donate.copied");
    });
  }
}

function openSupport() {
  var modal = document.getElementById("support-modal");
  renderDonate(state.ui && state.ui.donate);
  modal.classList.remove("hidden");
}

/* --- Помощь --- */
function renderHelp() {
  var box = document.getElementById("help-content");
  if (!box) return;
  var keys = ["help.what", "help.steps", "help.read_top", "help.read_side",
    "help.pick", "help.rules", "help.tips"];
  var titles = ["help.what", "help.steps", "help.read_top", "help.read_side",
    "help.pick", "help.rules", "help.tips"];
  var html = "";
  for (var i = 0; i < keys.length; i++) {
    var t = text(titles[i]);
    var body = text(keys[i]);
    html += "<h3>" + esc(t) + "</h3>";
    if (keys[i] === "help.steps") {
      var steps = body.split("\n");
      html += "<ol>";
      for (var s = 0; s < steps.length; s++) {
        html += "<li>" + esc(steps[s]) + "</li>";
      }
      html += "</ol>";
    } else {
      html += "<p>" + esc(body) + "</p>";
    }
  }
  html += '<div class="help-source">' + esc(text("help.source")) + "</div>";
  box.innerHTML = html;
}

function openHelp() {
  var modal = document.getElementById("help-modal");
  renderHelp();
  modal.classList.remove("hidden");
}

function bindModals() {
  document.getElementById("settings-close").addEventListener("click", closeSettings);
  document.getElementById("support-close").addEventListener("click", function () {
    document.getElementById("support-modal").classList.add("hidden");
  });
  document.getElementById("help-close").addEventListener("click", function () {
    document.getElementById("help-modal").classList.add("hidden");
  });
  document.getElementById("settings-modal").addEventListener("click", function (e) {
    if (e.target === this) closeSettings();
  });
  document.getElementById("support-modal").addEventListener("click", function (e) {
    if (e.target === this) this.classList.add("hidden");
  });
  document.getElementById("help-modal").addEventListener("click", function (e) {
    if (e.target === this) this.classList.add("hidden");
  });
}

/* --- Инициализация --- */
function init() {
  if (typeof orca !== "undefined" && orca.onMessage) {
    orca.onMessage(onMessage);
  }
  bindToolbar();
  bindFileInput();
  bindModals();
  bindSettingsLive();
  post({ type: "get_state" });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
