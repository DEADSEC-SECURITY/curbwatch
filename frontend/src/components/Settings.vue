<script setup>
import { ref, onMounted } from "vue";
import {
  UserPlus,
  Copy,
  ShieldCheck,
  KeyRound,
  LoaderCircle,
  LogOut,
} from "@lucide/vue";
import { api, dateTime } from "../api";
import EmailSettings from "./EmailSettings.vue";
import SelectMenu from "./SelectMenu.vue";
const props = defineProps({ user: { type: Object, required: true } });
const emit = defineEmits(["session", "logout"]);
const users = ref([]),
  sso = ref(null),
  busy = ref(false),
  error = ref(""),
  notice = ref(""),
  invitation = ref(null),
  copied = ref(false);
const email = ref(""),
  name = ref(""),
  role = ref("member"),
  secret = ref("");
const currentPassword = ref(""),
  newPassword = ref("");
const roleOptions = [
  { value: "member", label: "Member" },
  { value: "admin", label: "Administrator" },
];
const methodOptions = [
  { value: "client_secret_basic", label: "Client secret: Basic" },
  { value: "client_secret_post", label: "Client secret: POST" },
  { value: "none", label: "Public client (PKCE)" },
];
async function load() {
  if (props.user.role !== "admin") return;
  [users.value, sso.value] = await Promise.all([
    api("/admin/users"),
    api("/admin/sso"),
  ]);
}
async function action(operation) {
  busy.value = true;
  error.value = "";
  notice.value = "";
  try {
    await operation();
  } catch (failure) {
    error.value = failure.message;
  } finally {
    busy.value = false;
  }
}
function addUser() {
  action(async () => {
    const added = await api("/admin/users", {
      method: "POST",
      body: { email: email.value, name: name.value, role: role.value },
    });
    invitation.value = { ...added.invitation, email: added.user.email };
    copied.value = false;
    email.value = "";
    name.value = "";
    role.value = "member";
    await load();
  });
}
function inviteUser(user) {
  action(async () => {
    invitation.value = {
      ...(await api(`/admin/users/${user.id}/invite`, {
        method: "POST",
        body: {},
      })),
      email: user.email,
    };
    copied.value = false;
  });
}
function updateUser(user, changes) {
  action(async () => {
    await api(`/admin/users/${user.id}`, { method: "PATCH", body: changes });
    await load();
    notice.value =
      "Access updated. Existing sessions for this account have ended.";
  });
}
async function copyInvite() {
  try {
    await navigator.clipboard.writeText(invitation.value.url);
    copied.value = true;
  } catch {
    error.value =
      "Select the invitation address and copy it using your browser.";
  }
}
function saveSso() {
  action(async () => {
    sso.value = await api("/admin/sso", {
      method: "PUT",
      body: {
        enabled: sso.value.enabled,
        name: sso.value.name,
        issuer: sso.value.issuer,
        discovery_url: sso.value.discovery_url,
        client_id: sso.value.client_id,
        client_secret: secret.value || null,
        token_endpoint_auth_method: sso.value.token_endpoint_auth_method,
      },
    });
    secret.value = "";
    notice.value =
      "SSO settings saved. Test sign-in in another browser before ending this admin session.";
  });
}
function changePassword() {
  action(async () => {
    const session = await api("/auth/password", {
      method: "POST",
      body: {
        current_password: currentPassword.value,
        new_password: newPassword.value,
      },
    });
    emit("session", session);
    currentPassword.value = "";
    newPassword.value = "";
    notice.value = "Password updated. Other sessions have ended.";
  });
}
onMounted(() => action(load));
</script>
<template>
  <div class="settings-page">
    <div v-if="error" class="auth-error" role="alert">{{ error }}</div>
    <div v-if="notice" class="settings-notice" role="status">{{ notice }}</div>
    <template v-if="user.role === 'admin'">
      <EmailSettings :user="user" />
      <section class="settings-card">
        <header>
          <UserPlus :size="22" />
          <div>
            <h2>People & access</h2>
            <p>
              Only people you add can sign in. Everyone has access to this
              garage; administrators also manage access and sharing.
            </p>
          </div>
        </header>
        <form class="settings-invite-form" @submit.prevent="addUser">
          <label
            >Email<input
              v-model="email"
              type="email"
              autocomplete="off"
              required
              maxlength="254"
          /></label>
          <label
            >Name (optional)<input
              v-model="name"
              maxlength="80"
              autocomplete="off"
          /></label>
          <label
            >Role<SelectMenu
              id="new-user-role"
              v-model="role"
              label="New user role"
              :options="roleOptions"
              :disabled="busy"
          /></label>
          <button class="button primary" :disabled="busy">
            <UserPlus :size="17" />Add & invite
          </button>
        </form>
        <div v-if="invitation" class="settings-invitation" role="status">
          <strong>Invitation for {{ invitation.email }}</strong>
          <p>
            Expires {{ dateTime(new Date(invitation.expires_at * 1000)) }}.
            Share this link privately; it is shown once and can be used once.
          </p>
          <div>
            <input
              aria-label="Invitation link"
              :value="invitation.url"
              readonly
              @focus="$event.target.select()"
            /><button class="button primary" @click="copyInvite">
              <Copy :size="16" />{{ copied ? "Copied" : "Copy invitation" }}
            </button>
          </div>
          <small
            >Copy and send this link privately. Invitations aren’t emailed
            automatically. A verified SSO email can also activate this
            account.</small
          >
        </div>
        <div class="settings-users">
          <article v-for="person in users" :key="person.id">
            <div>
              <strong
                >{{ person.name || person.email }}
                <span v-if="person.id === user.id">(you)</span></strong
              ><small>{{ person.email }} · {{ person.status }}</small>
            </div>
            <SelectMenu
              :id="`user-role-${person.id}`"
              :model-value="person.role"
              :label="`Role for ${person.email}`"
              :options="roleOptions"
              :disabled="busy || person.id === user.id"
              @update:model-value="updateUser(person, { role: $event })"
            />
            <button
              v-if="person.status !== 'disabled' && person.id !== user.id"
              class="button secondary"
              :disabled="busy"
              @click="inviteUser(person)"
            >
              New invitation
            </button>
            <button
              v-if="person.id !== user.id"
              class="button secondary"
              :disabled="busy"
              @click="
                updateUser(person, {
                  status: person.status === 'disabled' ? 'active' : 'disabled',
                })
              "
            >
              {{ person.status === "disabled" ? "Enable" : "Disable" }}
            </button>
          </article>
        </div>
      </section>
      <section v-if="sso" class="settings-card">
        <header>
          <ShieldCheck :size="22" />
          <div>
            <h2>Single sign-on</h2>
            <p>
              Connect Authentik or another OpenID Connect provider. An admin
              must add each user’s verified email first.
            </p>
          </div>
        </header>
        <p v-if="sso.managed_by_environment" class="settings-notice">
          Managed by deployment configuration. These settings are read-only
          here.
        </p>
        <form class="settings-sso-form" @submit.prevent="saveSso">
          <label class="settings-check"
            ><input
              v-model="sso.enabled"
              type="checkbox"
              :disabled="sso.managed_by_environment"
            />Enable SSO</label
          >
          <label
            >Button label<input
              v-model="sso.name"
              maxlength="80"
              :disabled="sso.managed_by_environment"
              required
              placeholder="Authentik"
          /></label>
          <label
            >Issuer URL<input
              v-model="sso.issuer"
              type="url"
              :disabled="sso.managed_by_environment"
              placeholder="https://auth.example.com/application/o/curbwatch/"
              :required="sso.enabled"
          /></label>
          <label
            >Discovery URL<input
              v-model="sso.discovery_url"
              type="url"
              :disabled="sso.managed_by_environment"
              placeholder="Issuer + /.well-known/openid-configuration"
          /></label>
          <label
            >Client ID<input
              v-model="sso.client_id"
              :disabled="sso.managed_by_environment"
              autocomplete="off"
              :required="sso.enabled"
          /></label>
          <label
            >Client secret<input
              v-model="secret"
              type="password"
              :disabled="sso.managed_by_environment"
              autocomplete="new-password"
              :placeholder="
                sso.has_client_secret
                  ? 'Configured · leave blank to keep'
                  : 'Not configured'
              "
          /></label>
          <label
            >Client authentication<SelectMenu
              id="sso-client-auth"
              v-model="sso.token_endpoint_auth_method"
              label="Client authentication method"
              :options="methodOptions"
              :disabled="sso.managed_by_environment"
          /></label>
          <label class="settings-wide"
            >Callback URL<input
              :value="sso.callback_url"
              readonly
              @focus="$event.target.select()"
            /><small
              >Register this exact address with your provider. Set
              PARKING_BASE_URL when deploying.</small
            ></label
          >
          <p class="settings-wide data-note">
            Use a provider that verifies email addresses. Authentik requires an
            email verification mapping. See docs/authentication.md for setup and
            recovery.
          </p>
          <button
            v-if="!sso.managed_by_environment"
            class="button primary"
            :disabled="busy"
          >
            <LoaderCircle v-if="busy" class="spin" :size="16" />Save SSO
            settings
          </button>
        </form>
      </section>
    </template>
    <section class="settings-card">
      <header>
        <KeyRound :size="22" />
        <div>
          <h2>Your password</h2>
          <p>
            Signed in as {{ user.email }} ·
            {{ user.role === "admin" ? "Administrator" : "Member" }}. SSO-only
            accounts can use an admin invitation to set a local password.
          </p>
        </div>
      </header>
      <button class="button secondary settings-signout" @click="emit('logout')">
        <LogOut :size="16" />Sign out of Curbwatch
      </button>
      <form class="settings-password-form" @submit.prevent="changePassword">
        <label
          >Current password<input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            required
            maxlength="1024"
        /></label>
        <label
          >New password<input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            required
            minlength="12"
            maxlength="1024"
          /><small>At least 12 characters.</small></label
        >
        <button class="button primary" :disabled="busy">Update password</button>
      </form>
    </section>
  </div>
</template>
