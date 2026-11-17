<script setup>
import {
  ref,
  computed,
  nextTick,
  onMounted,
  onBeforeUnmount,
  watch,
} from "vue";
import { ChevronDown, Check } from "@lucide/vue";

const props = defineProps({
  id: { type: String, required: true },
  label: { type: String, required: true },
  modelValue: { type: String, default: "" },
  options: { type: Array, required: true },
  disabled: Boolean,
});
const emit = defineEmits(["update:modelValue"]);
const trigger = ref(null),
  popup = ref(null),
  open = ref(false),
  active = ref(0),
  position = ref({});
const selected = computed(() =>
  props.options.find((option) => option.value === props.modelValue),
);
let typed = "",
  typedAt = 0;
function close() {
  open.value = false;
}
function revealActive() {
  nextTick(() =>
    popup.value
      ?.querySelector(`[data-index="${active.value}"]`)
      ?.scrollIntoView({ block: "nearest" }),
  );
}
function show() {
  if (props.disabled || !props.options.length) return;
  typed = "";
  typedAt = 0;
  const rect = trigger.value.getBoundingClientRect();
  const width = Math.min(Math.max(rect.width, 180), window.innerWidth - 16);
  const needed = Math.min(320, props.options.length * 42 + 12);
  const below = window.innerHeight - rect.bottom - 12,
    above = rect.top - 12;
  const up = below < needed && above > below;
  const height = Math.min(needed, Math.max(80, up ? above : below));
  position.value = {
    width: `${width}px`,
    maxHeight: `${height}px`,
    left: `${Math.max(8, Math.min(rect.left, window.innerWidth - width - 8))}px`,
    top: `${up ? Math.max(8, rect.top - height - 5) : rect.bottom + 5}px`,
  };
  active.value = Math.max(
    0,
    props.options.findIndex((option) => option.value === props.modelValue),
  );
  open.value = true;
  revealActive();
}
function choose(index) {
  emit("update:modelValue", props.options[index].value);
  close();
  trigger.value?.focus({ preventScroll: true });
}
function keyboard(event) {
  if (event.key === "Escape" && open.value) {
    event.preventDefault();
    event.stopPropagation();
    close();
    return;
  }
  if (event.key === "Tab") {
    close();
    return;
  }
  if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
    event.preventDefault();
    event.stopPropagation();
    if (!open.value) {
      show();
      return;
    }
    active.value =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? props.options.length - 1
          : (active.value +
              (event.key === "ArrowDown" ? 1 : -1) +
              props.options.length) %
            props.options.length;
    revealActive();
  } else if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    event.stopPropagation();
    if (open.value) choose(active.value);
    else show();
  } else if (
    event.key.length === 1 &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey
  ) {
    event.preventDefault();
    event.stopPropagation();
    if (!open.value) show();
    const current = Date.now();
    typed =
      current - typedAt < 700
        ? typed + event.key.toLowerCase()
        : event.key.toLowerCase();
    typedAt = current;
    const match = props.options.findIndex(
      (option) =>
        option.label.toLowerCase().startsWith(typed) ||
        option.value.toLowerCase().startsWith(typed),
    );
    if (match >= 0) {
      active.value = match;
      revealActive();
    }
  }
}
function outside(event) {
  if (
    open.value &&
    !trigger.value?.contains(event.target) &&
    !popup.value?.contains(event.target)
  )
    close();
}
function scrolled(event) {
  if (open.value && !popup.value?.contains(event.target)) close();
}
watch(
  () => props.disabled,
  (value) => {
    if (value) close();
  },
);
onMounted(() => {
  document.addEventListener("pointerdown", outside, true);
  document.addEventListener("scroll", scrolled, true);
  window.addEventListener("resize", close);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", outside, true);
  document.removeEventListener("scroll", scrolled, true);
  window.removeEventListener("resize", close);
});
</script>

<template>
  <button
    :id="id"
    ref="trigger"
    type="button"
    class="select-trigger"
    role="combobox"
    :aria-label="label"
    aria-haspopup="listbox"
    :aria-expanded="open"
    :aria-controls="`${id}-options`"
    :aria-activedescendant="open ? `${id}-option-${active}` : undefined"
    :disabled="disabled"
    @click="open ? close() : show()"
    @keydown="keyboard"
  >
    <span>{{ selected?.label || "Not set" }}</span><ChevronDown :size="16" />
  </button>
  <Teleport to="body">
    <div
      v-if="open"
      :id="`${id}-options`"
      ref="popup"
      class="select-options"
      role="listbox"
      :aria-label="label"
      :style="position"
      @mousedown.prevent
    >
      <div
        v-for="(option, index) in options"
        :id="`${id}-option-${index}`"
        :key="option.value"
        :data-index="index"
        class="select-option"
        :class="{ highlighted: active === index }"
        role="option"
        :aria-selected="modelValue === option.value"
        @pointermove="active = index"
        @click="choose(index)"
      >
        <span>{{ option.label }}</span><Check
          v-if="modelValue === option.value"
          :size="16"
        />
      </div>
    </div>
  </Teleport>
</template>

<style>
.select-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-width: 0;
  padding: 12px 14px;
  border: 1px solid #dbe3d0;
  border-radius: 7px;
  background: #fff;
  color: #617c47;
  text-align: left;
  font-size: 13px;
  line-height: 1.5;
}
.select-trigger > span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.select-trigger > svg {
  flex-shrink: 0;
}
.select-trigger[aria-expanded="true"] {
  outline: 2px solid #a5bd85;
  outline-offset: 1px;
}
.select-options {
  position: fixed;
  z-index: 10000;
  padding: 5px;
  overflow-y: auto;
  overscroll-behavior: contain;
  border: 1px solid #ccd8bf;
  border-radius: 9px;
  background: #fff;
  color: #526b3d;
  box-shadow: 0 12px 36px #182a2238;
  box-sizing: border-box;
}
.select-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 40px;
  padding: 9px 12px;
  border-radius: 5px;
  font-size: 13px;
  line-height: 1.5;
  cursor: pointer;
}
.select-option.highlighted {
  background: #edf4df;
}
.select-option[aria-selected="true"] {
  color: #28472f;
  font-weight: 550;
}
.select-option > svg {
  flex-shrink: 0;
}
@media (max-width: 740px) {
  .select-trigger,
  .select-option {
    min-height: 44px;
  }
}
</style>
