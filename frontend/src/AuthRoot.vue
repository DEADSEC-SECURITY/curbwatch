<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import {
  LockKeyhole,
  ArrowRight,
  LoaderCircle,
  ShieldCheck,
} from "@lucide/vue";
import App from "./App.vue";
import { api, setCsrfToken } from "./api";
import PwaControls from "./components/PwaControls.vue";
import { PHONE_QUERY } from "./dialog.js";

const user = ref(null),
  ready = ref(false),
  busy = ref(false),
  error = ref("");
const configuration = ref({}),
  email = ref(""),
  password = ref(""),
  name = ref("");
const invite = ref(
  location.hash.startsWith("#invite/") ? location.hash.slice(8) : "",
);
const channel =
  typeof BroadcastChannel !== "undefined"
    ? new BroadcastChannel("curbwatch-auth")
    : null;
let timer;
function clearPrivateStorage(allDrafts = true) {
  try {
    localStorage.removeItem("curbwatch-snapshot-v1");
    sessionStorage.removeItem("curbwatch-vehicle-draft");
    if (allDrafts) {
      Object.keys(sessionStorage)
        .filter((key) => key.startsWith("curbwatch-vehicle-draft-"))
        .forEach((key) => sessionStorage.removeItem(key));
    }
  } catch {}
}
function signedIn(session, completeInvitation = false) {
  if (user.value && user.value.id !== session.user.id) clearPrivateStorage();
  setCsrfToken(session.csrf_token);
  user.value = session.user;
  password.value = "";
  error.value = "";
  if (
    completeInvitation ||
    (!invite.value && location.hash.startsWith("#login"))
  ) {
    invite.value = "";
    history.replaceState(
      null,
      "",
      window.matchMedia(PHONE_QUERY).matches ? "#today" : "#map",
    );
  }
}
function signedOut() {
  user.value = null;
  setCsrfToken("");
  password.value = "";
  clearPrivateStorage();
}
async function load() {
  error.value = "";
  try {
    configuration.value = await api("/auth/config");
    try {
      signedIn(await api("/auth/session"));
    } catch (failure) {
      if (failure.status !== 401) throw failure;
      signedOut();
    }
  } catch (failure) {
    error.value = failure.message;
  } finally {
    ready.value = true;
  }
}
async function submit() {
  busy.value = true;
  error.value = "";
  try {
    const session = await api(
      invite.value ? "/auth/invitations/accept" : "/auth/login",
      {
        method: "POST",
        body: invite.value
          ? { token: invite.value, password: password.value, name: name.value }
          : { email: email.value, password: password.value },
      },
    );
    signedIn(session, true);
    channel?.postMessage("changed");
  } catch (failure) {
    error.value = failure.message;
  } finally {
    busy.value = false;
  }
}
async function logout() {
  busy.value = true;
  try {
    await api("/auth/logout", { method: "POST", body: {} });
    signedOut();
    channel?.postMessage("logout");
  } catch (failure) {
    error.value = failure.message;
  } finally {
    busy.value = false;
  }
}
function unauthorized() {
  if (user.value) {
    signedOut();
    error.value = "Your session ended. Sign in again to continue.";
  }
}
async function checkSession() {
  if (!user.value) return;
  try {
    signedIn(await api("/auth/session"));
  } catch (failure) {
    if (failure.status === 401) unauthorized();
  }
}
function visible() {
  if (!document.hidden) checkSession();
}
function cancelInvite() {
  invite.value = "";
  password.value = "";
  error.value = "";
  history.replaceState(null, "", "#login");
}
onMounted(async () => {
  clearPrivateStorage(false);
  const ssoError = location.hash.startsWith("#login?error=");
  await load();
  if (ssoError)
    error.value =
      "SSO could not sign you in. Check that your administrator has added your verified email and that the provider is configured correctly.";
  window.addEventListener("curbwatch:unauthorized", unauthorized);
  document.addEventListener("visibilitychange", visible);
  timer = setInterval(checkSession, 60000);
  if (channel)
    channel.onmessage = (event) =>
      event.data === "logout" ? signedOut() : load();
});
onBeforeUnmount(() => {
  clearInterval(timer);
  channel?.close();
  window.removeEventListener("curbwatch:unauthorized", unauthorized);
  document.removeEventListener("visibilitychange", visible);
});
</script>
<template>
  <App
    v-if="user && !invite"
    :key="user.id"
    :user="user"
    @logout="logout"
    @session="signedIn"
  />
  <main v-else class="auth-page">
    <div class="auth-brand">
      <span class="brand-mark">P<span></span></span
      ><strong>curbwatch<span class="brand-period">.</span></strong>
    </div>
    <section class="auth-card">
      <span class="modal-icon"><LockKeyhole :size="26" /></span>
      <span class="eyebrow">YOUR PARKING, TOGETHER</span>
      <h1>{{ invite ? "You’re invited." : "Welcome back." }}</h1>
      <p>
        {{
          invite
            ? "Choose a password to activate the account your administrator invited."
            : "Sign in to your garage and street activity."
        }}
      </p>
      <p v-if="!ready" role="status">
        <LoaderCircle class="spin" :size="18" /> Checking access…
      </p>
      <div
        v-else-if="configuration.setup_required"
        class="auth-setup"
        role="status"
      >
        <ShieldCheck :size="22" /><strong>Ready for your administrator</strong>
        <p>
          The first admin hasn’t been configured yet. Use the deployment setup
          in <code>docs/authentication.md</code> to create it. Public signup is
          closed.
        </p>
        <button class="button secondary" @click="load">Check again</button>
      </div>
      <form v-else class="auth-form" @submit.prevent="submit">
        <template v-if="invite"
          ><label for="invite-name">Your name <span>(optional)</span></label
          ><input
            id="invite-name"
            v-model="name"
            autocomplete="name"
            maxlength="80"
        /></template>
        <template v-else
          ><label for="login-email">Email</label
          ><input
            id="login-email"
            v-model="email"
            type="email"
            autocomplete="username"
            required
        /></template>
        <label for="login-password">{{
          invite ? "Choose a password" : "Password"
        }}</label>
        <input
          id="login-password"
          v-model="password"
          type="password"
          :autocomplete="invite ? 'new-password' : 'current-password'"
          :minlength="invite ? 12 : 1"
          maxlength="1024"
          required
        />
        <small v-if="invite">Use at least 12 characters.</small>
        <button class="button primary" :disabled="busy">
          <LoaderCircle v-if="busy" class="spin" :size="17" />{{
            invite ? "Accept invitation" : "Sign in"
          }}<ArrowRight v-if="!busy" :size="17" />
        </button>
      </form>
      <div v-if="error" class="auth-error" role="alert">
        {{ error
        }}<button
          v-if="!Object.keys(configuration).length"
          class="button secondary"
          @click="load"
        >
          Retry
        </button>
      </div>
      <a
        v-if="configuration.sso_enabled && !invite"
        class="button secondary auth-sso"
        href="/api/auth/oidc/start"
        >Continue with {{ configuration.sso_name }}</a
      >
      <p class="auth-footnote">
        {{
          invite
            ? "Already have access?"
            : "Need access? Ask your administrator for an invitation."
        }}
        <button v-if="invite" @click="cancelInvite">Back to sign in</button>
      </p>
    </section>
    <div class="auth-install"><PwaControls /></div>
  </main>
  <div v-if="user && error" class="auth-floating-error" role="alert">
    {{ error }}
  </div>
</template>
