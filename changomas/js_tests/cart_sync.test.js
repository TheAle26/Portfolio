const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
  path.join(__dirname, '..', 'static', 'changomas', 'tracker.js'),
  'utf8',
);

function makeHarness({ authenticated = true, initialItems = [], fetchImpl, storage } = {}) {
  const listeners = {};
  const controls = Array.from({ length: 6 }, () => ({ disabled: false }));
  const status = makeElement();
  const toast = makeElement();
  const csrf = { value: 'csrf-token' };
  const body = {
    dataset: authenticated ? {
      cartApi: '/api/cart/', itemApiTemplate: '/api/cart/items/0000000000000/',
      importApi: '/api/cart/import/',
    } : {},
  };
  const cart = {
    value: initialItems.map((item) => ({ ...item })),
    items() { return this.value.map((item) => ({ ...item })); },
    replace(items, options = {}) {
      this.value = items.map((item) => ({ ...item }));
      if (!options.silent) documentListeners('changocart:change', {});
    },
    repaint() {},
  };
  const documentListeners = (type, event) => {
    for (const listener of listeners[type] || []) listener(event);
  };
  const document = {
    body,
    cookie: '',
    addEventListener(type, callback) {
      if (!listeners[type]) listeners[type] = [];
      listeners[type].push(callback);
    },
    querySelector(selector) {
      if (selector === '[data-quote-url]') return null;
      if (selector === '[data-toast]') return toast;
      if (selector === '[data-cart-sync]') return status;
      if (selector === '[name=csrfmiddlewaretoken]' || selector === 'input[name=csrfmiddlewaretoken]') return csrf;
      return null;
    },
    querySelectorAll() { return controls; },
    createElement() { return makeElement(); },
  };
  const window = {
    ChangoCart: cart,
    setTimeout() { return 1; },
    clearTimeout() {},
    crypto: { randomUUID: () => 'stable-import-id' },
  };
  if (storage !== undefined) {
    Object.defineProperty(window, 'localStorage', {
      configurable: true,
      get: typeof storage === 'function' ? storage : () => storage,
    });
  }
  const context = {
    document, window,
    fetch: fetchImpl || (() => Promise.reject(new Error('Unexpected request'))),
    Promise, Map, Set, Array, JSON, Math, Date, AbortController,
    decodeURIComponent,
  };
  vm.runInNewContext(source, context, { filename: 'tracker.js' });
  return {
    body, cart, controls, listeners, status, toast,
    change(items) {
      cart.value = items.map((item) => ({ ...item }));
      documentListeners('changocart:change', {});
    },
    click(button) {
      documentListeners('click', { target: { closest: (selector) => button.matches(selector) ? button : null } });
    },
  };
}

function makeElement() {
  const attributes = new Set();
  return {
    hidden: true,
    textContent: '',
    children: [],
    classList: { toggle() {} },
    setAttribute(name) { attributes.add(name); },
    appendChild(child) { this.children.push(child); },
    matches(selector) {
      const name = selector.slice(1, -1);
      return attributes.has(name);
    },
  };
}

function response({ status = 200, items = [], version = 1 } = {}) {
  return {
    status,
    ok: status >= 200 && status < 300,
    json: async () => ({ items, version }),
  };
}

function deferred() {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

test('serializes rapid cart edits and sends the latest quantity', async () => {
  const firstWrite = deferred();
  const writes = [];
  const harness = makeHarness({
    initialItems: [],
    fetchImpl: async (url, options = {}) => {
      if (options.method === 'GET') return response({ items: [], version: 1 });
      writes.push(JSON.parse(options.body));
      return writes.length === 1 ? firstWrite.promise : response({ items: [{ ean: 'sku-a', qty: 2 }], version: 3 });
    },
  });
  await tick();

  harness.change([{ ean: 'sku-a', qty: 1 }]);
  await tick();
  harness.change([{ ean: 'sku-a', qty: 2 }]);
  firstWrite.resolve(response({ items: [{ ean: 'sku-a', qty: 1 }], version: 2 }));
  await tick();
  await tick();

  assert.deepEqual(writes.map((write) => write.qty), [1, 2]);
  assert.equal(harness.controls.some((control) => control.disabled), false);
});

test('rebases local edits onto a conflicting remote cart without losing remote lines', async () => {
  const firstWrite = deferred();
  const writes = [];
  const original = [{ ean: 'sku-a', qty: 1 }, { ean: 'sku-b', qty: 1 }];
  const remote = [...original, { ean: 'sku-c', qty: 1 }];
  let server = original;
  let version = 1;
  const harness = makeHarness({
    initialItems: [],
    fetchImpl: async (_url, options = {}) => {
      if (options.method === 'GET') return response({ items: server, version });
      const payload = JSON.parse(options.body);
      writes.push({ ...payload, ean: decodeURIComponent(_url.split('/').filter(Boolean).at(-1)) });
      if (writes.length === 1) return firstWrite.promise;
      const next = new Map(server.map((item) => [item.ean, item.qty]));
      if (payload.qty === 0) next.delete(payload.ean);
      else next.set(payload.ean, payload.qty);
      server = Array.from(next, ([ean, qty]) => ({ ean, qty }));
      version += 1;
      return response({ items: server, version });
    },
  });
  await tick();

  harness.change([{ ean: 'sku-a', qty: 2 }, { ean: 'sku-b', qty: 1 }]);
  await tick();
  harness.change([
    { ean: 'sku-a', qty: 2 }, { ean: 'sku-b', qty: 1 }, { ean: 'sku-d', qty: 1 },
  ]);
  firstWrite.resolve(response({ status: 409, items: remote, version: 2 }));
  await tick();
  await tick();
  await tick();

  assert.deepEqual(new Map(harness.cart.items().map((item) => [item.ean, item.qty])), new Map([
    ['sku-a', 2], ['sku-b', 1], ['sku-c', 1], ['sku-d', 1],
  ]));
  assert.ok(writes.some((write) => write.ean === 'sku-d' && write.qty === 1));
  assert.ok(writes.some((write) => write.ean === 'sku-a' && write.qty === 2));
});

test('keeps account cart controls disabled after initial load failure and retries loading', async () => {
  let getCount = 0;
  const harness = makeHarness({
    fetchImpl: async (_url, options = {}) => {
      if (options.method !== 'GET') throw new Error('Unexpected write');
      getCount += 1;
      return getCount === 1 ? response({ status: 503 }) : response({ items: [], version: 4 });
    },
  });
  await tick();
  assert.ok(harness.controls.every((control) => control.disabled));
  const retryButton = harness.status.children.find((child) => child.matches('[data-cart-refresh]'));
  assert.ok(retryButton);

  harness.click(retryButton);
  await tick();

  assert.equal(getCount, 2);
  assert.ok(harness.controls.every((control) => !control.disabled));
});

test('handles blocked local storage while importing a guest cart', () => {
  const harness = makeHarness({
    authenticated: false,
    fetchImpl: async () => { throw new Error('Should not request without reading local storage'); },
    storage: () => { throw new Error('storage access denied'); },
  });
  const importButton = makeElement();
  importButton.setAttribute('data-import-guest', '');

  assert.doesNotThrow(() => harness.click(importButton));
  assert.match(harness.toast.textContent, /No se pudo leer el carrito guardado/);
});
