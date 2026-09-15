// Drive one TEST submission of Typeform yUQCu040 in a throwaway headless Chrome.
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const OUT = process.argv[2];
const URL = 'https://o4ltnhc1g3t.typeform.com/to/yUQCu040#invite_id=TEST0915';
const PORT = 9333;
const profile = mkdtempSync(join(tmpdir(), 'tf-headless-'));
const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
  '--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  '--window-size=1400,900', '--no-first-run', '--no-default-browser-check', 'about:blank',
], { stdio: 'ignore' });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let ws, seq = 0;
const pending = new Map();
function send(method, params = {}) {
  const id = ++seq;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((res, rej) => pending.set(id, { res, rej }));
}
async function title() {
  const r = await send('Runtime.evaluate', { expression: 'document.title', returnByValue: true });
  return r.result.value;
}
async function key(k, code, vk, text) {
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: k, code, windowsVirtualKeyCode: vk, text });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: k, code, windowsVirtualKeyCode: vk });
}
const enter = () => key('Enter', 'Enter', 13, '\r');
const letter = (c) => key(c, 'Key' + c.toUpperCase(), c.toUpperCase().charCodeAt(0), c);
const typeText = (t) => send('Input.insertText', { text: t });

async function clickAt(x, y) {
  for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased'])
    await send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: 1 });
}
// Click the innermost visible element in the viewport whose text matches.
async function clickText(src) {
  const r = await send('Runtime.evaluate', { returnByValue: true, expression: `
    (() => { const re = new RegExp(${JSON.stringify(src)}, 'i');
      const vis = (el) => { const b = el.getBoundingClientRect(); return b.width > 0 && b.height > 0 && b.top >= 0 && b.bottom <= innerHeight && getComputedStyle(el).visibility !== 'hidden'; };
      const c = [...document.querySelectorAll('button,[role=radio],[role=button],label,div,span')].filter(el => re.test((el.innerText||'').trim()) && vis(el));
      c.sort((a,b) => a.innerText.length - b.innerText.length || b.querySelectorAll('*').length - a.querySelectorAll('*').length);
      const el = c[0]; if (!el) return null; const b = el.getBoundingClientRect();
      return { x: b.left + b.width/2, y: b.top + b.height/2, t: el.innerText.trim().slice(0,40) }; })()` });
  const v = r.result.value;
  if (!v) throw new Error('nothing visible matching ' + src);
  await clickAt(v.x, v.y);
  return v.t;
}
// Click the visible text box, type, press Enter.
async function fill(text) {
  const r = await send('Runtime.evaluate', { returnByValue: true, expression: `
    (() => { const a = document.activeElement;
      if (a && /^(INPUT|TEXTAREA)$/.test(a.tagName)) return { focused: true, n: a.name || a.type || a.tagName, v: a.value };
      // Otherwise the text box nearest the middle of the screen (the current question).
      const mid = innerHeight / 2;
      const c = [...document.querySelectorAll('input:not([type=hidden]),textarea')].filter(e => e.getBoundingClientRect().width > 0)
        .sort((x, y) => Math.abs(x.getBoundingClientRect().top - mid) - Math.abs(y.getBoundingClientRect().top - mid));
      const el = c[0]; if (!el) return null; const b = el.getBoundingClientRect();
      return { x: b.left + 20, y: b.top + b.height/2, n: el.name || el.type, v: el.value }; })()` });
  const v = r.result.value;
  if (!v) throw new Error('no visible text box');
  console.log('   box:', v.focused ? 'focused' : 'clicked', v.n, v.v ? `(already has "${v.v.slice(0,20)}")` : '');
  if (!v.focused) await clickAt(v.x, v.y);
  if (text) await typeText(text);
  await enter();
}
async function shot(name) {
  const r = await send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(OUT, name), Buffer.from(r.data, 'base64'));
}
async function step(label, fn, wait = 2500) {
  await fn();
  await sleep(wait);
  console.log(`${label.padEnd(22)} -> ${await title()}`);
}

try {
  let target;
  for (let i = 0; i < 30 && !target; i++) {
    await sleep(500);
    try {
      const list = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json();
      target = list.find((t) => t.type === 'page');
    } catch {}
  }
  if (!target) throw new Error('headless Chrome never came up');
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r));
  ws.addEventListener('message', (e) => {
    const m = JSON.parse(e.data);
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id); pending.delete(m.id);
      m.error ? p.rej(new Error(JSON.stringify(m.error))) : p.res(m.result);
    }
  });
  await send('Page.enable');
  await send('Page.navigate', { url: URL });
  await sleep(7000);
  console.log('loaded                 ->', await title());
  await shot('00_welcome.png');

  await send('Emulation.setFocusEmulationEnabled', { enabled: true });
  await send('Page.bringToFront');
  await step('start', () => clickText('^Start$'));
  await step('house', () => clickText('^A house or townhouse'));
  await step('10 doors', () => clickText('^10 -- both sides'));
  await step('why', () => fill('TEST SUBMISSION by Claude to check the invite_id field. Please ignore.'));
  await step('name', () => fill('TEST Claude'));
  await step('email', () => fill('karthik@hub3.us'));
  await step('phone (skip)', () => fill(''));
  await step('NC yes', () => clickText("^Yes, I.m in North Carolina"));
  await step('street', () => fill('1 Test Street'));
  await step('unit (skip)', () => fill(''));
  await step('city', () => fill('Enfield'));
  await step('zip', () => fill('27823'), 3000);
  await shot('01_after_zip.png');
  // If a Submit button is showing, click it.
  const clicked = await send('Runtime.evaluate', { returnByValue: true, expression: `
    (() => { const b=[...document.querySelectorAll('button')].find(x=>/submit/i.test(x.innerText)); if(b){b.click(); return 'clicked Submit';} return 'no Submit button'; })()` });
  console.log('submit                 ->', clicked.result.value);
  await sleep(5000);
  console.log('final                  ->', await title());
  const body = await send('Runtime.evaluate', { returnByValue: true, expression: 'document.body.innerText.slice(0,400)' });
  console.log('final text:', JSON.stringify(body.result.value));
  await shot('02_final.png');
} catch (e) {
  console.error('ERROR', e.message);
} finally {
  chrome.kill('SIGKILL');
  process.exit(0);
}
