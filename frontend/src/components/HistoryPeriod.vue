<script setup>
import { computed } from "vue";
import SelectMenu from "./SelectMenu.vue";
const props = defineProps({
  modelValue: { type: String, default: "90" },
  period: Object,
});
const emit = defineEmits(["update:modelValue"]);
const options = [
  { value: "7", label: "Last week" },
  { value: "30", label: "Last month" },
  { value: "90", label: "Last 3 months" },
  { value: "180", label: "Last 6 months" },
  { value: "365", label: "Last year" },
  { value: "0", label: "All history" },
];
const dates = computed(() => {
  if (!props.period) return "";
  const format = (value) =>
    new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(value + "T12:00:00Z"));
  return `${format(props.period.start)} – ${format(props.period.end)}`;
});
</script>
<template>
  <div class="history-period">
    <label for="activity-history">Base highlights on</label>
    <SelectMenu
      id="activity-history"
      :model-value="modelValue"
      label="History period"
      :options="options"
      @update:model-value="emit('update:modelValue', $event)"
    />
    <span
      v-if="period"
      class="history-period-summary"
      :title="dates"
      role="status"
      >{{ period.ticket_count }}
      {{ period.ticket_count === 1 ? "ticket" : "tickets"
      }}<small>{{ dates }}</small></span
    >
  </div>
</template>
