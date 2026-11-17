<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { Mail, Send, ExternalLink, RefreshCw, LoaderCircle } from "@lucide/vue";
import { api, dateTime } from "../api";
import SelectMenu from "./SelectMenu.vue";
const props = defineProps({ user: { type: Object, required: true } });
const form = ref(null),
  password = ref(""),
  clearPassword = ref(false),
  reportTime = ref("09:15"),
  recipient = ref(props.user.email);
const status = ref({ counts: {}, recent: [], missing_recipient_vehicles: 0 });
const busy = ref(false),
  error = ref(""),
  notice = ref(""),
  acknowledged = ref({});
let timer;
const securityOptions = [
  { value: "starttls", label: "STARTTLS · usually port 587" },
  { value: "tls", label: "TLS · usually port 465" },
  { value: "none", label: "Plain SMTP · loopback testing only" },
];
async function load(replace = false) {
  const result = await api("/admin/email");
  status.value = result;
  if (!form.value || replace) {
    form.value = result.configuration;
    reportTime.value = `${String(form.value.report_hour).padStart(2, "0")}:${String(form.value.report_minute).padStart(2, "0")}`;
  }
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
function save() {
  action(async () => {
    const [report_hour, report_minute] = reportTime.value
      .split(":")
      .map(Number);
    await api("/admin/email", {
      method: "PUT",
      body: {
        enabled: form.value.enabled,
        host: form.value.host,
        port: Number(form.value.port),
        security: form.value.security,
        username: form.value.username,
        password: clearPassword.value ? "" : password.value || null,
        from_email: form.value.from_email,
        from_name: form.value.from_name,
        reply_to: form.value.reply_to || null,
        ticket_alerts: form.value.ticket_alerts,
        monthly_reports: form.value.monthly_reports,
        report_day: Number(form.value.report_day),
        report_hour,
        report_minute,
      },
    });
    password.value = "";
    clearPassword.value = false;
    await load(true);
    notice.value =
      "Email settings saved. Future ticket checks will use these settings.";
  });
}
function test() {
  action(async () => {
    await api("/admin/email/test", {
      method: "POST",
      body: { recipient: recipient.value },
    });
    await load();
    notice.value =
      "Test email queued. The hourly-check worker sends queued emails within about a minute while it is running.";
  });
}
function retry(delivery) {
  action(async () => {
    await api(`/admin/email/deliveries/${delivery.id}/retry`, {
      method: "POST",
      body: { acknowledge_uncertain: Boolean(acknowledged.value[delivery.id]) },
    });
    await load();
    notice.value = "Delivery queued for retry.";
  });
}
function securityChanged(value) {
  const defaults = { starttls: 587, tls: 465, none: 1025 };
  if (form.value.port === defaults[form.value.security])
    form.value.port = defaults[value];
  form.value.security = value;
}
onMounted(async () => {
  await action(() => load());
  timer = setInterval(() => load().catch(() => {}), 15000);
});
onBeforeUnmount(() => clearInterval(timer));
</script>
<template>
  <section class="settings-card email-settings">
    <header>
      <Mail :size="22" />
      <div>
        <h2>Email notifications</h2>
        <p>
          A note for each new ticket and a monthly view of what’s still due.
          Recipients come from each vehicle’s optional email address.
        </p>
      </div>
      <span
        v-if="form"
        class="email-state"
        :class="{ enabled: status.configuration?.enabled }"
        >{{
          status.configuration?.enabled ? "Delivery enabled" : "Delivery off"
        }}</span
      >
    </header>
    <div v-if="status.configuration_error" class="auth-error" role="alert">
      {{ status.configuration_error }}
    </div>
    <div v-if="error" class="auth-error" role="alert">{{ error }}</div>
    <div v-if="notice" class="settings-notice" role="status">{{ notice }}</div>
    <p v-if="!form" role="status">Loading email settings…</p>
    <template v-else>
      <p
        v-if="!status.configuration?.enabled && status.counts.queued"
        class="settings-notice"
      >
        Delivery is off. Queued emails will wait until it’s enabled again.
      </p>
      <p v-if="form.managed_by_environment" class="settings-notice">
        SMTP is managed by deployment configuration. Connection settings are
        read-only here.
      </p>
      <div class="email-preview-actions">
        <a
          class="button secondary"
          href="/api/admin/email/preview?kind=new_ticket"
          target="_blank"
          rel="noopener"
          >Preview ticket email<ExternalLink :size="14" /></a
        ><a
          class="button secondary"
          href="/api/admin/email/preview?kind=monthly"
          target="_blank"
          rel="noopener"
          >Preview monthly report<ExternalLink :size="14"
        /></a>
      </div>
      <form class="settings-sso-form email-config-form" @submit.prevent="save">
        <label class="settings-check"
          ><input
            v-model="form.enabled"
            type="checkbox"
            :disabled="form.managed_by_environment"
          />Enable email delivery</label
        >
        <label
          >SMTP host<input
            v-model="form.host"
            :disabled="form.managed_by_environment"
            placeholder="smtp.example.com"
            autocomplete="off"
            :required="form.enabled"
            maxlength="253"
        /></label>
        <label
          >SMTP port<input
            v-model.number="form.port"
            :disabled="form.managed_by_environment"
            type="number"
            min="1"
            max="65535"
            required
        /></label>
        <label
          >Connection security<SelectMenu
            id="smtp-security"
            :model-value="form.security"
            label="SMTP connection security"
            :options="securityOptions"
            :disabled="form.managed_by_environment"
            @update:model-value="securityChanged"
        /></label>
        <label
          >Username (optional)<input
            v-model="form.username"
            :disabled="form.managed_by_environment"
            autocomplete="off"
            maxlength="300"
        /></label>
        <label
          >Password<input
            v-model="password"
            type="password"
            :disabled="form.managed_by_environment"
            autocomplete="new-password"
            :placeholder="
              form.has_password
                ? 'Configured · leave blank to keep'
                : 'Not configured'
            "
            maxlength="4000"
        /></label>
        <label
          >From email<input
            v-model="form.from_email"
            type="email"
            :disabled="form.managed_by_environment"
            placeholder="parking@example.com"
            :required="form.enabled"
        /></label>
        <label
          >From name<input
            v-model="form.from_name"
            :disabled="form.managed_by_environment"
            required
            maxlength="80"
        /></label>
        <label
          >Reply-to email (optional)<input
            v-model="form.reply_to"
            type="email"
            :disabled="form.managed_by_environment"
        /></label>
        <label
          v-if="form.has_password && !form.managed_by_environment"
          class="settings-check settings-wide"
          ><input v-model="clearPassword" type="checkbox" />Remove the saved
          SMTP password</label
        >
        <div class="email-policy settings-wide">
          <label class="settings-check"
            ><input
              v-model="form.ticket_alerts"
              type="checkbox"
              :disabled="form.managed_by_environment"
            />One email for each new ticket</label
          >
          <p>
            Starts with future ticket checks. Existing tickets, imports and a
            vehicle’s initial history won’t trigger a batch of alerts.
          </p>
          <label class="settings-check"
            ><input
              v-model="form.monthly_reports"
              type="checkbox"
              :disabled="form.managed_by_environment"
            />Monthly outstanding-ticket report</label
          >
          <p>
            One report per email address, combining that person’s vehicles.
            Includes every unpaid ticket’s balance, issue date and age. Sent
            only when something is outstanding.
          </p>
        </div>
        <template v-if="form.monthly_reports">
          <label
            >Day of month<input
              v-model.number="form.report_day"
              type="number"
              min="1"
              max="28"
              :disabled="form.managed_by_environment"
              required
            /><small>1–28, so the schedule works every month.</small></label
          >
          <label
            >Send at · {{ form.timezone
            }}<input
              v-model="reportTime"
              type="time"
              :disabled="form.managed_by_environment"
              required
            /><small
              >A missed current-month report is sent when the app
              resumes.</small
            ></label
          >
        </template>
        <p
          v-if="status.missing_recipient_vehicles"
          class="settings-wide email-recipient-note"
        >
          {{ status.missing_recipient_vehicles }}
          {{
            status.missing_recipient_vehicles === 1
              ? "vehicle has"
              : "vehicles have"
          }}
          no valid email address. Add one from Vehicles → Edit to receive alerts
          for that car.
        </p>
        <button
          v-if="!form.managed_by_environment"
          class="button primary"
          :disabled="busy"
        >
          <LoaderCircle v-if="busy" class="spin" :size="16" />Save email
          settings
        </button>
      </form>
      <form class="email-test-form" @submit.prevent="test">
        <label
          >Test recipient<input
            v-model="recipient"
            type="email"
            required
            autocomplete="off" /></label
        ><button
          class="button secondary"
          :disabled="busy || !status.configuration?.enabled"
        >
          <Send :size="16" />Send test email
        </button>
      </form>
      <div class="email-delivery-heading">
        <div>
          <h3>Recent deliveries</h3>
          <p>
            {{ status.counts.queued || 0 }} queued ·
            {{ status.counts.sent || 0 }} accepted by SMTP ·
            {{ (status.counts.failed || 0) + (status.counts.uncertain || 0) }}
            need attention
          </p>
        </div>
        <button
          class="icon-button"
          aria-label="Refresh email delivery status"
          :disabled="busy"
          @click="action(() => load())"
        >
          <RefreshCw :size="17" />
        </button>
      </div>
      <p v-if="!status.recent.length" class="data-note">
        No emails yet. Enable delivery and send a test to check your connection.
      </p>
      <div v-else class="email-delivery-list">
        <article v-for="delivery in status.recent" :key="delivery.id">
          <div>
            <strong>{{
              delivery.subject ||
              (delivery.kind === "monthly"
                ? "Monthly outstanding report"
                : delivery.kind === "test"
                  ? "Connection test"
                  : "New ticket alert")
            }}</strong><small
              >{{ delivery.recipient }} ·
              {{ dateTime(delivery.sent_at || delivery.created_at) }}</small
            >
            <p v-if="delivery.error">{{ delivery.error }}</p>
            <label v-if="delivery.status === 'uncertain'" class="settings-check"
              ><input v-model="acknowledged[delivery.id]" type="checkbox" />I
              checked the mailbox; resending may duplicate this email.</label
            >
          </div>
          <span class="email-delivery-state" :class="delivery.status">{{
            delivery.status === "sent"
              ? "SMTP accepted"
              : delivery.status === "uncertain"
                ? "Unconfirmed"
                : delivery.status
          }}</span>
          <button
            v-if="['failed', 'uncertain'].includes(delivery.status)"
            class="button secondary"
            :disabled="
              busy ||
              (delivery.status === 'uncertain' && !acknowledged[delivery.id])
            "
            @click="retry(delivery)"
          >
            Retry
          </button>
        </article>
      </div>
    </template>
  </section>
</template>
