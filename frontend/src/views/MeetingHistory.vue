<script setup>
import { defineProps, computed } from 'vue'

const props = defineProps({
  meeting: Object,
  t: Function
})

const stringToColor = (str) => {
  if (!str) return '#888888';
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
}

const parseSegments = computed(() => {
  const raw = props.meeting?.raw_results;
  if (!raw) return [];
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch (e) {
    return [];
  }
})

const formatTime = (seconds) => {
  if (seconds == null) return '0.00s';
  return (typeof seconds === 'number' ? seconds : parseFloat(seconds)).toFixed(2) + 's';
}

const downloadFile = (url, defaultName) => {
  if (!url) return;

  // Use window.open as fallback for better cross-origin download support
  window.open(url, '_blank');
}
</script>

<template>
  <div v-if="meeting" class="flex-1 w-full max-w-5xl mx-auto space-y-xl pb-10 mt-2 fade-in">
    <!-- Header Section -->
    <section class="flex flex-col gap-md">
      <div>
        <h2 class="font-headline-lg text-headline-lg text-on-surface">{{ meeting.title }}</h2>
        <div class="flex items-center gap-2 mt-2 text-body-sm text-on-surface-variant font-body-sm">
          <span>{{ meeting.date }}</span>
          <span>•</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-primary inline-block"></span> {{ meeting.status || 'Analyzed' }}</span>
        </div>
      </div>
      <div class="flex flex-wrap gap-3 mt-sm">
        <button v-if="meeting.audio_file" @click="downloadFile(meeting.audio_file, meeting.title + '.wav')" class="flex items-center gap-2 px-4 py-2 bg-surface-container border border-outline-variant rounded-lg text-tertiary hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[18px]">volume_up</span> Tải Audio
        </button>
        <button v-if="meeting.minute_docx" @click="downloadFile(meeting.minute_docx, meeting.title + '.docx')" class="flex items-center gap-2 px-4 py-2 bg-surface-container border border-outline-variant rounded-lg text-secondary hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[18px]">description</span> Tải Biên bản (Word)
        </button>
        <button v-if="meeting.task_xlsx" @click="downloadFile(meeting.task_xlsx, meeting.title + '.xlsx')" class="flex items-center gap-2 px-4 py-2 bg-surface-container border border-outline-variant rounded-lg text-primary hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[18px]">download</span> Tải Tasks (Excel)
        </button>
      </div>
    </section>

    <!-- Transcript Section (Adapted from the box style) -->
    <section v-if="parseSegments.length > 0" class="bg-surface-container rounded-xl border border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-outline-variant bg-surface-container-low flex justify-between items-center">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> {{ t('transcript_result') }}
          </h3>
          <p class="text-body-sm text-on-surface-variant mt-1">{{ t('transcript_desc') }}</p>
        </div>
      </div>
      <div class="p-lg bg-surface">
        <div class="transcript-log max-h-[600px] overflow-auto flex flex-col gap-4 pr-2">
          <div v-for="(seg, idx) in parseSegments" :key="idx" class="relative border-l-2 border-outline-variant pl-4 py-1">
            <div class="absolute -left-[5px] top-3 w-2 h-2 rounded-full bg-primary/50"></div>
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-sm tracking-wide" :style="{ color: stringToColor(seg[2]) }">{{ seg[2] }}</span>
              <span class="text-xs text-on-surface-variant font-label-caps">[{{ formatTime(seg[0]) }}]</span>
            </div>
            <p class="text-sm leading-relaxed text-on-surface whitespace-pre-wrap break-words m-0">{{ seg[3] }}</p>
          </div>
        </div>
      </div>
    </section>
    
    <section v-else-if="meeting.raw_results" class="bg-surface-container rounded-xl border border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-outline-variant bg-surface-container-low flex justify-between items-center">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> {{ t('transcript_result') }}
          </h3>
          <p class="text-body-sm text-on-surface-variant mt-1">{{ t('transcript_desc') }}</p>
        </div>
      </div>
      <div class="p-lg bg-surface">
        <pre class="whitespace-pre-wrap font-label-caps text-sm bg-surface-container-high p-4 rounded-lg overflow-auto border border-outline-variant max-h-[600px] text-on-surface">{{ meeting.raw_results }}</pre>
      </div>
    </section>
    
    <section v-else-if="meeting.transcript" class="bg-surface-container rounded-xl border border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-outline-variant bg-surface-container-low flex justify-between items-center">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> {{ t('transcript_result') }}
          </h3>
        </div>
      </div>
      <div class="p-lg bg-surface">
        <pre class="whitespace-pre-wrap font-body-sm text-sm max-h-[600px] overflow-auto text-on-surface">{{ meeting.transcript }}</pre>
      </div>
    </section>
  </div>
  <div v-else class="flex h-full items-center justify-center text-on-surface-variant font-medium text-lg min-h-[400px]">
     Chọn một cuộc họp từ Sidebar để xem chi tiết.
  </div>
</template>

<style scoped>
.transcript-log::-webkit-scrollbar {
  width: 6px;
}
.transcript-log::-webkit-scrollbar-track {
  background: transparent;
}
.transcript-log::-webkit-scrollbar-thumb {
  background: #464554;
  border-radius: 3px;
}
.transcript-log::-webkit-scrollbar-thumb:hover {
  background: #908fa0;
}
</style>
