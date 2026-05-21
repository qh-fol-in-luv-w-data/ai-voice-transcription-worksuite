<script setup>
import { ref } from 'vue'
import {
  audioFile, language, modelType, isTranscribing, transcribeStatus, transcriptResults,
  isCleaned, transcriptText, isExtracting, extractStatus, isCleaning,
  tasks, selectedAttendees, isReanalyzing, dict, uiLang, 
  hrProjectsMap, dbEmployees, docxUrl, excelUrl, isTaskModalOpen
} from '../composables/useVoiceApp'

import { transcribeAudio, extractTasks, cleanTranscript } from '../api'
import { currentMeetingName, originalTranscriptResults, loadHistory } from '../composables/useVoiceApp'

const t = (key) => dict[uiLang.value][key] || key

const languages = [
  { val: 'vi', label: 'Tiếng Việt' },
  { val: 'en', label: 'English' },
  { val: 'ja', label: '日本語' },
  { val: 'zh', label: '中文' },
  { val: 'ko', label: '한국어' },
  { val: 'auto', label: 'Auto detect' }
]

const handleFileChange = (e) => {
  if (e.target.files.length > 0) {
    audioFile.value = e.target.files[0]
  }
}

const startTranscribe = async () => {
  if (!audioFile.value) {
    alert(t('alert_no_file'))
    return
  }
  isTranscribing.value = true
  transcribeStatus.value = t('status_transcribe_wait')
  transcriptResults.value = []
  originalTranscriptResults.value = []
  isCleaned.value = false
  transcriptText.value = ''
  tasks.value = []
  selectedAttendees.value = []
  
  try {
    const res = await transcribeAudio(audioFile.value, language.value)
    if (res.status === 'success') {
      transcribeStatus.value = t('status_transcribe_ok')
      transcriptResults.value = res.results
      originalTranscriptResults.value = [...res.results]
      isCleaned.value = false
      transcriptText.value = res.final_text
      dbEmployees.value = res.employees || []
      currentMeetingName.value = res.meeting_name || null
      if (res.meeting_name) loadHistory()
    } else {
      transcribeStatus.value = '❌ Error: ' + res.message
    }
  } catch (e) {
    transcribeStatus.value = t('error_connect')
  } finally {
    isTranscribing.value = false
  }
}

const startCleanTranscript = async () => {
  if (isCleaned.value) {
    transcriptResults.value = [...originalTranscriptResults.value]
    isCleaned.value = false
    return
  }

  if (transcriptResults.value.length === 0) return
  isCleaning.value = true
  try {
    const res = await cleanTranscript(transcriptResults.value, modelType.value, currentMeetingName.value)
    if (res.status === 'success') {
      if (originalTranscriptResults.value.length === 0) {
        originalTranscriptResults.value = [...transcriptResults.value]
      }
      transcriptResults.value = res.cleaned_results
      isCleaned.value = true
    } else {
      alert('❌ Lỗi lọc: ' + res.message)
    }
  } catch (e) {
    alert(t('error_connect'))
  } finally {
    isCleaning.value = false
  }
}

const openTaskModal = async () => {
   if (tasks.value.length === 0 && transcriptResults.value.length > 0) {
      await startExtractTasks()
   }
   isTaskModalOpen.value = true
}

const startExtractTasks = async () => {
  if (transcriptResults.value.length === 0) {
    alert(t('alert_no_transcript'))
    return
  }
  isExtracting.value = true
  extractStatus.value = t('status_extract_wait')
  
  try {
    const res = await extractTasks(transcriptResults.value, modelType.value, currentMeetingName.value)
    if (res.status === 'success') {
      extractStatus.value = t('status_extract_ok')
      tasks.value = res.items
      hrProjectsMap.value = res.hr_projects_map || {}
      dbEmployees.value = res.employees || []
      docxUrl.value = res.docx_url
      excelUrl.value = res.excel_url
      loadHistory()
    } else {
      extractStatus.value = '❌ Error: ' + res.message
    }
  } catch (e) {
    extractStatus.value = t('error_connect')
  } finally {
    isExtracting.value = false
  }
}

</script>

<template>
  <div class="w-full flex flex-col gap-8 pb-10 mt-2 fade-in">
    <!-- UPLOAD CARD -->
    <div class="shadcn-card glow-effect border-primary/20">
      <div class="card-header border-b border-border bg-primary/5">
        <h3 class="card-title text-xl flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-primary"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>
          {{ t('audio_processing') }}
        </h3>
        <p class="card-description">{{ t('audio_desc') }}</p>
      </div>
      <div class="card-content flex flex-col gap-6 p-6">
        <div class="flex items-center gap-4 p-8 border-2 border-dashed border-primary/30 rounded-xl bg-primary/5 hover:bg-primary/10 transition-colors relative overflow-hidden group">
            <div class="absolute inset-0 bg-gradient-to-r from-primary/0 via-primary/5 to-primary/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000"></div>
            <input type="file" accept="audio/*" @change="handleFileChange" class="hidden" id="audio-upload" />
            <label for="audio-upload" class="shadcn-btn shadcn-btn-primary cursor-pointer shrink-0 shadow-lg shadow-primary/20">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
              {{ t('upload_empty') }}
            </label>
            <div class="flex flex-col min-w-0">
               <span class="text-sm font-semibold text-foreground truncate">
                 {{ audioFile ? audioFile.name : 'Chưa có file nào' }}
               </span>
               <span class="text-xs text-muted-foreground">{{ t('upload_support') }}</span>
            </div>
        </div>

        <div class="flex items-center gap-4 flex-wrap">
           <div class="flex-1 min-w-[200px]">
              <label class="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{{ t('target_lang') }}</label>
              <select v-model="language" class="shadcn-input w-full h-10 bg-background/50">
                 <option v-for="l in languages" :key="l.val" :value="l.val">{{ l.label }}</option>
              </select>
           </div>
           
           <div class="flex-1 min-w-[200px]">
              <label class="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Mô hình Phân tích</label>
              <select v-model="modelType" class="shadcn-input w-full h-10 bg-background/50">
                 <option value="gpt-4o-mini">GPT-4o-mini (Nhanh, rẻ)</option>
                 <option value="gpt-4o">GPT-4o (Thông minh nhất)</option>
              </select>
           </div>
           
           <div class="flex-none self-end">
              <button @click="startTranscribe" :disabled="isTranscribing" class="shadcn-btn shadcn-btn-primary h-10 px-8 shadow-lg shadow-primary/20">
                 <svg v-if="!isTranscribing" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                 <svg v-else xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                 {{ isTranscribing ? t('analyzing') : t('analyze_voice') }}
              </button>
           </div>
        </div>

        <div v-if="transcribeStatus" 
             class="p-4 rounded-lg text-sm border font-medium flex items-center shadow-inner"
             :class="transcribeStatus.includes('❌') ? 'bg-destructive/10 text-destructive border-destructive/20' : (transcribeStatus.includes('⏳') ? 'bg-muted text-foreground border-border' : 'bg-primary/10 text-primary border-primary/20')">
           {{ transcribeStatus }}
        </div>
      </div>
    </div>

    <!-- TRANSCRIPT CARD -->
    <div v-if="transcriptResults.length > 0" class="shadcn-card border-secondary/30">
      <div class="card-header border-b border-border bg-secondary/5 flex justify-between items-center">
        <div>
          <h3 class="card-title">{{ t('transcript_result') }}</h3>
          <p class="card-description">{{ t('transcript_desc') }}</p>
        </div>
        <div class="flex gap-2">
           <button @click="startCleanTranscript" :disabled="isCleaning" class="shadcn-btn shadcn-btn-outline" :class="isCleaned ? 'border-primary text-primary' : ''">
             <svg v-if="isCleaning" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
             <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
             {{ isCleaned ? "Hoàn tác (Hiển thị tất cả)" : "Lọc hội thoại rác" }}
           </button>
           
           <button @click="openTaskModal" class="shadcn-btn shadcn-btn-primary shadow-md shadow-primary/20" :disabled="isExtracting">
             <svg v-if="isExtracting" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
             <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
             {{ tasks.length > 0 ? "Xem Task" : t('extract_task') }}
           </button>
        </div>
      </div>
      <div class="card-content p-0">
         <div class="log-view p-6 space-y-6 max-h-[600px] overflow-auto relative">
            <div v-for="(seg, idx) in transcriptResults" :key="idx" class="log-entry group">
               <div class="log-meta">
                  <span class="log-speaker group-hover:text-primary transition-colors">{{ seg[2] }}</span>
                  <span class="log-time">[{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s]</span>
               </div>
               <p class="log-text">{{ seg[3] }}</p>
            </div>
         </div>
      </div>
    </div>
    
  </div>
</template>
