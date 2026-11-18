/* Offline PESSTOWISE export: saved science bytes, FITS metadata, USTAR and gzip. */
(() => {
  'use strict';
  const enc = new TextEncoder(), dec = new TextDecoder('ascii');
  const concat = arrays => {
    const result = new Uint8Array(arrays.reduce((n, a) => n + a.length, 0));
    let offset = 0;
    for (const a of arrays) { result.set(a, offset); offset += a.length; }
    return result;
  };
  const decode64 = value => Uint8Array.from(atob(value), c => c.charCodeAt(0));
  function clean(value, label, required = true) {
    const text = String(value || '').trim();
    if ((required && (!text || ['UNKNOWN', 'TODO', 'NULL'].includes(text.toUpperCase()))) || /[\x00-\x1f\x7f]/.test(text))
      throw new Error('Enter ' + label + ' without tabs or line breaks.');
    return text;
  }
  function fitsString(key, value) {
    if (/[^\x20-\x7e]/.test(value)) throw new Error('FITS header names and group names must use ASCII characters.');
    let prefix = key.length <= 8 ? key.padEnd(8) + '= ' : 'HIERARCH ' + key + ' = ';
    const atoms = Array.from(value, c => c === "'" ? "''" : c), cards = [];
    do {
      let part = '';
      const capacity = 80 - prefix.length - 4;
      while (atoms.length && part.length + atoms[0].length <= capacity) part += atoms.shift();
      cards.push((prefix + "'" + part + (atoms.length ? '&' : '') + "'").padEnd(80));
      prefix = 'CONTINUE  ';
    } while (atoms.length);
    return cards;
  }
  function onesSum(bytes) {
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    let sum = 0;
    for (let i = 0; i < bytes.length; i += 4) {
      sum += view.getUint32(i, false);
      sum = (sum % 4294967296) + Math.floor(sum / 4294967296);
    }
    while (sum > 4294967295) sum = (sum % 4294967296) + Math.floor(sum / 4294967296);
    return sum >>> 0;
  }
  function encodeChecksum(value) {
    // FITS checksum convention, also used by Astropy _char_encode/_encode_byte.
    const out = Array(16).fill(0), excluded = n => (n >= 58 && n <= 64) || (n >= 91 && n <= 96);
    for (let i = 0; i < 4; i++) {
      const byte = (value >>> ((3 - i) * 8)) & 255, q = Math.floor(byte / 4) + 48;
      const chars = [q + byte % 4, q, q, q];
      for (let j = 0; j < 4; j += 2) {
        while (excluded(chars[j]) || excluded(chars[j + 1])) { chars[j]++; chars[j + 1]--; }
      }
      for (let j = 0; j < 4; j++) out[4 * j + i] = chars[j];
    }
    return Array.from({length: 16}, (_, i) => String.fromCharCode(out[(i + 15) % 16])).join('');
  }
  function updateFits(bytes, metadata) {
    if (bytes.length % 2880 || onesSum(bytes) !== 4294967295) throw new Error('Saved FITS checksum failed. Rebuild this report.');
    const remove = new Set([...Object.keys(metadata), 'CHECKSUM', 'LONGSTRN',
      'WISEREP ASSOCIATED GROUPS', 'WISEREP PROPRIETARY UNTIL']);
    const cards = []; let end = -1, dropping = false;
    for (let offset = 0; offset < bytes.length; offset += 80) {
      const card = dec.decode(bytes.subarray(offset, offset + 80));
      const key = card.startsWith('HIERARCH ') ? card.slice(9).split('=')[0].trim() : card.slice(0, 8).trim();
      if (key === 'END') { end = offset + 80; break; }
      if (key === 'CONTINUE') { if (!dropping) cards.push(card); continue; }
      dropping = remove.has(key);
      if (!dropping) cards.push(card);
    }
    if (end < 0) throw new Error('Missing FITS header terminator.');
    for (const [key, value] of Object.entries(metadata)) cards.push(...fitsString(key, value));
    cards.push(...fitsString('LONGSTRN', 'OGIP 1.0'));
    const checksumIndex = cards.length;
    cards.push("CHECKSUM= '0000000000000000'".padEnd(80), 'END'.padEnd(80));
    const header = enc.encode(cards.join('').padEnd(Math.ceil(cards.length * 80 / 2880) * 2880));
    const data = bytes.subarray(Math.ceil(end / 2880) * 2880);
    const result = concat([header, data]);
    const checksum = encodeChecksum((~onesSum(result)) >>> 0);
    result.set(enc.encode(checksum), checksumIndex * 80 + 11);
    if (onesSum(result) !== 4294967295) throw new Error('Could not update FITS checksum.');
    return result;
  }
  function tar(files, timestamp) {
    const parts = [], seen = new Set();
    for (const file of files) {
      if (!/^[A-Za-z0-9][A-Za-z0-9_.+-]*$/.test(file.name) || file.name.length > 100 || seen.has(file.name))
        throw new Error('Invalid or duplicate archive filename: ' + file.name);
      seen.add(file.name);
      const header = new Uint8Array(512);
      const put = (offset, text) => header.set(enc.encode(text), offset);
      const oct = (offset, value, width) => {
        const text = Math.trunc(value).toString(8);
        if (text.length >= width) throw new Error('Archive member exceeds USTAR limit.');
        put(offset, text.padStart(width - 1, '0') + '\0');
      };
      put(0, file.name); oct(100, 420, 8); oct(108, 0, 8); oct(116, 0, 8);
      oct(124, file.bytes.length, 12); oct(136, timestamp, 12);
      put(148, '        '); put(156, '0'); put(257, 'ustar\0'); put(263, '00');
      const checksum = header.reduce((sum, byte) => sum + byte, 0);
      put(148, checksum.toString(8).padStart(6, '0') + '\0 ');
      parts.push(header, file.bytes, new Uint8Array((512 - file.bytes.length % 512) % 512));
    }
    return concat([...parts, new Uint8Array(1024)]);
  }
  function gzip(bytes) {
    // Valid gzip with stored DEFLATE blocks: works offline without a CDN/library
    // or browser-specific compression API. These small spectral bundles need no
    // scientific resampling or lossy compression.
    const parts = [Uint8Array.from([31,139,8,0,0,0,0,0,0,255])];
    for (let offset = 0; offset < bytes.length; offset += 65535) {
      const size = Math.min(65535, bytes.length - offset), inv = (~size) & 65535;
      parts.push(Uint8Array.from([offset + size === bytes.length ? 1 : 0, size & 255, size >>> 8, inv & 255, inv >>> 8]), bytes.subarray(offset, offset + size));
    }
    let crc = 4294967295;
    for (const byte of bytes) {
      crc ^= byte;
      for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
    }
    const trailer = new Uint8Array(8), view = new DataView(trailer.buffer);
    view.setUint32(0, (crc ^ 4294967295) >>> 0, true); view.setUint32(4, bytes.length >>> 0, true);
    return concat([...parts, trailer]);
  }
  function build(config, choices, attribution, now = new Date()) {
    const chosen = config.groups.filter(g => choices[g.id]);
    if (!chosen.length) throw new Error('Choose Public or Private for at least one target.');
    if (!attribution.reviewed) throw new Error('Confirm that you reviewed the selected spectra and access settings.');
    const observers = clean(attribution.observers, 'observer names'), reducers = clean(attribution.reducers, 'reducer names');
    const group = clean(attribution.group, 'the source group'), date = clean(attribution.date, 'the reduction date');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date) || !Number.isFinite(Date.parse(date)) || new Date(date).toISOString().slice(0,10) !== date)
      throw new Error('Enter a valid UTC reduction date.');
    const privateSelected = chosen.some(g => choices[g.id] === 'private');
    let privateGroups = '', embargo = '';
    if (privateSelected) {
      privateGroups = clean(attribution.privateGroups, 'the private associated groups');
      if (privateGroups.split(',').some(x => !x.trim())) throw new Error('Enter comma-separated private group names.');
      embargo = clean(attribution.embargo, 'the private embargo end time');
      if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$/.test(embargo) || !(Date.parse(embargo + 'Z') > now.getTime())
          || new Date(embargo + 'Z').toISOString().slice(0, embargo.length) !== embargo)
        throw new Error('The private embargo must be a future UTC date/time.');
    }
    const stamp = now.toISOString().slice(0,16).replaceAll('-', '').replace('T', '_').replace(':', '_');
    const batches = {}, filenames = new Set();
    for (const target of chosen) {
      const access = choices[target.id];
      if (!['public', 'private'].includes(access) || !target.products.length) throw new Error('Target has no eligible products or invalid access.');
      const spectrumType = attribution.types?.[target.id] || 'Object';
      if (!['Object', 'Host'].includes(spectrumType)) throw new Error('Choose Object or Host for the spectrum type.');
      for (const product of target.products) {
        if (filenames.has(product.filename)) throw new Error('A spectrum was selected more than once.');
        filenames.add(product.filename);
        const batch = batches[access] ||= {files: [], rows: [], quality: product.quality};
        if (batch.quality !== product.quality) throw new Error('Export one quality per access class at a time.');
        const metadata = {OBSERVER: observers, REDUCER: reducers, 'DATE-RED': date, TELESCOP: 'ESO-NTT',
          'PESSTO ACCESS': access, 'EFOSPEC NIGHT': config.night, 'WISEREP SOURCE GROUP': group,
          'WISEREP SPECTRUM TYPE': spectrumType, 'WISEREP QUALITY': product.quality};
        if (access === 'private') Object.assign(metadata, {'WISEREP ASSOCIATED GROUPS': privateGroups, 'WISEREP PROPRIETARY UNTIL': embargo});
        batch.files.push({name: product.filename, bytes: updateFits(decode64(product.fits_base64), metadata)},
          {name: product.ascii_name, bytes: enc.encode(product.ascii)});
        const row = product.row.slice(); row[6] = observers; row[9] = reducers; row[10] = date; row[12] = spectrumType;
        batch.rows.push(row.join('\t'));
      }
    }
    return Object.entries(batches).map(([access, batch]) => {
      const base = 'pessto_' + stamp + '_' + batch.quality + '_upload';
      batch.files.push({name: base + '.txt', bytes: enc.encode(config.header + '\n' + config.defaults + '\n' + batch.rows.join('\n') + '\n')});
      return {name: base + '_' + access + '.tgz', access, count: batch.rows.length,
        bytes: gzip(tar(batch.files, now.getTime() / 1000))};
    });
  }
  globalThis.EFOSpecDelivery = {build, updateFits, onesSum};
  if (typeof document === 'undefined') return;
  const root = document.getElementById('delivery-export'); if (!root) return;
  const config = JSON.parse(document.getElementById('delivery-payload').textContent);
  const status = document.getElementById('delivery-status'), downloads = document.getElementById('delivery-downloads');
  const controls = [...root.querySelectorAll('[data-delivery-target]')], urls = [];
  function invalidate() {
    urls.splice(0).forEach(url => URL.revokeObjectURL(url)); downloads.replaceChildren(); status.className = '';
    const selected = controls.filter(el => el.value);
    status.textContent = selected.length ? selected.length + ' target(s) selected. Prepare tarballs after completing the delivery details.' : 'No spectra selected.';
  }
  root.addEventListener('input', invalidate); root.addEventListener('change', invalidate);
  document.getElementById('delivery-clear').addEventListener('click', () => {
    root.querySelectorAll('input,select').forEach(el => {
      if (el.type === 'checkbox') el.checked = false;
      else if (el.tagName === 'INPUT') el.value = el.defaultValue;
      else el.value = el.hasAttribute('data-delivery-type') ? 'Object' : '';
    }); invalidate();
  });
  document.getElementById('delivery-build').addEventListener('click', () => {
    invalidate();
    const value = name => root.querySelector('[name="delivery-' + name + '"]').value;
    try {
      const choices = Object.fromEntries(controls.map(el => [el.dataset.deliveryTarget, el.value]));
      const archives = build(config, choices, {observers: value('observers'), reducers: value('reducers'), date: value('date'),
        group: value('group'), privateGroups: value('private-groups'), embargo: value('embargo'),
        types: Object.fromEntries([...root.querySelectorAll('[data-delivery-type]')].map(el => [el.dataset.deliveryType, el.value])),
        reviewed: root.querySelector('[name="delivery-reviewed"]').checked});
      for (const archive of archives) {
        const link = document.createElement('a'), url = URL.createObjectURL(new Blob([archive.bytes], {type: 'application/gzip'}));
        urls.push(url); link.href = url; link.download = archive.name;
        link.textContent = 'Download ' + archive.access + ' TGZ (' + archive.count + ' spectra)'; downloads.appendChild(link);
      }
      status.textContent = 'Ready. Download each tarball below; nothing has been uploaded.';
    } catch (error) { status.textContent = error.message; status.className = 'delivery-error'; }
  });
})();
