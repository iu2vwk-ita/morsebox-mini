'use strict';
/* IU2VWK Morse Simulator — client UI: websocket live, sidetone WebAudio, touch paddle. */
const $ = id => document.getElementById(id);
const els = {
  dot: $('connDot'), connTxt: $('connTxt'), host: $('hostLine'),
  decoded: $('decoded'), clear: $('clearTxt'), wpmEcho: $('wpmEcho'),
  lamp: $('lamp'), leverL: $('leverL'), leverR: $('leverR'),
  labL: $('labL'), labR: $('labR'),
  wpmVal: $('wpmVal'), wpmSlider: $('wpmSlider'),
  revBtn: $('revBtn'), revState: $('revState'),
  seg: [...document.querySelectorAll('.seg button')],
  tone: $('toneSlider'), toneVal: $('toneVal'),
  vol: $('volSlider'), volVal: $('volVal'),
  padL: $('padL'), padR: $('padR'), padLT: $('padLT'), padRT: $('padRT'),
  skey: $('straightKey'), touch: $('touchPanel'),
  gpio: $('gpioLine'),
};
let S = { wpm: 20, reverse: false, mode: 'iambic-b', tone: 650, buzzer: false, volume: 70 };
let ws = null, retry = 0;
let local = { l: false, r: false, k: false };   // paddle touch locali
let keyOn = false;

/* While the user is moving a slider, ignore the device echo for that control:
   otherwise the echoed value (slightly behind your finger) snaps the slider back. */
const editUntil = { wpm: 0, tone: 0, volume: 0 };
const EDIT_GRACE = 1200;   // ms
function touchEdit(name) { editUntil[name] = Date.now() + EDIT_GRACE; }
function editing(name) { return Date.now() < editUntil[name]; }

/* ---------------- audio ---------------- */
let AC = null, osc = null, gain = null;
function audio() {
  if (!AC) {
    AC = new (window.AudioContext || window.webkitAudioContext)();
    osc = AC.createOscillator(); osc.type = 'sine';
    gain = AC.createGain(); gain.gain.value = 0;
    osc.connect(gain).connect(AC.destination);
    osc.frequency.value = S.tone;
    osc.start();
  }
  if (AC.state === 'suspended') AC.resume();
  return AC;
}
function sidetone(on) {
  if (!AC) return;
  const t = AC.currentTime;
  gain.gain.cancelScheduledValues(t);
  gain.gain.setTargetAtTime(on ? (S.volume / 100) * 0.5 : 0, t, on ? 0.004 : 0.006);
}
document.addEventListener('pointerdown', () => audio(), { once: true });

/* ---------------- websocket ---------------- */
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(proto + '://' + location.host + '/ws');
  ws.onopen = () => {
    retry = 0;
    els.dot.className = 'dot on';
    els.connTxt.textContent = 'connected';
  };
  ws.onclose = () => {
    els.dot.className = 'dot off';
    els.connTxt.textContent = 'reconnecting…';
    setTimeout(connect, Math.min(5000, 400 * ++retry + 400));
  };
  ws.onmessage = ev => {
    let m;
    try { m = JSON.parse(ev.data); } catch (e) { return; }
    if (m.t === 'hello') {
      applySettings(m.settings);
      els.decoded.textContent = m.text || '';
      scrollRx();
      els.gpio.textContent = m.gpio && m.gpio !== 'mock' ? 'GPIO: ' + m.gpio : 'demo, no GPIO';
    } else if (m.t === 'settings') {
      applySettings(m.settings);
    } else if (m.t === 'key') {
      setKey(m.on);
      setPads(!!m.dit, !!m.dah);
    } else if (m.t === 'pad') {
      setPads(!!m.dit, !!m.dah);
    } else if (m.t === 'txt') {
      els.decoded.textContent += m.ch;
      scrollRx();
    }
  };
}
function send(o) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(o)); }
function pushPads() { send({ t: 'paddle', dit: local.l, dah: local.r, key: local.k }); }
setInterval(() => { if (local.l || local.r || local.k) pushPads(); }, 1000); // heartbeat anti-stallo

/* ---------------- render ---------------- */
function setKey(on) {
  keyOn = on;
  els.lamp.classList.toggle('lit', on);
  sidetone(on);
}
function setPads(dit, dah) {
  // dit = physical LEFT lever (or RIGHT if reverse): levers follow the real keys
  els.leverL.classList.toggle('hit', dit);
  els.leverR.classList.toggle('hit', dah);
}
function scrollRx() { els.decoded.scrollTop = els.decoded.scrollHeight; }

function applySettings(s) {
  s = Object.assign({}, s);
  if (editing('wpm')) delete s.wpm;
  if (editing('tone')) delete s.tone;
  if (editing('volume')) delete s.volume;
  S = Object.assign(S, s);
  els.wpmVal.textContent = S.wpm;
  els.wpmEcho.textContent = '· ' + S.wpm + ' WPM';
  if (document.activeElement !== els.wpmSlider) els.wpmSlider.value = S.wpm;
  els.revBtn.setAttribute('aria-pressed', S.reverse ? 'true' : 'false');
  els.revState.textContent = S.reverse ? 'reversed' : 'normal';
  const ditLeft = !S.reverse;
  els.padLT.textContent = ditLeft ? 'DIT' : 'DAH';
  els.padRT.textContent = ditLeft ? 'DAH' : 'DIT';
  els.labL.textContent = (ditLeft ? 'DIT' : 'DAH') + ' · L';
  els.labR.textContent = (ditLeft ? 'DAH' : 'DIT') + ' · R';
  els.seg.forEach(b => b.classList.toggle('on', b.dataset.mode === S.mode));
  els.touch.classList.toggle('dim', S.mode === 'straight');
  if (document.activeElement !== els.tone) els.tone.value = S.tone;
  els.toneVal.textContent = S.tone + ' Hz';
  if (document.activeElement !== els.vol) els.vol.value = S.volume;
  els.volVal.textContent = S.volume + '%';
  if (AC && osc) osc.frequency.value = S.tone;
}
function saveSettings() {
  send({ t: 'settings', wpm: S.wpm, reverse: S.reverse, mode: S.mode, tone: S.tone, volume: S.volume });
}

/* ---------------- controls ---------------- */
function setWpm(w) {
  S.wpm = Math.max(5, Math.min(60, Math.round(w)));
  els.wpmVal.textContent = S.wpm;
  els.wpmSlider.value = S.wpm;
  els.wpmEcho.textContent = '· ' + S.wpm + ' WPM';
  saveSettings();
}
$('wpmDown').onclick = () => { touchEdit('wpm'); setWpm(S.wpm - 1); };
$('wpmUp').onclick = () => { touchEdit('wpm'); setWpm(S.wpm + 1); };
els.wpmSlider.oninput = () => { touchEdit('wpm'); setWpm(+els.wpmSlider.value); };
els.revBtn.onclick = () => {
  S.reverse = !S.reverse;
  applySettings(S);
  saveSettings();
};
els.seg.forEach(b => b.onclick = () => { S.mode = b.dataset.mode; applySettings(S); saveSettings(); });
let toneTimer = null;
els.tone.oninput = () => {
  touchEdit('tone');
  S.tone = +els.tone.value;
  els.toneVal.textContent = S.tone + ' Hz';
  if (AC && osc) osc.frequency.value = S.tone;
  clearTimeout(toneTimer);
  toneTimer = setTimeout(saveSettings, 120);   // send while dragging, not only on release
};
els.tone.onchange = saveSettings;
let volTimer = null;
els.vol.oninput = () => {
  touchEdit('volume');
  S.volume = +els.vol.value;
  els.volVal.textContent = els.vol.value + '%';
  clearTimeout(volTimer);
  volTimer = setTimeout(saveSettings, 150);
};
els.clear.onclick = () => { els.decoded.textContent = ''; };

/* ---------------- touch paddles ---------------- */
function bindHold(el, set) {
  const on = e => { e.preventDefault(); audio(); set(true); };
  const off = e => { e.preventDefault(); set(false); };
  el.addEventListener('pointerdown', on);
  el.addEventListener('pointerup', off);
  el.addEventListener('pointercancel', off);
  el.addEventListener('pointerleave', off);
  el.addEventListener('contextmenu', e => e.preventDefault());
}
function refreshPadButtons() {
  els.padL.classList.toggle('hit', local.l);
  els.padR.classList.toggle('hit', local.r);
  els.skey.classList.toggle('hit', local.k);
}
bindHold(els.padL, v => { local.l = v; refreshPadButtons(); pushPads(); });
bindHold(els.padR, v => { local.r = v; refreshPadButtons(); pushPads(); });
bindHold(els.skey, v => { local.k = v; refreshPadButtons(); pushPads(); });

/* keyboard: Z = left lever, X = right lever, Space = straight key */
const keymap = { KeyZ: 'l', KeyX: 'r', Space: 'k' };
document.addEventListener('keydown', e => {
  const k = keymap[e.code];
  if (!k || e.repeat) return;
  e.preventDefault(); audio();
  local[k] = true; refreshPadButtons(); pushPads();
});
document.addEventListener('keyup', e => {
  const k = keymap[e.code];
  if (!k) return;
  e.preventDefault();
  local[k] = false; refreshPadButtons(); pushPads();
});

/* ---------------- go ---------------- */
els.host.textContent = location.host + ' · QR at the booth leads here';
connect();
