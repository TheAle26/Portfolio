(function () {
  'use strict';
  var body = document.body;
  var cartPage = document.querySelector('[data-quote-url]');
  var toast = document.querySelector('[data-toast]');
  var status = document.querySelector('[data-cart-sync]');
  var auth = Boolean(body.dataset.cartApi && body.dataset.itemApiTemplate);
  var csrf = document.querySelector('[name=csrfmiddlewaretoken]');
  var version = null;
  var serverItems = [];
  var cartReady = !auth;
  var busy = false;
  var needsSync = false;
  var quoteTicket = 0;
  var quoteAbort = null;
  var applyingServer = false;
  var debounce;

  function message(text, error) {
    if (toast) { toast.textContent = text; toast.hidden = false; toast.classList.toggle('toast--error', Boolean(error)); }
    if (status && error) {
      status.textContent = text + ' ';
      var retry = document.createElement('button');
      retry.type = 'button'; retry.className = 'text-link'; retry.setAttribute('data-cart-retry', ''); retry.textContent = 'Reintentar';
      status.appendChild(retry); status.hidden = false;
    }
    if (toast) window.setTimeout(function () { toast.hidden = true; }, 4200);
  }
  function setCartReady(ready) {
    cartReady = ready;
    var controls = document.querySelectorAll('[data-cart-add], [data-cart-inc], [data-cart-dec], [data-cart-remove], [data-cart-clear], [data-import-guest]');
    for (var i = 0; i < controls.length; i++) controls[i].disabled = !ready;
    if (ready && window.ChangoCart) window.ChangoCart.repaint();
  }
  function loadFailure(text) {
    var target = status || toast;
    if (!target) return;
    target.textContent = text + ' ';
    var button = document.createElement('button');
    button.type = 'button'; button.className = 'text-link'; button.setAttribute('data-cart-refresh', ''); button.textContent = 'Reintentar carga';
    target.appendChild(button); target.hidden = false;
  }
  function items() { return window.ChangoCart ? window.ChangoCart.items() : []; }
  function token() {
    var found = csrf;
    if (!found) found = document.querySelector('input[name=csrfmiddlewaretoken]');
    if (found) return found.value;
    var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }
  function request(url, method, payload, signal) {
    var headers = { 'Content-Type': 'application/json', 'X-CSRFToken': token() };
    return fetch(url, { method: method, credentials: 'same-origin', headers: headers, body: payload === undefined ? undefined : JSON.stringify(payload), signal: signal });
  }
  function applyServer(data) {
    if (data && Array.isArray(data.items) && window.ChangoCart && window.ChangoCart.replace) {
      version = data.version;
      serverItems = data.items.slice();
      applyingServer = true;
      window.ChangoCart.replace(data.items, { silent: true });
      applyingServer = false;
      if (status) status.hidden = true;
    }
  }
  function refresh() {
    if (!auth) return Promise.resolve();
    return request(body.dataset.cartApi, 'GET').then(function (response) {
      if (!response.ok) throw new Error('No pudimos cargar tu carrito de cuenta.');
      return response.json();
    }).then(applyServer);
  }
  function sync() {
    if (!auth || !cartReady) return Promise.resolve();
    needsSync = true;
    if (busy) return Promise.resolve();
    busy = true;
    function run() {
      if (!needsSync) { busy = false; return Promise.resolve(); }
      needsSync = false;
      var target = items();
      var before = serverItems.slice();
      var desired = new Map(target.map(function (item) { return [item.ean, item.qty]; }));
      var current = new Map(before.map(function (item) { return [item.ean, item.qty]; }));
      var changes = [];
      target.forEach(function (item) { if (current.get(item.ean) !== item.qty) changes.push({ ean: item.ean, qty: item.qty }); });
      before.forEach(function (item) { if (!desired.has(item.ean)) changes.push({ ean: item.ean, qty: 0 }); });
      function send(index) {
        if (index >= changes.length) {
          if (JSON.stringify(items()) !== JSON.stringify(target)) needsSync = true;
          return Promise.resolve();
        }
        var change = changes[index];
        var url = body.dataset.itemApiTemplate.replace('0000000000000', encodeURIComponent(change.ean));
        var method = change.qty === 0 ? 'DELETE' : 'PUT';
        return request(url, method, { qty: change.qty, version: version }).then(function (response) {
          if (response.status === 409) return response.json().then(function (data) {
            var latest = items();
            var latestByEan = new Map(latest.map(function (item) { return [item.ean, item.qty]; }));
            var beforeByEan = new Map(before.map(function (item) { return [item.ean, item.qty]; }));
            applyServer(data);
            var rebased = new Map(serverItems.map(function (item) { return [item.ean, item.qty]; }));
            var keys = new Set(Array.from(beforeByEan.keys()).concat(Array.from(latestByEan.keys())));
            keys.forEach(function (ean) {
              if (beforeByEan.get(ean) === latestByEan.get(ean)) return;
              if (latestByEan.has(ean)) rebased.set(ean, latestByEan.get(ean));
              else rebased.delete(ean);
            });
            message('Tu carrito cambió en otra pestaña. Actualizamos la versión y volvemos a guardar tus cambios.', true);
            window.ChangoCart.replace(Array.from(rebased, function (entry) { return { ean: entry[0], qty: entry[1] }; }));
          });
          if (!response.ok) throw new Error('No pudimos guardar el carrito. Tu cambio sigue visible; probá de nuevo en unos segundos.');
          return response.json().then(function (data) { version = data.version; serverItems = data.items.slice(); return send(index + 1); });
        });
      }
      return send(0).then(function () { if (status) status.hidden = true; return run(); }).catch(function (error) { busy = false; needsSync = true; message(error.message || 'No pudimos sincronizar el carrito.', true); });
    }
    return run();
  }
  function updateQuote() {
    if (!cartPage) return;
    var target = items();
    var ticket = ++quoteTicket;
    if (quoteAbort) quoteAbort.abort();
    quoteAbort = new AbortController();
    request(cartPage.dataset.quoteUrl, 'POST', { items: target }, quoteAbort.signal).then(function (response) {
      if (!response.ok) throw new Error('No pudimos actualizar la cotización.');
      return response.text();
    }).then(function (html) {
      if (ticket !== quoteTicket) return;
      var slot = document.querySelector('[data-quote-content]');
      if (slot) { slot.innerHTML = html; if (window.ChangoCart) window.ChangoCart.repaint(); }
    }).catch(function (error) { if (error.name !== 'AbortError') message('No pudimos actualizar la cotización. Revisá tu conexión.', true); });
  }
  document.addEventListener('changocart:change', function () {
    if (auth && !applyingServer) sync();
    window.clearTimeout(debounce);
    debounce = window.setTimeout(updateQuote, 120);
  });
  document.addEventListener('click', function (event) {
    var importButton = event.target.closest && event.target.closest('[data-import-guest]');
    if (!importButton) return;
    var guest = [];
    var storage;
    try { storage = window.localStorage; guest = JSON.parse(storage.getItem('changomas:cart:v1') || '[]'); }
    catch (error) { message('No se pudo leer el carrito guardado en este dispositivo.', true); return; }
    if (!Array.isArray(guest) || guest.length === 0) { message('No hay un carrito local para importar.', false); return; }
    var importId;
    var fingerprint = JSON.stringify(guest);
    try {
      importId = storage.getItem('changomas:cart:import-id');
      if (!importId || storage.getItem('changomas:cart:import-fingerprint') !== fingerprint) {
        importId = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : String(Date.now()) + '-' + Math.random().toString(16).slice(2);
        storage.setItem('changomas:cart:import-id', importId);
        storage.setItem('changomas:cart:import-fingerprint', fingerprint);
      }
    } catch (error) { message('No se pudo preparar la importación del carrito.', true); return; }
    request(body.dataset.importApi, 'POST', { items: guest, import_id: importId }).then(function (response) {
      if (!response.ok) throw new Error('No se pudo importar. Tu carrito de este dispositivo sigue guardado.');
      return response.json();
    }).then(function (data) { applyServer(data); message('Carrito importado a tu cuenta.', false); updateQuote(); }).catch(function (error) { message(error.message, true); });
  });
  document.addEventListener('click', function (event) {
    if (event.target.closest && event.target.closest('[data-cart-refresh]')) {
      if (status) status.hidden = true;
      if (toast) toast.hidden = true;
      refresh().then(function () { setCartReady(true); updateQuote(); }).catch(function (error) { loadFailure(error.message); });
      return;
    }
    if (event.target.closest && event.target.closest('[data-cart-retry]')) { needsSync = true; sync(); }
  });
  if (auth) {
    setCartReady(false);
    refresh().then(function () { setCartReady(true); updateQuote(); }).catch(function (error) { loadFailure(error.message); });
  }
  else updateQuote();
}());
