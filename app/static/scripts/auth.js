const IDLE_LIMIT_MS = 5 * 60 * 1000;
const WARNING_MS = 10 * 1000;
let lastActivity = Date.now();
let warningOpen = false;
let signingOut = false;
let audioContext = null;
let lastHeartbeatSecond = null;
let workspaceBusy = false;

const style = document.createElement('style');
style.textContent = `
  .session-overlay[hidden]{display:none}.session-overlay{position:fixed;inset:0;z-index:2000;display:grid;place-items:center;padding:24px;background:rgba(20,22,39,.48);backdrop-filter:blur(8px)}
  .session-dialog{width:min(440px,100%);padding:28px;border:1px solid var(--line,#e5e7ef);border-radius:20px;color:var(--ink,#171a2b);background:var(--surface,#fff);box-shadow:0 30px 90px rgba(21,24,45,.3)}
  .session-kicker{color:var(--primary,#5b5bd6);font-size:.65rem;font-weight:850;letter-spacing:.11em;text-transform:uppercase}.session-dialog h2{margin:9px 0 8px;font-size:1.45rem}.session-dialog p{margin:0;color:var(--muted,#72778c);font-size:.82rem;line-height:1.55}
  .session-countdown{margin:20px 0;padding:14px;display:flex;align-items:center;justify-content:space-between;border-radius:12px;background:var(--surface-soft,#f8f9fc)}.session-countdown strong{font-size:1.35rem;color:#cf2f3f}.session-actions{display:grid;grid-template-columns:1fr 1fr;gap:10px}.session-actions button{min-height:44px;margin:0;justify-content:center;border-radius:11px}.session-signout{color:var(--ink,#171a2b)!important;background:var(--surface-soft,#f8f9fc)!important;border:1px solid var(--line,#e5e7ef)!important;box-shadow:none!important}
  @media(max-width:480px){.session-actions{grid-template-columns:1fr}}
`;
document.head.append(style);

const overlay = document.createElement('div');
overlay.className = 'session-overlay';
overlay.hidden = true;
overlay.setAttribute('role', 'dialog');
overlay.setAttribute('aria-modal', 'true');
overlay.setAttribute('aria-labelledby', 'session-title');
overlay.innerHTML = `
  <div class="session-dialog">
    <span class="session-kicker">Session security</span>
    <h2 id="session-title">Are you still working?</h2>
    <p>You have been inactive for nearly five minutes. Continue to keep your workspace open.</p>
    <div class="session-countdown"><span>Signing out automatically in</span><strong id="session-seconds">10s</strong></div>
    <div class="session-actions"><button id="continue-session" type="button">Continue session</button><button class="session-signout" id="close-session" type="button">Sign out</button></div>
  </div>`;
document.body.append(overlay);

const seconds = document.getElementById('session-seconds');
const continueButton = document.getElementById('continue-session');
const closeButton = document.getElementById('close-session');

async function signOut() {
  if (signingOut) return;
  signingOut = true;
  try { await fetch('/api/auth/logout', {method: 'POST'}); } finally {
    window.location.replace('/login');
  }
}

function enableAlertAudio() {
  if (!audioContext) {
    const AudioEngine = window.AudioContext || window.webkitAudioContext;
    if (AudioEngine) audioContext = new AudioEngine();
  }
  if (audioContext?.state === 'suspended') audioContext.resume().catch(() => {});
}

function playHeartbeat() {
  if (!audioContext || audioContext.state !== 'running') return;
  const start = audioContext.currentTime;
  [0, 0.16].forEach((offset, index) => {
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.setValueAtTime(index === 0 ? 72 : 58, start + offset);
    gain.gain.setValueAtTime(0.0001, start + offset);
    gain.gain.exponentialRampToValueAtTime(index === 0 ? 0.22 : 0.14, start + offset + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + offset + 0.12);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(start + offset);
    oscillator.stop(start + offset + 0.13);
  });
}

function continueSession() {
  lastActivity = Date.now();
  warningOpen = false;
  overlay.hidden = true;
  lastHeartbeatSecond = null;
  document.body.classList.remove('dialog-open');
}

function noteActivity() {
  enableAlertAudio();
  if (!warningOpen) lastActivity = Date.now();
}

window.addEventListener('workspace-busy-change', event => {
  workspaceBusy = Boolean(event.detail?.busy);
  lastActivity = Date.now();
  lastHeartbeatSecond = null;
  if (workspaceBusy && warningOpen) {
    warningOpen = false;
    overlay.hidden = true;
    document.body.classList.remove('dialog-open');
  }
});

['pointerdown', 'keydown', 'touchstart', 'scroll'].forEach(name =>
  window.addEventListener(name, noteActivity, {passive: true}),
);
continueButton.addEventListener('click', continueSession);
closeButton.addEventListener('click', signOut);
document.getElementById('logout')?.addEventListener('click', async () => {
  const button = document.getElementById('logout');
  button.disabled = true;
  await signOut();
});

setInterval(() => {
  if (workspaceBusy) {
    lastActivity = Date.now();
    return;
  }
  const remaining = IDLE_LIMIT_MS - (Date.now() - lastActivity);
  if (remaining <= 0) {
    signOut();
    return;
  }
  if (remaining <= WARNING_MS) {
    const remainingSeconds = Math.max(1, Math.ceil(remaining / 1000));
    seconds.textContent = `${remainingSeconds}s`;
    if (remainingSeconds <= 5 && remainingSeconds !== lastHeartbeatSecond) {
      lastHeartbeatSecond = remainingSeconds;
      playHeartbeat();
    }
    if (!warningOpen) {
      warningOpen = true;
      overlay.hidden = false;
      document.body.classList.add('dialog-open');
      continueButton.focus();
    }
  }
}, 250);
