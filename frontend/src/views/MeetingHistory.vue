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
  <div v-if="meeting" class="w-full flex flex-col gap-8 pb-10 mt-2 fade-in">
    <!-- Meeting Info Card -->
    <div class="shadcn-card glow-effect">
      <div class="card-header border-b border-border bg-muted/10">
        <h3 class="card-title text-xl">{{ meeting.title }}</h3>
        <p class="card-description">Date: {{ meeting.date }} &middot; Status: {{ meeting.status }}</p>
      </div>
      
      <div class="card-content flex items-center gap-4 mt-4">
          <button v-if="meeting.audio_file" @click="downloadFile(meeting.audio_file, meeting.title + '.wav')" class="shadcn-btn shadcn-btn-outline h-10 hover:bg-primary hover:text-primary-foreground transition-colors">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
             {{ t('audio_processing') || 'Audio' }}
          </button>
          
          <button v-if="meeting.minute_docx" @click="downloadFile(meeting.minute_docx, meeting.title + '.docx')" class="shadcn-btn shadcn-btn-outline h-10 hover:bg-primary hover:text-primary-foreground transition-colors">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
             {{ t('export_docx') }}
          </button>
          
          <button v-if="meeting.task_xlsx" @click="downloadFile(meeting.task_xlsx, meeting.title + '.xlsx')" class="shadcn-btn shadcn-btn-outline h-10 hover:bg-primary hover:text-primary-foreground transition-colors">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
             {{ t('export_xlsx') }}
          </button>
      </div>
    </div>
    
    <!-- TRANSCRIPT -->
    <div v-if="parseSegments.length > 0" class="shadcn-card">
      <div class="card-header border-b border-border bg-muted/10">
        <h3 class="card-title">{{ t('transcript_result') }}</h3>
        <p class="card-description">{{ t('transcript_desc') }}</p>
      </div>
      <div class="card-content p-6">
        <div class="transcript-log max-h-[600px] overflow-auto flex flex-col gap-3 pr-1">
          <div v-for="(seg, idx) in parseSegments" :key="idx" class="log-entry">
            <div class="log-meta">
              <span class="log-speaker" :style="{ color: stringToColor(seg[2]) }">{{ seg[2] }}</span>
              <span class="log-time">[{{ formatTime(seg[0]) }}]</span>
            </div>
            <p class="log-text">{{ seg[3] }}</p>
          </div>
        </div>
      </div>
    </div>
    <div v-else-if="meeting.raw_results" class="shadcn-card">
      <div class="card-header border-b border-border bg-muted/10">
        <h3 class="card-title">{{ t('transcript_result') }}</h3>
        <p class="card-description">{{ t('transcript_desc') }}</p>
      </div>
      <div class="card-content p-6">
        <pre class="whitespace-pre-wrap font-mono text-sm bg-muted/20 p-4 rounded-lg overflow-auto border border-border max-h-[600px]">{{ meeting.raw_results }}</pre>
      </div>
    </div>
    <div v-else-if="meeting.transcript" class="shadcn-card">
       <div class="card-header border-b border-border bg-muted/10">
         <h3 class="card-title">{{ t('transcript_result') }}</h3>
       </div>
       <div class="card-content p-6">
          <pre class="whitespace-pre-wrap font-sans text-sm max-h-[600px] overflow-auto">{{ meeting.transcript }}</pre>
       </div>
    </div>
  </div>
  <div v-else class="flex h-full items-center justify-center text-muted-foreground font-medium text-lg">
     Select a meeting from the sidebar to view details.
  </div>
</template>

<style scoped>
.log-entry {
  border-left: 2px solid hsl(var(--border));
  padding-left: 1rem;
  position: relative;
}
.log-entry::before {
  content: "";
  position: absolute;
  left: -5px;
  top: 0.5rem;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: hsl(var(--ring));
}
.log-meta {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 0.25rem;
}
.log-speaker {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.05em;
}
.log-time {
  font-size: 0.75rem;
  color: hsl(var(--muted-foreground));
}
.log-text {
  font-size: 0.875rem;
  line-height: 1.5;
  margin: 0;
  color: hsl(var(--foreground));
  word-break: break-word;
  white-space: pre-wrap;
}
.transcript-log::-webkit-scrollbar {
  width: 6px;
}
.transcript-log::-webkit-scrollbar-track {
  background: transparent;
}
.transcript-log::-webkit-scrollbar-thumb {
  background: hsl(var(--border));
  border-radius: 3px;
}
</style>
