<script setup>
import { ref } from "vue";
import { Play, Pause, Repeat2 } from "@lucide/vue";
defineProps({
  playing: Boolean,
  speed: { type: Number, default: 2000 },
  disabled: Boolean,
});
defineEmits(["toggle", "speed"]);
const optionsOpen = ref(false);
</script>

<template>
  <div class="timeline-playback" role="group" aria-label="Timeline playback">
    <button
      type="button"
      class="playback-toggle"
      :class="{ playing }"
      :disabled="disabled && !playing"
      :aria-label="
        playing ? 'Pause timeline playback' : 'Play timeline playback'
      "
      :aria-pressed="playing"
      @click="$emit('toggle')"
    >
      <Pause v-if="playing" :size="15" /><Play v-else :size="15" /><span>{{
        playing ? "Pause" : "Play"
      }}</span>
    </button>
    <button
      class="playback-more"
      :aria-expanded="optionsOpen"
      @click="optionsOpen = !optionsOpen"
    >
      Playback options
    </button>
    <div class="playback-options" :class="{ expanded: optionsOpen }">
      <div class="playback-speed" role="group" aria-label="Playback speed">
        <span>Every</span>
        <button
          v-for="interval in [1000, 2000]"
          :key="interval"
          type="button"
          :aria-label="`${interval / 1000} ${interval === 1000 ? 'second' : 'seconds'} per hour`"
          :aria-pressed="speed === interval"
          :class="{ chosen: speed === interval }"
          @click="$emit('speed', interval)"
        >
          {{ interval / 1000 }}s
        </button>
      </div>
      <span class="playback-loop"><Repeat2 :size="13" />Loops 24 hours</span>
    </div>
  </div>
</template>

<style>
.timeline-playback {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}
.playback-more {
  display: none;
}
.playback-options {
  display: flex;
  align-items: center;
  flex: 1;
  gap: 12px;
}
.playback-toggle {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 36px;
  padding: 7px 13px;
  background: #f1f5e8;
  color: #4b6839;
  border: 1px solid #dce6ce;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 550;
}
.playback-toggle.playing {
  background: #203d31;
  color: #fff;
  border-color: #203d31;
}
.playback-speed {
  display: flex;
  align-items: center;
  gap: 3px;
  color: #8b9880;
  font-size: 10px;
}
.playback-speed > span {
  margin-right: 3px;
}
.playback-speed button {
  min-height: 32px;
  min-width: 34px;
  padding: 5px 8px;
  color: #7e8d6f;
  border: 1px solid transparent;
  border-radius: 5px;
  font-size: 11px;
}
.playback-speed button.chosen {
  background: #f3f6ed;
  border-color: #dfe7d4;
  color: #526e3d;
  font-weight: 600;
}
.playback-loop {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  color: #97a18c;
  font-size: 9px;
}
@media (max-width: 740px), (max-width: 980px) and (max-height: 500px) {
  .playback-more {
    display: block;
    min-height: 44px;
    padding: 8px;
    font-size: 12px;
    color: #526a42;
    margin-left: auto;
  }
  .playback-options {
    display: none;
    flex-basis: 100%;
    flex-wrap: wrap;
    padding: 8px 0;
  }
  .playback-options.expanded {
    display: flex;
  }
  .timeline-playback {
    gap: 8px;
  }
  .playback-toggle,
  .playback-speed button {
    min-height: 44px;
  }
  .playback-speed button {
    min-width: 38px;
  }
  .playback-loop {
    font-size: 12px;
  }
  .playback-speed,
  .playback-toggle,
  .playback-speed button {
    font-size: 13px;
  }
}
</style>
