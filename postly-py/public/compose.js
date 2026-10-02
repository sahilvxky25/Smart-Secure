/* Compose windows: rich text editor, recipient autocomplete, draft autosave, undo-send. */

const composeWins = new Map(); // id -> state
let composeSeq = 0;
const SEND_DELAY_MS = 5000;

const quoteName = (p) => (/[,;<>"]/.test(p.name || '') ? `"${p.name.replace(/"/g, '')}" <${p.address}>` : fmtAddr(p));
const joinAddrs = (list) => (list || []).map(quoteName).join(', ');

function signatureHtml() {
  const s = (App.user && App.user.signature) || '';
  return s ? `<div data-sig="1">-- <br>${esc(s).replace(/\n/g, '<br>')}</div>` : '';
}

function openCompose(init = {}) {
  if (init.draftId) {
    for (const c of composeWins.values()) if (c.draftId === init.draftId) { setComposeMode(c, 'normal'); c.editor.focus(); return c; }
  }
  const c = {
    id: ++composeSeq,
    draftId: init.draftId || null,
    threadId: init.threadId || null,
    inReplyTo: init.inReplyTo || null,
    keep: init.attachments || [],   // attachments already stored on the server draft
    files: init.files || [],        // new File objects not yet uploaded
    dirty: false, closed: false, saveChain: Promise.resolve(),
  };
  const el = document.createElement('section');
  el.className = 'compose';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', 'New message');
  el.innerHTML = `
    <div class="compose-head" data-c="head">
      <span class="ttl">New message</span>
      <button class="icon-btn sm" data-c="min" aria-label="Minimize" data-icon="minus"></button>
      <button class="icon-btn sm" data-c="max" aria-label="Full screen" data-icon="maximize"></button>
      <button class="icon-btn sm" data-c="close" aria-label="Save and close" data-icon="x"></button>
    </div>
    <div class="compose-body">
      <div class="crow"><label for="c${c.id}to">To</label><input id="c${c.id}to" name="to" autocomplete="off" spellcheck="false">
        <span class="tog"><button type="button" data-c="tog-cc">Cc</button><button type="button" data-c="tog-bcc">Bcc</button></span></div>
      <div class="crow" data-row="cc" hidden><label for="c${c.id}cc">Cc</label><input id="c${c.id}cc" name="cc" autocomplete="off" spellcheck="false"></div>
      <div class="crow" data-row="bcc" hidden><label for="c${c.id}bcc">Bcc</label><input id="c${c.id}bcc" name="bcc" autocomplete="off" spellcheck="false"></div>
      <div class="crow"><label for="c${c.id}sub">Subject</label><input id="c${c.id}sub" name="subject" autocomplete="off"></div>
      <div class="editor" contenteditable="true" role="textbox" aria-multiline="true" aria-label="Message body"></div>
      <div class="cattach"></div>
      <div class="compose-foot">
        <button class="btn primary" data-c="send">Send</button>
        <button class="icon-btn" data-cmd="bold" aria-label="Bold" data-icon="bold"></button>
        <button class="icon-btn" data-cmd="italic" aria-label="Italic" data-icon="italic"></button>
        <button class="icon-btn" data-cmd="underline" aria-label="Underline" data-icon="underline"></button>
        <button class="icon-btn" data-cmd="insertUnorderedList" aria-label="Bulleted list" data-icon="list"></button>
        <button class="icon-btn" data-cmd="insertOrderedList" aria-label="Numbered list" data-icon="olist"></button>
        <button class="icon-btn" data-cmd="link" aria-label="Insert link" data-icon="link"></button>
        <button class="icon-btn" data-c="attach" aria-label="Attach files" data-icon="clip"></button>
        <button class="icon-btn" data-c="discard" aria-label="Discard draft" data-icon="trash"></button>
        <span class="status" aria-live="polite"></span>
      </div>
      <input type="file" multiple hidden>
    </div>`;
  c.el = el;
  c.editor = $('.editor', el);
  c.fileInput = $('input[type=file]', el);
  c.status = $('.status', el);
  c.inputs = { to: $('[name=to]', el), cc: $('[name=cc]', el), bcc: $('[name=bcc]', el), subject: $('[name=subject]', el) };

  c.inputs.to.value = init.to || '';
  c.inputs.cc.value = init.cc || '';
  c.inputs.bcc.value = init.bcc || '';
  c.inputs.subject.value = init.subject || '';
  c.editor.innerHTML = init.html != null ? init.html : `<div><br></div>${signatureHtml()}`;
  if (init.cc) $('[data-row=cc]', el).hidden = false;
  if (init.bcc) $('[data-row=bcc]', el).hidden = false;
  updateComposeTitle(c);
  renderComposeAttachments(c);

  paintIcons(el);
  $('#composeDock').append(el);
  composeWins.set(c.id, c);
  wireCompose(c);

  if (init.focus === 'editor' || init.to) {
    c.editor.focus();
    const r = document.createRange();
    r.setStart(c.editor, 0); r.collapse(true);
    const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
  } else c.inputs.to.focus();
  return c;
}

function updateComposeTitle(c) {
  $('.ttl', c.el).textContent = c.inputs.subject.value.trim() || 'New message';
}

function setComposeMode(c, mode) {
  c.el.classList.toggle('min', mode === 'min' ? !c.el.classList.contains('min') : false);
  if (mode === 'max') c.el.classList.toggle('max');
  if (mode === 'normal') c.el.classList.remove('min');
}

function wireCompose(c) {
  const el = c.el;
  const touch = () => { c.dirty = true; scheduleDraftSave(c); };

  el.addEventListener('input', (e) => {
    if (e.target === c.inputs.subject) updateComposeTitle(c);
    if (['to', 'cc', 'bcc'].includes(e.target.name)) suggestFor(c, e.target);
    touch();
  });
  el.addEventListener('mousedown', (e) => { if (e.target.closest('[data-cmd]')) e.preventDefault(); }); // keep editor selection
  el.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); sendCompose(c); }
    if (['to', 'cc', 'bcc'].includes(e.target.name)) suggestKeys(c, e);
  });
  el.addEventListener('focusout', (e) => { if (['to', 'cc', 'bcc'].includes(e.target.name)) setTimeout(() => closeSuggest(c), 150); });
  c.fileInput.addEventListener('change', () => {
    addComposeFiles(c, [...c.fileInput.files]);
    c.fileInput.value = '';
  });
  // paste/drop files into the editor
  c.editor.addEventListener('paste', (e) => {
    const files = [...(e.clipboardData?.files || [])];
    if (files.length) { e.preventDefault(); addComposeFiles(c, files); }
  });
  el.addEventListener('dragover', (e) => { if (e.dataTransfer?.types?.includes('Files')) e.preventDefault(); });
  el.addEventListener('drop', (e) => { if (e.dataTransfer?.files?.length) { e.preventDefault(); addComposeFiles(c, [...e.dataTransfer.files]); } });

  el.addEventListener('click', (e) => {
    const rm = e.target.closest('[data-rm]');
    if (rm) {
      const [kind, key] = rm.dataset.rm.split(':');
      if (kind === 'k') c.keep = c.keep.filter((a) => String(a.id) !== key);
      else c.files.splice(Number(key), 1);
      renderComposeAttachments(c); c.dirty = true; scheduleDraftSave(c);
      return;
    }
    const cmd = e.target.closest('[data-cmd]');
    if (cmd) {
      c.editor.focus();
      if (cmd.dataset.cmd === 'link') {
        const url = prompt('Link address (https://…)');
        if (url && /^(https?:\/\/|mailto:)/i.test(url.trim())) document.execCommand('createLink', false, url.trim());
        else if (url) toast('Links must start with http://, https:// or mailto:', { error: true });
      } else document.execCommand(cmd.dataset.cmd);
      touch();
      return;
    }
    const act = e.target.closest('[data-c]');
    if (!act) return;
    switch (act.dataset.c) {
      case 'head': if (!e.target.closest('button')) setComposeMode(c, 'min'); break;
      case 'min': setComposeMode(c, 'min'); break;
      case 'max': setComposeMode(c, 'max'); break;
      case 'close': closeCompose(c); break;
      case 'send': sendCompose(c); break;
      case 'discard': discardCompose(c); break;
      case 'attach': c.fileInput.click(); break;
      case 'tog-cc': case 'tog-bcc': {
        const row = $(`[data-row=${act.dataset.c.slice(4)}]`, el);
        row.hidden = !row.hidden;
        if (!row.hidden) $('input', row).focus();
        break;
      }
    }
  });
}

// ---------- attachments ----------

function addComposeFiles(c, files) {
  const total = [...c.files, ...files].reduce((n, f) => n + f.size, 0) + c.keep.reduce((n, a) => n + a.size, 0);
  if (total > 25 * 1048576) return toast('Attachments can’t be more than 25 MB in total', { error: true });
  c.files.push(...files);
  renderComposeAttachments(c);
  c.dirty = true;
  scheduleDraftSave(c);
}

function renderComposeAttachments(c) {
  const chip = (name, size, key) => `<span class="att">${icon('clip')}<span>${esc(name)}</span><small>${fmtSize(size)}</small><button type="button" class="icon-btn sm" data-rm="${key}" aria-label="Remove ${esc(name)}">${icon('x')}</button></span>`;
  $('.cattach', c.el).innerHTML =
    c.keep.map((a) => chip(a.filename, a.size, `k:${a.id}`)).join('') + c.files.map((f, i) => chip(f.name, f.size, `f:${i}`)).join('');
}

// ---------- recipient autocomplete ----------

function closeSuggest(c) { $('.suggest', c.el)?.remove(); }

const fetchContacts = debounce(async (c, input, token) => {
  try {
    const list = await api('/api/contacts?q=' + encodeURIComponent(token));
    closeSuggest(c);
    if (!list.length || document.activeElement !== input) return;
    const box = document.createElement('div');
    box.className = 'suggest';
    box.innerHTML = list.map((p, i) => `<button type="button" data-pick="${esc(quoteName(p))}" class="${i === 0 ? 'sel' : ''}">${esc(displayName(p))}<small>${esc(p.address)}</small></button>`).join('');
    box.addEventListener('mousedown', (e) => {
      const b = e.target.closest('[data-pick]');
      if (!b) return;
      e.preventDefault();
      pickSuggestion(input, b.dataset.pick);
      closeSuggest(c);
      c.dirty = true; scheduleDraftSave(c);
    });
    input.closest('.crow').append(box);
  } catch { /* autocomplete is best-effort */ }
}, 160);

function suggestFor(c, input) {
  const token = input.value.split(',').pop().trim();
  if (token.length < 2) return closeSuggest(c);
  fetchContacts(c, input, token);
}

function pickSuggestion(input, text) {
  const parts = input.value.split(',');
  parts.pop();
  input.value = [...parts.map((p) => p.trim()).filter(Boolean), text].join(', ') + ', ';
  input.focus();
}

function suggestKeys(c, e) {
  const box = $('.suggest', c.el);
  if (!box) return;
  const items = $$('button', box);
  let i = items.findIndex((b) => b.classList.contains('sel'));
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    items[i]?.classList.remove('sel');
    i = (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
    items[i].classList.add('sel');
  } else if (e.key === 'Enter' || e.key === 'Tab') {
    if (i >= 0) { e.preventDefault(); pickSuggestion(e.target, items[i].dataset.pick); closeSuggest(c); }
  } else if (e.key === 'Escape') { e.stopPropagation(); closeSuggest(c); }
}

// ---------- drafts ----------

function composeFields(c) {
  return {
    to: c.inputs.to.value.trim(), cc: c.inputs.cc.value.trim(), bcc: c.inputs.bcc.value.trim(),
    subject: c.inputs.subject.value.trim(), html: c.editor.innerHTML,
  };
}

/** True if the editor has real text/images beyond the signature and any quoted reply. */
function composeHasBody(c) {
  const probe = c.editor.cloneNode(true);
  $$('[data-sig], blockquote, .quote-wrap', probe).forEach((n) => n.remove());
  return probe.textContent.trim().length > 0 || !!$('img', probe);
}

function composeIsEmpty(c) {
  const f = composeFields(c);
  return !f.to && !f.cc && !f.bcc && !f.subject && !composeHasBody(c) && !c.files.length && !c.keep.length;
}

function buildForm(c) {
  const f = composeFields(c);
  const fd = new FormData();
  Object.entries(f).forEach(([k, v]) => fd.append(k, v));
  if (c.inReplyTo) fd.append('inReplyTo', c.inReplyTo);
  if (c.threadId) fd.append('threadId', c.threadId);
  if (c.draftId) fd.append('draftId', c.draftId);
  fd.append('keepAttachments', JSON.stringify(c.keep.map((a) => a.id)));
  c.files.forEach((file) => fd.append('attachments', file, file.name));
  return fd;
}

const scheduleDraftSave = (c) => {
  clearTimeout(c.saveTimer);
  c.status.textContent = '';
  c.saveTimer = setTimeout(() => saveDraft(c).catch(() => {}), 1800);
};

/** Serialised so two saves never race each other. */
function saveDraft(c, { force = false } = {}) {
  clearTimeout(c.saveTimer);
  c.saveChain = c.saveChain.catch(() => {}).then(async () => {
    if (c.closed && !force) return;
    if (composeIsEmpty(c) && !c.draftId) return;
    c.status.textContent = 'Saving…';
    try {
      const res = await api('/api/drafts', { method: 'POST', form: buildForm(c) });
      c.draftId = res.id; c.threadId = res.threadId; c.keep = res.attachments; c.files = [];
      c.dirty = false;
      renderComposeAttachments(c);
      c.status.textContent = 'Draft saved';
    } catch (e) {
      c.status.textContent = 'Not saved';
      throw e;
    }
  });
  return c.saveChain;
}

function removeComposeWindow(c) {
  c.closed = true;
  clearTimeout(c.saveTimer);
  c.el.remove();
  composeWins.delete(c.id);
}

async function closeCompose(c) {
  if (composeIsEmpty(c)) {
    const id = c.draftId;
    removeComposeWindow(c);
    if (id) api('/api/threads/batch', { method: 'POST', body: { action: 'delete', threads: ['d' + id], scope: 'drafts' } }).catch(() => {});
    return;
  }
  try {
    await saveDraft(c);
    removeComposeWindow(c);
    toast('Draft saved');
  } catch (e) {
    toast(`Couldn’t save the draft: ${e.message}`, { error: true });
  }
}

async function discardCompose(c) {
  const id = c.draftId;
  await c.saveChain.catch(() => {});
  const real = c.draftId || id;
  removeComposeWindow(c);
  if (real) {
    try { await api('/api/threads/batch', { method: 'POST', body: { action: 'delete', threads: ['d' + real], scope: 'drafts' } }); } catch { /* ignore */ }
  }
  toast('Draft discarded');
  App.refresh();
}

// ---------- sending (with undo) ----------

async function sendCompose(c) {
  const f = composeFields(c);
  if (!f.to && !f.cc && !f.bcc) {
    toast('Add at least one recipient', { error: true });
    c.inputs.to.focus();
    return;
  }
  if (!f.subject && !composeHasBody(c) && !c.files.length && !c.keep.length) {
    if (!confirm('Send this message without a subject or text?')) return;
  } else if (!f.subject && !confirm('Send this message without a subject?')) return;

  $('[data-c=send]', c.el).disabled = true;
  try {
    await saveDraft(c, { force: true }); // persisted first, so nothing is lost if the tab closes during the undo window
  } catch (e) {
    $('[data-c=send]', c.el).disabled = false;
    return toast(`Couldn’t send: ${e.message}`, { error: true });
  }
  const snapshot = { to: f.to, cc: f.cc, bcc: f.bcc, subject: f.subject, html: f.html, draftId: c.draftId, threadId: c.threadId, inReplyTo: c.inReplyTo, attachments: c.keep };
  removeComposeWindow(c);

  let cancelled = false;
  let timer;
  const t = toast('Sending…', {
    action: 'Undo', ms: SEND_DELAY_MS + 1500,
    onAction: () => { cancelled = true; clearTimeout(timer); openCompose({ ...snapshot, focus: 'editor' }); },
  });
  timer = setTimeout(async () => {
    if (cancelled) return;
    const fd = new FormData();
    ['to', 'cc', 'bcc', 'subject', 'html'].forEach((k) => fd.append(k, snapshot[k]));
    if (snapshot.inReplyTo) fd.append('inReplyTo', snapshot.inReplyTo);
    if (snapshot.threadId) fd.append('threadId', snapshot.threadId);
    fd.append('draftId', snapshot.draftId);
    fd.append('keepAttachments', JSON.stringify(snapshot.attachments.map((a) => a.id)));
    try {
      await api('/api/send', { method: 'POST', form: fd });
      t.dismiss();
      toast('Message sent');
    } catch (e) {
      t.dismiss();
      toast(`Couldn’t send: ${e.message}. It’s saved in Drafts.`, { error: true, ms: 9000 });
    }
    App.refresh();
  }, SEND_DELAY_MS);
}

// ---------- reply / forward helpers ----------

function quoteBlock(m) {
  return `<div class="quote-wrap">On ${esc(fmtLongDate(m.date))}, ${esc(displayName(m.from))} &lt;${esc(m.from.address)}&gt; wrote:<blockquote>${m.html}</blockquote></div>`;
}

const prefixSubject = (s, p) => (new RegExp(`^${p}:`, 'i').test(s || '') ? s : `${p}: ${s || ''}`.trim());

function startReply(m, thread, all = false) {
  const me = App.user.email;
  let to, cc = [];
  if (m.folder === 'sent') to = m.to;
  else to = [m.from];
  if (all) {
    const seen = new Set([me, ...to.map((p) => p.address)]);
    cc = [...m.to, ...m.cc].filter((p) => !seen.has(p.address) && seen.add(p.address));
    if (m.folder !== 'sent') to = [m.from, ...m.to.filter((p) => p.address !== me && p.address !== m.from.address)];
    to = to.filter((p, i, a) => a.findIndex((q) => q.address === p.address) === i);
  }
  openCompose({
    to: joinAddrs(to), cc: joinAddrs(cc), subject: prefixSubject(m.subject || thread.subject, 'Re'),
    threadId: thread.threadId, inReplyTo: m.messageId,
    html: `<div><br></div>${signatureHtml()}<br>${quoteBlock(m)}`, focus: 'editor',
  });
}

async function startForward(m, thread) {
  let files = [];
  if (m.attachments.length) {
    const t = toast('Preparing attachments…', { ms: 15000 });
    try {
      files = await Promise.all(m.attachments.map(async (a) => {
        const r = await fetch(`/api/attachments/${a.id}?download=1`, { credentials: 'same-origin' });
        return new File([await r.blob()], a.filename, { type: a.contentType });
      }));
    } catch { toast('Couldn’t copy the attachments', { error: true }); }
    t.dismiss();
  }
  const head = `---------- Forwarded message ----------<br>From: ${esc(fmtAddr(m.from))}<br>Date: ${esc(fmtLongDate(m.date))}<br>Subject: ${esc(m.subject)}<br>To: ${esc(joinAddrs(m.to))}<br><br>`;
  openCompose({
    subject: prefixSubject(m.subject || thread.subject, 'Fwd'),
    html: `<div><br></div>${signatureHtml()}<br><div class="quote-wrap">${head}${m.html}</div>`, files,
  });
}

async function editDraft(id) {
  try {
    const d = await api('/api/drafts/' + id);
    openCompose({
      draftId: d.id, to: joinAddrs(d.to), cc: joinAddrs(d.cc), bcc: joinAddrs(d.bcc), subject: d.subject, html: d.html,
      threadId: d.threadId, inReplyTo: d.inReplyTo, attachments: d.attachments, focus: 'editor',
    });
  } catch (e) { toast(e.message, { error: true }); }
}

window.addEventListener('beforeunload', (e) => {
  if ([...composeWins.values()].some((c) => c.dirty && !composeIsEmpty(c))) { e.preventDefault(); e.returnValue = ''; }
});
