/* HackRetraction UI — логика: форма, превью, генерация, настройки. */
"use strict";

var state = {
  params: {},
  settings: {},
  ui: null,
  gcode: "",
  defaultStartGcode: "",
  defaultEndGcode: ""
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
      /* None (не подтянуто) → пустое поле, а не "null". */
      var value = params[key] !== undefined && params[key] !== null ? params[key] : "";
      html += '<div class="field">';
      /* Кнопка сброса к рекомендуемому значению — первой в строке (видна при отличии). */
      html += '<button type="button" class="btn-reset-param" data-reset-param="' +
        key + '" data-tip="t.reset_param">&#10227;</button>';
      html += '<label title="' + esc(label) + '">' + esc(label) + "</label>";
      /* «Вопросик» рендерится всегда (занимает колонку сетки), но пустой data-tip
         тултип не показывает — так поля выровнены по колонкам. */
      var tipAttr = tip ? ' tabindex="0"' : "";
      html += '<span class="tip"' + tipAttr + ' data-tip="' + esc(tip) + '">' +
        (tip ? "?" : "") + "</span>";
      if (type === "textarea") {
        /* Полям стартового/конечного gcode — увеличенная высота (см. .gcode-field). */
        var taClass = (key === "startGcode" || key === "endGcode") ? ' class="gcode-field"' : "";
        html += '<textarea' + taClass + ' data-param="' + key + '">' + esc(value) + "</textarea>";
        /* Кнопки для стартового/конечного gcode: «Рекомендованный» (дефолтный
           рассчитанный gcode) и «Подтянуть значение» (из профиля). */
        if (key === "startGcode" || key === "endGcode") {
          html += '<div class="gcode-btns">';
          html += '<button type="button" class="btn btn-default-gcode" ' +
            'data-default-gcode="' + key + '" data-tip="t.default_gcode">' +
            esc(text("btn.default_gcode")) + "</button>";
          html += '<button type="button" class="btn btn-pull-gcode" ' +
            'data-pull-gcode="' + key + '" data-tip="t.pull_gcode">' +
            esc(text("btn.pull_gcode")) + "</button>";
          html += "</div>";
        }
      } else {
        /* Шаги инкрементальных параметров не могут быть отрицательными. */
        var min = STEP_KEYS.indexOf(key) >= 0 ? ' min="0"' : "";
        /* Явный шаг стрелочек из ui.steps (иначе "any"). */
        var step = (ui.steps && ui.steps[key]) || "any";
        html += '<span class="input-wrap">';
        html += '<input type="number" step="' + step + '" data-param="' + key +
          '" value="' + esc(value) + '"' + min + ">";
        if (unit) {
          html += '<span class="unit">' + esc(unit) + "</span>";
        }
        html += "</span>";
      }
      html += "</div>";
    }
    html += "</div></div>";
  }
  panel.innerHTML = html;
  bindSections();
  bindLivePreview();
  bindTips();
  bindDefaultGcodeButtons();
  bindPullGcodeButtons();
  applyStepLock(params);
  bindResetParamButtons();
  updateResetButtons();
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
    } else if (STEP_KEYS.indexOf(key) >= 0) {
      /* Поля тройки всегда присутствуют: пустое → 0, иначе Python сохранит
         устаревшее значение из прошлой генерации (валидация пропускает их). */
      params[key] = 0;
    }
  }
  return params;
}

/* --- Валидация пустых числовых полей --- */
function fieldLabel(key) {
  var lbl = label("p." + key);
  return lbl === "p." + key ? key : lbl;
}

function markFieldError(key) {
  var el = document.querySelector('[data-param="' + key + '"]');
  if (!el) return;
  el.classList.add("field-error");
  var field = el.closest ? el.closest(".field") : null;
  if (field) field.classList.add("field-error");
}

function clearFieldError(key) {
  var el = document.querySelector('[data-param="' + key + '"]');
  if (!el) return;
  el.classList.remove("field-error");
  var field = el.closest ? el.closest(".field") : null;
  if (field) field.classList.remove("field-error");
}

/* --- Кнопки сброса полей к рекомендуемым значениям --- */
function updateResetButtons() {
  var rec = state.recommended || {};
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var key = el.getAttribute("data-param");
    /* Кнопка — сосед .input-wrap в .field (label | tip/wrap | button). */
    var field = el.closest ? el.closest(".field") : el.parentElement.parentElement;
    var btn = field ? field.querySelector(".btn-reset-param") : null;
    if (!btn) continue;
    var rv;
    if (el.tagName === "TEXTAREA" || el.tagName === "textarea") {
      /* Для gcode-полей рекомендуемое — рассчитанный дефолтный gcode. */
      rv = key === "startGcode" ? state.defaultStartGcode : state.defaultEndGcode;
    } else {
      rv = rec[key];
    }
    var show;
    if (el.tagName === "TEXTAREA" || el.tagName === "textarea") {
      show = rv !== undefined && rv !== null && String(el.value) !== String(rv);
    } else {
      show = rv !== undefined && rv !== null && num(el.value, NaN) !== num(rv, NaN);
    }
    btn.classList.toggle("visible", show);
  }
}

function bindResetParamButtons() {
  var btns = document.querySelectorAll(".btn-reset-param");
  for (var i = 0; i < btns.length; i++) {
    btns[i].addEventListener("click", function () {
      var key = this.getAttribute("data-reset-param");
      var el = document.querySelector('[data-param="' + key + '"]');
      if (!el) return;
      var rv;
      if (el.tagName === "TEXTAREA" || el.tagName === "textarea") {
        /* gcode-поле: возврат к рекомендованному (рассчитанному) gcode. */
        rv = key === "startGcode" ? state.defaultStartGcode : state.defaultEndGcode;
      } else {
        rv = (state.recommended || {})[key];
      }
      if (rv === undefined || rv === null) return;
      el.value = rv;
      state.params[key] = rv;
      updateResetButtons();
      applyStepLock(state.params);
      renderPreview(state.params);
      clearFieldError(key);
    });
  }
}

function validateNumericFields() {
  var empty = [];
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    /* Текстовые поля gcode и заблокированные поля пропускаем. */
    if (el.tagName === "TEXTAREA" || el.tagName === "textarea") continue;
    if (el.disabled) continue;
    var key = el.getAttribute("data-param");
    /* Поля тройки могут быть пустыми — их проверяет _validate_steps
       (ровно одно из трёх должно быть ненулевым). */
    if (STEP_KEYS.indexOf(key) >= 0) continue;
    if (el.value.trim() === "") {
      empty.push({ key: key, label: fieldLabel(key) });
    }
  }
  return empty;
}

function requestGenerate() {
  var empty = validateNumericFields();
  if (empty.length === 0) return true;
  var names = [];
  for (var i = 0; i < empty.length; i++) {
    names.push(empty[i].label);
    markFieldError(empty[i].key);
  }
  showToast("status.field_empty", { field: names.join(", ") });
  return false;
}

function setFormValues(params) {
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    var el = inputs[i];
    var key = el.getAttribute("data-param");
    if (params[key] !== undefined) {
      /* None → очистить поле (значение не подтянуто/сброшено). */
      el.value = params[key] === null ? "" : params[key];
    }
  }
}

/* --- Live-обновление превью при изменении параметров --- */
function bindLivePreview() {
  var inputs = document.querySelectorAll("[data-param]");
  for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("input", function () {
      /* Снятие подсветки ошибки при изменении поля. */
      clearFieldError(this.getAttribute("data-param"));
      var params = collectParams();
      applyStepLock(params);
      updateResetButtons();
      renderPreview(params);
      /* Пересчёт дефолтных gcode при смене зависимых значений (размеры
         стола, температуры) — только если поле gcode не редактировалось
         пользователем (равно дефолту). */
      var key = this.getAttribute("data-param");
      if (key === "dimensionX" || key === "dimensionY" ||
          key === "tempBed" || key === "tempStarthotend") {
        recalcDefaultsIfUnmodified(params);
      }
    });
    /* Снятие подсветки и по change (например, стрелки спиннера). */
    inputs[i].addEventListener("change", function () {
      clearFieldError(this.getAttribute("data-param"));
    });
  }
}

/* Кнопки «По умолчанию» у полей стартового/конечного gcode. */
function bindDefaultGcodeButtons() {
  var buttons = document.querySelectorAll("[data-default-gcode]");
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener("click", function () {
      /* Передаём текущие значения формы: Python заменит ТОЛЬКО целевое
         поле, не затирая пользовательский ввод в соседнем gcode-поле. */
      post({
        type: "default_gcode",
        field: this.getAttribute("data-default-gcode"),
        params: collectParams()
      });
    });
  }
}

/* Кнопки «Подтянуть значение» у полей стартового/конечного gcode. */
function bindPullGcodeButtons() {
  var buttons = document.querySelectorAll("[data-pull-gcode]");
  for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener("click", function () {
      post({
        type: "pull_gcode",
        field: this.getAttribute("data-pull-gcode"),
        params: collectParams()
      });
    });
  }
}

/* Если оба поля gcode не тронуты — запрашиваем пересчёт дефолтов. */
function recalcDefaultsIfUnmodified(params) {
  var startEl = document.querySelector('[data-param="startGcode"]');
  var endEl = document.querySelector('[data-param="endGcode"]');
  if (!startEl || !endEl) return;
  var startUnmodified = startEl.value === state.defaultStartGcode;
  var endUnmodified = endEl.value === state.defaultEndGcode;
  if (startUnmodified || endUnmodified) {
    post({ type: "recalc_default_gcode", params: params });
  }
}

/* --- Тултипы через JS (fixed, не обрезаются панелью) --- */
function bindTips() {
  /* Делегирование: data-tip есть у «вопросиков», кнопок тулбара, кнопок
     полей и заблокированных .input-wrap (тройка шагов). Один обработчик
     на документ — работает и для элементов, добавленных позже. */
  document.addEventListener("mouseover", function (e) {
    var el = e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!el) return;
    var rel = e.relatedTarget;
    if (rel && rel.closest && rel.closest("[data-tip]") === el) return;
    showTipFor(el);
  });
  document.addEventListener("mouseout", function (e) {
    var el = e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
    if (!el) return;
    var rel = e.relatedTarget;
    if (rel && rel.closest && rel.closest("[data-tip]") === el) return;
    hideTip();
  });
}

function showTipFor(tip) {
  var box = document.getElementById("tip-box");
  if (!box) return;
  /* data-tip может содержать ключ перевода (t.*) — резолвим в текст. */
  var key = tip.getAttribute("data-tip") || "";
  /* Пустой data-tip (незаблокированное поле тройки) — тултип не показываем. */
  if (!key) return;
  box.textContent = key.indexOf("t.") === 0 ? tip(key) : key;
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
var lastPreviewParams = {};

function renderPreview(params) {
  lastPreviewParams = params || {};
  var side = document.getElementById("preview-side");
  var top = document.getElementById("preview-top");
  if (side) side.innerHTML = renderSide(params);
  if (top) top.innerHTML = renderTop(params);
  fitPreviews();
}

/* --- Масштабирование превью под размер контейнера --- */
var sideScale = 1;

function fitPreviews() {
  fitTopView();
  fitSideView();
}

/* Вид сверху: квадрат вписывается в контейнер и по ширине, и по высоте
   (пропорции сохраняются); базовый шрифт масштабируется вместе с ним —
   подписи заданы в em и тянутся за шрифтом. */
function fitTopView() {
  var wrap = document.querySelector(".preview-block.top .preview-wrap");
  var stage = document.getElementById("preview-top");
  if (!wrap || !stage) return;
  var r = wrap.getBoundingClientRect();
  var size = Math.max(140, Math.min(320, r.width - 16, r.height - 16));
  stage.style.width = size + "px";
  stage.style.height = size + "px";
  stage.style.fontSize = Math.round(size * 0.045) + "px";
}

/* Вид сбоку: масштабируется по высоте контейнера (текст и блоки в em). */
function fitSideView() {
  var wrap = document.querySelector(".preview-block.side .preview-wrap");
  var tower = document.getElementById("preview-side");
  if (!wrap || !tower) return;
  var r = wrap.getBoundingClientRect();
  var availH = Math.max(40, r.height - 24);
  var nt = Math.max(1, Math.round(num(lastPreviewParams.NumTests, 1)));
  var lt = Math.max(1, num(lastPreviewParams.layersTest, 1));
  var naturalH = nt * Math.max(6, Math.round(lt * 1.2));
  var k = Math.min(1.5, Math.max(0.3, availH / naturalH));
  /* Пол блока (6px) масштабируется вместе с k: иначе при малых
     слоях на тест башня не может сжаться и появляется скролл. */
  var blockH = Math.max(6 * k, Math.round(lt * 1.2 * k));
  if (nt * blockH > availH) {
    k = Math.max(0.3, (availH -  2) / (nt * Math.max(6, lt * 1.2)));
  }
  if (Math.abs(k - sideScale) < 0.01) return;
  sideScale = k;
  tower.style.fontSize = Math.round(14 * k) + "px";
  tower.innerHTML = renderSide(lastPreviewParams);
}

function num(v, d) {
  var n = Number(v);
  return isNaN(n) ? d : n;
}

function fmtNum(v) {
  return (Math.round(v * 100) / 100).toString();
}

/* Вид сверху: квадрат с точками дистанции ретракции по периметру. */
function renderTop(p) {
  var srd = num(p.startRetractiondistance, 0);
  var ird = num(p.incrementRetractiondistance, 0);
  var val = function (i) { return fmtNum(srd + ird * i); };

  /* Длинные значения -> класс small (мельче шрифт, чтобы не сливались). */
  var maxLen = 0;
  for (var i = 0; i < 16; i++) {
    var len = val(i).length;
    if (len > maxLen) maxLen = len;
  }
  var labelCls = maxLen > 4 ? "topview-label small" : "topview-label";

  /* Точка на линии рамки + подпись снаружи (pos — сторона квадрата). */
  var dot = function (x, y, v, pos) {
    return '<div class="topview-dot" style="left:' + x + '%;top:' + y + '%"></div>' +
      '<div class="' + labelCls + '" data-pos="' + pos + '" style="left:' + x +
      '%;top:' + y + '%">' + v + "</div>";
  };

  var h = '<div class="topview-square-wrap">';
  h += '<div class="topview-square"></div>';
  /* Низ (0-3): подписи под квадратом */
  for (var i = 0; i < 4; i++) {
    h += dot((i + 0.5) * 25, 100, val(i), "bottom");
  }
  /* Верх (11-8): подписи над квадратом */
  for (var j = 0; j < 4; j++) {
    h += dot((j + 0.5) * 25, 0, val(11 - j), "top");
  }
  /* Лево (12-15): подписи слева */
  for (var k = 0; k < 4; k++) {
    h += dot(0, (k + 0.5) * 25, val(12 + k), "left");
  }
  /* Право (7-4): подписи справа */
  for (var m = 0; m < 4; m++) {
    h += dot(100, (m + 0.5) * 25, val(7 - m), "right");
  }
  h += "</div>";
  /* Надпись «перед» под квадратом, по ширине самого вида: буквы
     распределяются по всей ширине (как бренд на передней кромке стола). */
  var front = "HACKRETRACTION";
  var letters = "";
  for (var i = 0; i < front.length; i++) {
    letters += "<span>" + front[i] + "</span>";
  }
  h += '<div class="topview-front">' + letters + "</div>";
  return h;
}

/* Вид сбоку: монолитная башня из ячеек (column-reverse), подписи справа.
   Точки на стыках ячеек — со стороны инкрементного параметра (справа). */
function renderSide(p) {
  var nt = Math.max(1, Math.round(num(p.NumTests, 1)));
  var lt = Math.max(1, num(p.layersTest, 1));
  var srs = num(p.startRetractionspeed, 0);
  var irs = num(p.incrementRetractionspeed, 0);
  var fs = num(p.speedFan, 0);
  var fsi = num(p.speedFanIncrement, 0);
  var tsh = num(p.tempStarthotend, 0);
  var tih = num(p.tempIncrementhotend, 0);

  /* Показываем только параметры с ненулевым шагом (динамические). */
  var showSpeed = irs !== 0;
  var showFan = fsi !== 0;
  var showTemp = tih !== 0;
  var hasStep = showSpeed || showFan || showTemp;

  /* Высота блока пропорциональна слоям на тест (1.2px на слой);
     sideScale — масштаб по высоте контейнера (см. fitSideView). */
  var blockH = Math.max(6 * sideScale, Math.round(lt * 1.2 * sideScale));

  var h = '<div class="tower">';
  for (var i = 0; i < nt; i++) {
    h += '<div class="tower-row" style="height:' + blockH + 'px">';
    h += '<div class="tower-block">';
    /* Точка на стыке ячеек (кроме верхнего блока), справа у параметров. */
    if (hasStep && i < nt - 1) {
      h += '<span class="tower-dot"></span>';
    }
    h += "</div>";
    h += '<div class="tower-labels">';
    if (showSpeed) {
      h += '<span class="lbl lbl-speed">' + fmtNum(srs + irs * i) + " мм/с</span>";
    }
    if (showFan) {
      h += '<span class="lbl lbl-fan">' + fmtNum(fs + fsi * i) + " %</span>";
    }
    if (showTemp) {
      h += '<span class="lbl lbl-temp">' + fmtNum(tsh + tih * i) + " °C</span>";
    }
    h += "</div></div>";
  }
  h += "</div>";
  return h;
}

/* --- Блокировка шагов: только один из трёх инкрементов может быть ненулевым --- */
var STEP_KEYS = ["incrementRetractionspeed", "tempIncrementhotend", "speedFanIncrement"];

function label(key) {
  if (state.ui && state.ui.labels && state.ui.labels[key]) {
    return state.ui.labels[key];
  }
  return key;
}

function tip(key) {
  if (state.ui && state.ui.tips && state.ui.tips[key]) {
    return state.ui.tips[key];
  }
  return key;
}


function applyStepLock(params) {
  var active = null;
  for (var i = 0; i < STEP_KEYS.length; i++) {
    if (num(params[STEP_KEYS[i]], 0) !== 0) {
      active = STEP_KEYS[i];
      break;
    }
  }
  for (var j = 0; j < STEP_KEYS.length; j++) {
    var key = STEP_KEYS[j];
    var input = document.querySelector('[data-param="' + key + '"]');
    if (!input) continue;
    var locked = active !== null && active !== key;
    input.disabled = locked;
    if (locked) {
      /* Сбрасываем заблокированное поле, чтобы не было двух ненулевых шагов. */
      input.value = "0";
      params[key] = 0;
    } else if (num(params[key], 0) < 0) {
      /* Шаг не может быть отрицательным — обнуляем (и в форме, и в превью). */
      input.value = "0";
      params[key] = 0;
    }
    var tipEl = input.parentElement.querySelector(".tip");
    if (tipEl) {
      if (locked) {
        tipEl.setAttribute(
          "data-tip",
          tip("t.locked").replace("{param}", label("p." + active))
        );
        tipEl.classList.add("locked");
      } else {
        tipEl.setAttribute("data-tip", tip("t." + key));
        tipEl.classList.remove("locked");
      }
    }
    /* Тултип и визуал на самом поле (.input-wrap) при блокировке. */
    var wrap = input.parentElement; /* .input-wrap */
    if (locked) {
      wrap.setAttribute("data-tip", tip("t.step_locked"));
      wrap.classList.add("locked");
    } else {
      wrap.removeAttribute("data-tip");
      wrap.classList.remove("locked");
    }
  }
}

/* --- Тосты (вместо статусбара) --- */
var TOAST_ERROR_KEYS = [
  "status.error", "status.save_failed", "status.load_failed", "status.copy_failed",
  "status.step_multiple", "status.step_none", "status.step_negative", "status.pull_fail",
  "status.field_empty"
];

function toastType(key) {
  if (TOAST_ERROR_KEYS.indexOf(key) >= 0) return "error";
  if (key === "status.generated" || key === "status.copied" || key === "status.saved" ||
      key === "status.pull_ok" || key === "status.reset_ok" || key === "status.loaded") {
    return "success";
  }
  return "info";
}

function showToast(key, params) {
  var container = document.getElementById("toast-container");
  if (!container) return;
  var t = text(key);
  if (params) {
    for (var k in params) {
      t = t.replace("{" + k + "}", String(params[k]));
    }
  }
  var toast = document.createElement("div");
  toast.className = "toast " + toastType(key);
  toast.textContent = t;
  container.appendChild(toast);
  /* Удаляем с анимацией через 4 секунды. */
  window.setTimeout(function () {
    toast.classList.add("out");
    window.setTimeout(function () {
      if (toast.parentElement) toast.parentElement.removeChild(toast);
    }, 300);
  }, 4000);
}

/* --- Копирование с fallback --- */
function copyText(value, okKey) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(value).then(function () {
      showToast(okKey);
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
  showToast(ok ? okKey : "status.copy_failed");
}

/* --- Обработка сообщений Python --- */
function onMessage(msg) {
  if (!msg) return;
  switch (msg.type) {
    case "state":
      state.ui = msg.ui;
      state.params = msg.params || {};
      state.recommended = msg.recommended || {};
      state.settings = msg.settings || {};
      state.defaultStartGcode = msg.default_start_gcode || "";
      state.defaultEndGcode = msg.default_end_gcode || "";
      applyTexts();
      applyTheme(state.settings);
      applyFont(state.settings);
      buildForm(state.ui, state.params);
      renderPreview(state.params);
      break;
    case "generated":
      state.gcode = msg.gcode || "";
      showToast("status.generated");
      /* Отложенное действие из меню «Сгенерировать GCODE». */
      if (pendingAction === "copy") {
        pendingAction = null;
        copyText(state.gcode, "status.copied");
      } else if (pendingAction === "save") {
        pendingAction = null;
        promptSave();
      }
      break;
    case "pulled":
      state.params = msg.params || {};
      state.recommended = msg.recommended || {};
      state.defaultStartGcode = msg.default_start_gcode || "";
      state.defaultEndGcode = msg.default_end_gcode || "";
      setFormValues(state.params);
      applyStepLock(state.params);
      updateResetButtons();
      renderPreview(state.params);
      showToast(msg.status || "status.pull_ok");
      break;
    case "reset":
      state.params = msg.params || {};
      state.recommended = msg.recommended || {};
      state.defaultStartGcode = msg.default_start_gcode || "";
      state.defaultEndGcode = msg.default_end_gcode || "";
      setFormValues(state.params);
      applyStepLock(state.params);
      updateResetButtons();
      renderPreview(state.params);
      showToast(msg.status || "status.reset_ok");
      break;
    case "default_gcode_set":
      state.params = msg.params || {};
      setFormValues(state.params);
      updateResetButtons();
      break;
    case "gcode_pulled":
      state.params = msg.params || {};
      setFormValues(state.params);
      updateResetButtons();
      break;
    case "default_gcode_updated":
      /* Обновляем поля, только если они всё ещё равны старым дефолтам. */
      var startEl = document.querySelector('[data-param="startGcode"]');
      var endEl = document.querySelector('[data-param="endGcode"]');
      if (startEl && startEl.value === state.defaultStartGcode) {
        startEl.value = msg.start_gcode || "";
      }
      if (endEl && endEl.value === state.defaultEndGcode) {
        endEl.value = msg.end_gcode || "";
      }
      state.defaultStartGcode = msg.start_gcode || "";
      state.defaultEndGcode = msg.end_gcode || "";
      break;
    case "loaded":
      state.params = msg.params || {};
      setFormValues(state.params);
      applyStepLock(state.params);
      updateResetButtons();
      renderPreview(state.params);
      showToast("status.loaded");
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
      if (msg.key === "status.field_empty" && msg.params && msg.params.field) {
        /* Вторая линия защиты (Python): подсветка поля по ключу из params. */
        markFieldError(msg.params.field);
        showToast(msg.key, { field: fieldLabel(msg.params.field) });
      } else {
        showToast(msg.key, msg.params);
      }
      break;
    case "error":
      showToast("status.error", { error: msg.message });
      break;
  }
}

/* --- Кнопки --- */
var pendingAction = null;

function promptSave() {
  var path = window.prompt(text("status.path_placeholder"), "");
  if (path) {
    post({ type: "save", path: path });
  }
}

function toggleGenerateMenu() {
  var menu = document.getElementById("generate-menu");
  if (!menu) return;
  var hidden = menu.classList.contains("hidden");
  menu.classList.toggle("hidden");
  if (hidden) {
    /* Закрытие по клику вне меню. */
    window.setTimeout(function () {
      document.addEventListener("click", closeGenerateMenu, true);
    }, 0);
  }
}

function closeGenerateMenu(e) {
  var menu = document.getElementById("generate-menu");
  if (!menu || menu.classList.contains("hidden")) return;
  var wrap = document.getElementById("btn-generate");
  if (e && wrap && (e.target === wrap || menu.contains(e.target))) return;
  menu.classList.add("hidden");
  document.removeEventListener("click", closeGenerateMenu, true);
}

function bindToolbar() {
  var map = {
    "btn-help": function () { openHelp(); },
    "btn-reset": function () { post({ type: "reset" }); },
    "btn-generate": function () { toggleGenerateMenu(); },
    "gen-copy": function () {
      if (!requestGenerate()) return;
      pendingAction = "copy";
      post({ type: "generate", params: collectParams() });
    },
    "gen-save": function () {
      if (!requestGenerate()) return;
      pendingAction = "save";
      post({ type: "generate", params: collectParams() });
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
  setSelect("set-firmware", s.firmware || "marlin");
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
    comment_lang: getSelect("set-comment-lang"),
    firmware: getSelect("set-firmware")
  };
}

/* Применение настроек в реальном времени по смене значения. */
function bindSettingsLive() {
  var ids = ["set-theme", "set-font-size", "set-font", "set-language",
             "set-comment-lang", "set-firmware"];
  for (var i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    if (!el) continue;
    el.addEventListener("change", function () {
      /* Текущие значения формы передаём для пересчёта рекомендуемых:
         поля, не изменённые пользователем, обновятся новыми значениями. */
      post({ type: "settings", settings: collectSettings(), params: collectParams() });
    });
    el.addEventListener("input", function () {
      post({ type: "settings", settings: collectSettings(), params: collectParams() });
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
  /* Настройки применяются в реальном времени (bindSettingsLive) — при закрытии
     ничего не постим, иначе поля обнулятся (reapply без params). */
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
  var sections = [
    { title: "help.title", body: "help.what", type: "p" },
    { title: "help.title_steps", body: "help.steps", type: "ol" },
    { title: "help.title_read", body: "help.read", type: "ul" },
    { title: "help.title_pick", body: "help.pick", type: "p" },
    { title: "help.title_pick", body: "help.pick_list", type: "ul" },
    { title: "help.title_tips", body: "help.tips", type: "ul" },
  ];
  var html = "";
  var lastTitle = "";
  for (var i = 0; i < sections.length; i++) {
    var s = sections[i];
    var t = text(s.title);
    if (t !== lastTitle) {
      html += "<h3>" + esc(t) + "</h3>";
      lastTitle = t;
    }
    var body = text(s.body);
    if (s.type === "ol" || s.type === "ul") {
      var items = body.split("\n");
      html += "<" + s.type + ">";
      for (var j = 0; j < items.length; j++) {
        html += "<li>" + esc(items[j]) + "</li>";
      }
      html += "</" + s.type + ">";
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
  bindTips();
  post({ type: "get_state" });
  /* Масштабирование превью при изменении размеров окна (debounce). */
  var resizeTimer = null;
  window.addEventListener("resize", function () {
    if (resizeTimer) window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(fitPreviews, 80);
  });
  fitPreviews();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
