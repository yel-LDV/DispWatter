import { state, setToken } from "./state.js";
import { el, toast } from "./ui.js";
import { socket } from "./ws.js";

let authenticatedCallback = () => {};

export function initAuth(onAuthenticated) {
  authenticatedCallback = onAuthenticated;

  const form = el("loginForm");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    await submitLogin();
  });

  el("btnLogout")?.addEventListener("click", logout);
}

function showLogin(message = "") {
  el("loginScreen")?.classList.remove("hidden");
  el("appShell")?.classList.add("hidden");
  const error = el("loginError");
  if (error) error.textContent = message;
}

function showApp(user) {
  el("loginScreen")?.classList.add("hidden");
  el("appShell")?.classList.remove("hidden");
  el("userName").textContent = user?.username || "—";
  el("userRole").textContent = user?.role || "—";
}

async function submitLogin() {
  const username = el("loginUser").value.trim();
  const password = el("loginPassword").value;
  const submit = el("loginSubmit");
  const error = el("loginError");
  const card = el("loginForm");

  error.textContent = "";
  submit.disabled = true;
  submit.textContent = "Entrando…";

  try {
    const result = await socket.login(username, password);
    if (!result?.ok) {
      error.textContent = result?.message || "Usuario o contraseña incorrectos";
      card.classList.remove("shake");
      void card.offsetWidth;
      card.classList.add("shake");
      return;
    }

    setToken(result.token);
    state.user = result.user;
    showApp(result.user);
    authenticatedCallback();
    toast(`Bienvenido, ${result.user.username}`, "success");
  } catch (err) {
    error.textContent = err.message || "No se pudo conectar con el backend";
  } finally {
    submit.disabled = false;
    submit.textContent = "Entrar";
  }
}

export async function tryResume() {
  if (!state.token) {
    showLogin();
    return false;
  }
  try {
    const result = await socket.resume(state.token);
    if (!result?.ok) {
      setToken("");
      state.user = null;
      showLogin("La sesión ha caducado. Vuelve a iniciar sesión.");
      return false;
    }
    state.user = result.user;
    showApp(result.user);
    authenticatedCallback();
    return true;
  } catch {
    showLogin("No se pudo recuperar la sesión.");
    return false;
  }
}

export function logout() {
  socket.disconnect();
  setToken("");
  state.user = null;
  state.devices = [];
  window.location.reload();
}
