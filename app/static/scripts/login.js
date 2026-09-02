const form = document.getElementById('login-form');
const button = document.getElementById('login-button');
const status = document.getElementById('login-status');
const overlay = document.getElementById('auth-overlay');
const errorTitle = document.getElementById('auth-error-title');
const errorMessage = document.getElementById('auth-error-message');
const dismissError = document.getElementById('dismiss-auth-error');
const username = document.getElementById('username');
const password = document.getElementById('password');
const passwordToggle = document.getElementById('password-toggle');
const forgotPassword = document.getElementById('forgot-password');

passwordToggle.addEventListener('click', () => {
  const reveal = password.type === 'password';
  password.type = reveal ? 'text' : 'password';
  passwordToggle.setAttribute('aria-pressed', String(reveal));
  passwordToggle.setAttribute('aria-label', reveal ? 'Hide password' : 'Show password');
  password.focus({preventScroll: true});
  const cursor = password.value.length;
  password.setSelectionRange(cursor, cursor);
});

forgotPassword.addEventListener('click', () => {
  errorTitle.textContent = 'Password reset assistance';
  errorMessage.textContent =
    'This private workspace does not reset passwords by email. Contact your workspace administrator to update your account password securely.';
  status.textContent = '';
  status.classList.remove('error');
  overlay.classList.add('help');
  overlay.hidden = false;
  document.body.classList.add('dialog-open');
  dismissError.textContent = 'Back to sign in';
  dismissError.focus();
});

function clearError() {
  overlay.hidden = true;
  document.body.classList.remove('dialog-open');
  [username, password].forEach(input => {
    input.classList.remove('input-invalid');
    input.removeAttribute('aria-invalid');
  });
  status.classList.remove('error');
  overlay.classList.remove('help');
  dismissError.textContent = 'Try again';
}

function showError(message, invalidCredentials) {
  errorTitle.textContent = invalidCredentials
    ? "We couldn't verify those details"
    : 'Sign-in is temporarily unavailable';
  errorMessage.textContent = invalidCredentials
    ? 'The username or password is incorrect. Check your details and try again.'
    : message;
  [username, password].forEach(input => {
    input.classList.toggle('input-invalid', invalidCredentials);
    if (invalidCredentials) input.setAttribute('aria-invalid', 'true');
  });
  status.textContent = message;
  status.classList.add('error');
  overlay.hidden = false;
  document.body.classList.add('dialog-open');
  dismissError.focus();
}

dismissError.addEventListener('click', () => {
  clearError();
  password.select();
});
overlay.addEventListener('click', event => {
  if (event.target === overlay) dismissError.click();
});
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && !overlay.hidden) dismissError.click();
});
[username, password].forEach(input => input.addEventListener('input', clearError));

form.addEventListener('submit', async event => {
  event.preventDefault();
  clearError();
  button.disabled = true;
  status.textContent = 'Authenticating…';
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({username: username.value.trim(), password: password.value}),
    });
    if (!response.ok) {
      let message = 'Sign-in failed.';
      try { message = (await response.json()).detail || message; } catch {}
      const error = new Error(message);
      error.invalidCredentials = response.status === 401;
      throw error;
    }
    status.textContent = 'Authenticated. Opening your workspace…';
    window.location.replace('/');
  } catch (error) {
    showError(error.message, Boolean(error.invalidCredentials));
    button.disabled = false;
  }
});
