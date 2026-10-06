// Drives the real static/app.js in two jsdom "browsers" against a running server.
// Usage: npm i jsdom && node tests/ui_test.js http://127.0.0.1:8000
const { JSDOM, CookieJar } = require('jsdom');
const BASE = process.argv[2] || 'http://127.0.0.1:8000';
const RUN = Math.random().toString(36).slice(2, 7);
let passed = 0;
const ok = (c, l) => { if (!c) { console.error('  ✗ FAILED:', l); process.exit(1); } passed++; console.log('  ✓', l); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, label, ms = 5000) {
  const end = Date.now() + ms;
  while (Date.now() < end) { try { const v = fn(); if (v) return v; } catch {} await sleep(40); }
  throw new Error('Timed out waiting for: ' + label);
}

async function browser(name) {
  const jar = new CookieJar(); const errors = [];
  const dom = await JSDOM.fromURL(BASE + '/', {
    runScripts: 'dangerously', resources: 'usable', pretendToBeVisual: true, cookieJar: jar,
    beforeParse(w) {
      w.matchMedia = (q) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {} });
      w.Element.prototype.scrollTo = function () {}; w.Element.prototype.scrollIntoView = function () {};
      w.confirm = () => true;
      w.addEventListener('error', (e) => errors.push(e.message));
      w.fetch = async (url, opts = {}) => {
        const full = new URL(url, BASE).href;
        const r = await fetch(full, { ...opts, redirect: 'manual', headers: { ...(opts.headers || {}), Cookie: jar.getCookieStringSync(full), Origin: BASE } });
        for (const c of r.headers.getSetCookie()) jar.setCookieSync(c, full);
        return r;
      };
    },
  });
  const w = dom.window, d = w.document;
  const b = {
    name, w, d, errors,
    $: (s) => d.querySelector(s), $$: (s) => [...d.querySelectorAll(s)],
    byText: (sel, t) => [...d.querySelectorAll(sel)].find((e) => e.textContent.trim().includes(t)),
    type(el, v) { el.value = v; el.dispatchEvent(new w.Event('input', { bubbles: true })); },
    click(el) { el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true })); },
    field(label) { const l = [...d.querySelectorAll('label.field')].find((x) => x.querySelector('span') && x.querySelector('span').textContent.includes(label)); return l && l.querySelector('input,select,textarea'); },
  };
  await until(() => d.querySelector('.auth,.app'), name + ' boot');
  return b;
}

async function register(b, nm, email) {
  b.click(b.byText('button.link', 'Create account'));
  await until(() => b.$('h1') && b.$('h1').textContent.includes('Create your account'), 'register view');
  b.type(b.field('Your name'), nm); b.type(b.field('Email'), email); b.type(b.field('Password'), 'Passw0rd!x');
  await until(() => b.$$('select option').length > 3, 'questions loaded');
  b.type(b.field('Answer'), 'Rex the Dog');
  b.click(b.byText('button', 'Create account'));
  await until(() => b.$('.app'), nm + ' enters the app');
}

(async () => {
  console.log('UI: sign-up');
  const A = await browser('alice'), B = await browser('bob');
  ok(A.$('h1').textContent === 'Sign in', 'login screen renders');
  const ea = `alice.${RUN}@ui.test`, eb = `bob.${RUN}@ui.test`;
  await register(A, 'Alice', ea); await register(B, 'Bob', eb);
  ok(A.$('.top .avatar.me') && A.$('.empty-list'), 'registered user lands in the app (empty chat list)');

  console.log('UI: start a chat and exchange messages in real time');
  A.click(A.$('[aria-label="New chat"]'));
  await until(() => A.field('Their email'), 'new chat dialog');
  A.type(A.field('Their email'), eb); A.click(A.byText('.modal button', 'Start chat'));
  await until(() => A.$('.chat-head .t1'), 'chat opens');
  ok(A.$('.chat-head .t1').textContent === 'Bob', 'chat with Bob opened');
  A.type(A.$('.composer textarea'), 'Hello Bob <img src=x onerror=alert(1)> https://example.com/x');
  A.click(A.$('.send'));
  await until(() => A.$('.msg.out'), 'message appears for sender');
  ok(!A.$('.msg.out img') && A.$('.msg.out .text').textContent.includes('<img src=x'), 'HTML in messages is shown as text (no XSS)');
  ok(A.$('.msg.out .text a') && A.$('.msg.out .text a').rel.includes('noopener'), 'links are clickable and safe');
  const item = await until(() => B.$('.item.unread'), 'Bob sees unread chat live');
  ok(item.querySelector('.badge').textContent === '1' && item.textContent.includes('Hello Bob'), 'Bob sees unread badge + preview');
  await until(() => A.$('.msg.out .tick:not(.read)'), 'delivered tick'); ok(true, 'Alice sees delivered ✓✓ (grey)');
  B.click(item);
  await until(() => B.$('.msg.in'), 'Bob opens chat');
  await until(() => A.$('.msg.out .tick.read'), 'read tick');
  ok(true, 'Alice sees read ✓✓ (blue) after Bob opens the chat');
  ok(!B.$('.item .badge'), 'unread badge clears');
  B.type(B.$('.composer textarea'), 'typing...');
  await until(() => /typing/.test(A.$('.chat-head .t2').textContent), 'typing indicator');
  ok(true, 'typing indicator shows in header');
  B.type(B.$('.composer textarea'), 'Hi Alice!'); B.click(B.$('.send'));
  await until(() => A.$$('.msg.in').length === 1, 'reply arrives');
  ok(A.$('.msg.in .text').textContent.includes('Hi Alice!'), 'live reply arrives');
  // reply & delete via menu
  A.click(A.$('.msg.in .menu-btn')); A.click(A.byText('.popup button', 'Reply'));
  A.type(A.$('.composer textarea'), 'quoted!'); A.click(A.$('.send'));
  await until(() => A.$('.msg.out .quote'), 'quoted reply'); ok(A.$('.msg.out .quote').textContent.includes('Hi Alice!'), 'reply shows quoted message');
  A.click(A.$$('.msg.out .menu-btn').pop()); A.click(A.byText('.popup button', 'Delete for everyone'));
  await until(() => A.$('.bubble.deleted'), 'deleted'); await until(() => B.$('.bubble.deleted'), 'deleted on peer');
  ok(true, 'delete-for-everyone updates both sides');

  console.log('UI: groups');
  A.click(A.$('[aria-label="Menu"]')); A.click(A.byText('.popup button', 'New group'));
  await until(() => A.field('Group name'), 'group dialog');
  A.type(A.field('Group name'), 'Weekend plans');
  await until(() => A.$('.pick input'), 'contacts listed'); A.$('.pick input').checked = true;
  A.click(A.byText('.modal button', 'Create group'));
  await until(() => A.$('.chat-head .t1') && A.$('.chat-head .t1').textContent === 'Weekend plans', 'group opens');
  ok(true, 'group created with a contact selected');
  await until(() => B.byText('.item .name', 'Weekend plans'), 'Bob receives the group live'); ok(true, 'Bob sees the new group instantly');
  A.type(A.$('.composer textarea'), 'Who is in?'); A.click(A.$('.send'));
  B.click(B.byText('.item', 'Weekend plans'));
  await until(() => B.byText('.msg.in .text', 'Who is in?'), 'group message'); ok(B.$('.msg.in .sender').textContent === 'Alice', 'group messages show sender name');
  A.click(A.$('.chat-head .who')); await until(() => A.byText('.modal h4', 'Members'), 'group info');
  ok(A.byText('.modal .tag', 'Admin') && A.byText('.modal button', 'Leave group'), 'group info shows admin badge + controls');
  A.click(A.$('.modal-head .iconbtn'));

  console.log('UI: settings, change password, 2FA setup screen');
  A.click(A.$('.top .avatar.me')); await until(() => A.byText('.modal h4', 'Two-step verification'), 'settings');
  ok(['Profile', 'Appearance', 'Change password', 'Security question', 'Devices', 'Delete account'].every((t) => A.byText('.modal h4', t)), 'settings has every section');
  A.click(A.byText('.modal button', 'Set up 2FA'));
  await until(() => A.$('.modal img.qr'), '2FA QR'); ok(A.$('.modal img.qr').src.startsWith('data:image/svg+xml') && A.$('.secret').textContent.length >= 16, '2FA shows QR code and manual key');
  A.type(A.field('Current password'), 'Passw0rd!x'); A.type(A.field('New password'), 'NewPassw0rd9'); A.type(A.field('Confirm new'), 'NewPassw0rd9');
  A.click(A.byText('.modal button', 'Change password')); await until(() => A.byText('.modal .ok', 'Password changed'), 'password changed'); ok(true, 'change password from the UI');
  A.click(A.$('.modal-head .iconbtn'));

  console.log('UI: log out, forgot password, delete account');
  A.click(A.$('[aria-label="Menu"]')); A.click(A.byText('.popup button', 'Log out'));
  await until(() => A.$('h1') && A.$('h1').textContent === 'Sign in', 'logged out'); ok(true, 'log out returns to sign-in');
  A.click(A.byText('button.link', 'Forgot password?')); await until(() => A.$('h1').textContent.includes('Reset'), 'forgot view');
  A.type(A.field('Email'), ea); A.click(A.byText('button', 'Continue'));
  await until(() => A.$('.q-box'), 'question shown'); ok(A.$('.q-box').textContent === 'What was the name of your first pet?', 'forgot-password shows the question chosen at sign-up');
  A.type(A.field('Your answer'), 'wrong'); A.click(A.byText('button', 'Verify answer'));
  await until(() => A.$('.err:not([hidden])'), 'wrong answer error'); ok(true, 'wrong answer is rejected');
  A.type(A.field('Your answer'), 'REX the dog'); A.click(A.byText('button', 'Verify answer'));
  await until(() => A.$('h1').textContent.includes('new password'), 'reset view');
  A.type(A.field('New password'), 'ResetPass42'); A.type(A.field('Confirm new'), 'ResetPass42'); A.click(A.byText('button', 'Save new password'));
  await until(() => A.$('.ok') && A.$('h1').textContent === 'Sign in', 'back to login'); ok(true, 'password reset completes');
  A.type(A.field('Email'), ea); A.type(A.field('Password'), 'ResetPass42'); A.click(A.byText('button', 'Sign in'));
  await until(() => A.$('.app'), 'login with reset password'); ok(true, 'can sign in with the reset password');
  A.click(A.$('.top .avatar.me')); await until(() => A.byText('.modal button', 'Delete my account'), 'settings');
  A.click(A.byText('.modal button', 'Delete my account')); await until(() => A.field('Type DELETE'), 'delete dialog');
  A.type(A.field('Your password'), 'ResetPass42'); A.type(A.field('Type DELETE'), 'DELETE');
  A.click(A.byText('.modal button', 'Permanently delete account'));
  await until(() => A.$('h1') && A.$('.ok') && A.$('.ok').textContent.includes('deleted'), 'deleted'); ok(true, 'account deleted from the UI');
  await until(() => !B.byText('.item .name', 'Alice'), 'Bob loses the 1:1 chat'); ok(true, "Bob's chat with Alice disappears live");

  ok(A.errors.length === 0 && B.errors.length === 0, 'no JavaScript errors in either browser: ' + JSON.stringify([...A.errors, ...B.errors]));
  console.log(`\nAll ${passed} UI checks passed ✔`); process.exit(0);
})().catch((e) => { console.error('UI TEST ERROR:', e.message); process.exit(1); });
