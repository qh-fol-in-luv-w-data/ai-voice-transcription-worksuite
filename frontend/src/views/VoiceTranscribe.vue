<script setup>
import { ref, computed } from 'vue'
import {
  audioFile, language, modelType, isTranscribing, transcribeStatus, transcriptResults,
  isCleaned, transcriptText, isExtracting, extractStatus, isCleaning,
  tasks, selectedAttendees, isReanalyzing, dict, uiLang,
  hrProjectsMap, dbEmployees, docxUrl, excelUrl, isTaskModalOpen
} from '../composables/useVoiceApp'

import { transcribeAudio, extractTasks, cleanTranscript, enrollMappedSpeakers, updateMeetingResults, checkMeetingStatus } from '../api'
import { currentMeetingName, originalTranscriptResults, loadHistory } from '../composables/useVoiceApp'

const t = (key) => dict[uiLang.value][key] || key
const transcribeProgress = ref(0)

// ── STRANGER MAPPING ─────────────────────────────────────────────────────────
const speakerMapping = ref({})
const isEnrollingMapped = ref(false)

const unknownSpeakers = computed(() => {
  const speakers = new Set()
  for (const seg of transcriptResults.value) {
    if (seg[2] && seg[2].includes('Người lạ')) {
      speakers.add(seg[2])
    }
  }
  return Array.from(speakers)
})

const employeeOptions = computed(() =>
  dbEmployees.value.map(emp => ({
    value: emp.employee_name + ' (' + emp.name + ')',
    label: emp.employee_name + ' (' + emp.name + ')' + (emp.user_id ? ' — ' + emp.user_id : '')
  }))
)

const enrollMapped = async () => {
  const validMappings = {}
  for (const [spk, name] of Object.entries(speakerMapping.value)) {
    if (name) validMappings[spk] = name
  }
  if (Object.keys(validMappings).length === 0) {
    alert('Chưa chọn tên cho người lạ nào!')
    return
  }
  isEnrollingMapped.value = true
  try {
    // Enroll trước khi đổi tên để backend còn tìm được segment theo tên cũ
    if (currentMeetingName.value) {
      const res = await enrollMappedSpeakers(currentMeetingName.value, validMappings)
      const enrolled = res?.enrolled || []
      const errors = res?.errors || []
      const skipped = res?.skipped || []
      let msg = `✅ Đã cập nhật tên.`
      if (enrolled.length) msg += ` Đăng ký giọng: ${enrolled.join(', ')}.`
      if (skipped.length) msg += ` Đã có sẵn: ${skipped.join(', ')}.`
      if (errors.length) msg += ` Lỗi: ${errors.join(', ')}.`
      alert(msg)
    } else {
      alert('✅ Đã cập nhật tên.')
    }
    // Đổi tên sau khi enroll xong
    for (const seg of transcriptResults.value) {
      if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]]
    }
    for (const seg of originalTranscriptResults.value) {
      if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]]
    }
    if (currentMeetingName.value) {
      await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
    }
    speakerMapping.value = {}
  } catch(e) {
    alert('❌ Lỗi: ' + e.message)
  } finally {
    isEnrollingMapped.value = false
  }
}

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
  transcribeProgress.value = 0
  transcribeStatus.value = t('status_transcribe_wait')
  transcriptResults.value = []
  originalTranscriptResults.value = []
  isCleaned.value = false
  transcriptText.value = ''
  tasks.value = []
  selectedAttendees.value = []
  
  try {
    const res = await transcribeAudio(audioFile.value, language.value)
    if (res.status === 'processing' && res.meeting_name) {
      currentMeetingName.value = res.meeting_name
      
      // Polling loop
      const pollTimer = setInterval(async () => {
        try {
          const pollRes = await checkMeetingStatus(currentMeetingName.value)
          if (pollRes.status === 'processing') {
            if (pollRes.progress_info) {
               transcribeProgress.value = pollRes.progress_info.progress || 0
               transcribeStatus.value = pollRes.progress_info.message || "Đang xử lý..."
            }
          } else if (pollRes.status === 'success') {
            clearInterval(pollTimer)
            transcribeProgress.value = 100
            transcribeStatus.value = t('status_transcribe_ok')
            transcriptResults.value = pollRes.results
            originalTranscriptResults.value = [...pollRes.results]
            isCleaned.value = false
            transcriptText.value = pollRes.final_text
            dbEmployees.value = pollRes.employees || []
            loadHistory()
            isTranscribing.value = false
          } else if (pollRes.status === 'error') {
            clearInterval(pollTimer)
            transcribeStatus.value = '❌ Error: ' + pollRes.message
            isTranscribing.value = false
          }
        } catch (err) {
          console.error("Polling error", err)
        }
      }, 3000)
    } else if (res.status === 'success') {
      transcribeStatus.value = t('status_transcribe_ok')
      transcriptResults.value = res.results
      originalTranscriptResults.value = [...res.results]
      isCleaned.value = false
      transcriptText.value = res.final_text
      dbEmployees.value = res.employees || []
      currentMeetingName.value = res.meeting_name || null
      if (res.meeting_name) loadHistory()
      isTranscribing.value = false
    } else {
      transcribeStatus.value = '❌ Error: ' + res.message
      isTranscribing.value = false
    }
  } catch (e) {
    transcribeStatus.value = t('error_connect')
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
    <div class="shadcn-card glow-effect border-border/50">
      <div class="card-header border-b border-border bg-muted/5">
        <h3 class="card-title text-xl flex items-center gap-2 font-semibold">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="text-foreground"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>
          {{ t('audio_processing') }}
        </h3>
        <p class="card-description">{{ t('audio_desc') }}</p>
      </div>
      <div class="card-content flex flex-col gap-6 p-8">
        <div class="flex items-center gap-4 p-8 border-2 border-dashed border-border rounded-xl bg-muted/5 hover:bg-muted/20 transition-colors relative overflow-hidden group">
            <div class="absolute inset-0 bg-gradient-to-r from-foreground/0 via-foreground/5 to-foreground/0 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-1000"></div>
            <input type="file" accept="audio/*" @change="handleFileChange" class="hidden" id="audio-upload" />
            <label for="audio-upload" class="shadcn-btn cursor-pointer shrink-0 shadow-sm border border-border hover:bg-foreground hover:text-background transition-colors">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
              {{ t('upload_empty') }}
            </label>
            <div class="flex flex-col min-w-0">
               <span class="text-sm font-semibold text-foreground truncate">
                 {{ audioFile ? audioFile.name : (t('no_file_selected') === 'no_file_selected' ? 'Chưa có file nào' : t('no_file_selected')) }}
               </span>
               <span class="text-xs text-muted-foreground">{{ t('upload_support') }}</span>
            </div>
        </div>

        <div class="flex items-center gap-4 flex-wrap">
           <div class="flex-1 min-w-[200px]">
              <label class="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">{{ t('target_lang') }}</label>
              <select v-model="language" class="shadcn-input w-full h-12 bg-muted/5 font-medium border-border/50 focus:border-foreground">
                 <option v-for="l in languages" :key="l.val" :value="l.val">{{ l.label }}</option>
              </select>
           </div>
           
           <div class="flex-1 min-w-[200px]">
              <label class="block text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">Model</label>
              <select v-model="modelType" class="shadcn-input w-full h-12 bg-muted/5 font-medium border-border/50 focus:border-foreground">
                 <option value="gpt-4o-mini">GPT-4o-mini</option>
                 <option value="gpt-4o">GPT-4o</option>
              </select>
           </div>
           
           <div class="flex-none self-end">
              <button @click="startTranscribe" :disabled="isTranscribing" class="shadcn-btn h-12 px-8 font-bold text-background bg-foreground shadow-lg hover:bg-foreground/90 transition-all">
                 <svg v-if="!isTranscribing" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><polygon points="5 3 19 12 5 21 5 3"></polygon></svg>
                 <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                 {{ isTranscribing ? t('analyzing') : t('analyze_voice') }}
              </button>
           </div>
        </div>

        <div v-if="transcribeStatus" 
             class="p-4 rounded-lg text-sm border font-medium flex flex-col gap-2 shadow-inner"
             :class="transcribeStatus.includes('❌') ? 'bg-destructive/10 text-destructive border-destructive/20' : (transcribeStatus.includes('⏳') || isTranscribing ? 'bg-muted text-foreground border-border' : 'bg-primary/10 text-primary border-primary/20')">
           <span>{{ transcribeStatus }}</span>
           <div v-if="isTranscribing" class="flex items-center gap-3 mt-1">
             <div class="flex-1 h-2 bg-foreground/10 rounded-full overflow-hidden">
               <div class="h-full bg-primary transition-all duration-500 ease-out" :style="{ width: transcribeProgress + '%' }"></div>
             </div>
             <span class="text-xs font-bold text-primary w-8 text-right">{{ transcribeProgress }}%</span>
           </div>
        </div>
      </div>
    </div>

    <!-- STRANGER MAPPING CARD -->
    <div v-if="unknownSpeakers.length > 0" class="shadcn-card" style="border-color: hsl(var(--primary)/0.5); border-width: 2px;">
      <div class="card-header border-b border-border bg-muted/5">
        <h3 class="card-title text-base font-semibold flex items-center gap-2">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="m19 11-2 2-2-2"/><path d="m15 15 2-2 2 2"/></svg>
          Gán tên người tham dự
        </h3>
        <p class="card-description">AI phát hiện giọng nói chưa xác định. Chọn tên nhân viên thực tế để gán vào biên bản và đăng ký vào hệ thống.</p>
      </div>
      <div class="card-content p-4 flex flex-col gap-3">
        <div v-for="spk in unknownSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-3 bg-background border border-border p-3 rounded-lg">
          <span class="font-bold text-sm min-w-[140px]">{{ spk }}</span>
          <el-select
            v-model="speakerMapping[spk]"
            filterable
            clearable
            allow-create
            default-first-option
            placeholder="Chọn nhân viên hoặc nhập tên..."
            style="flex: 1"
          >
            <el-option
              v-for="opt in employeeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="flex justify-end mt-1">
          <el-button type="primary" :loading="isEnrollingMapped" @click="enrollMapped">
            Cập nhật danh tính & Đăng ký giọng
          </el-button>
        </div>
      </div>
    </div>

    <!-- TRANSCRIPT CARD -->
    <div v-if="transcriptResults.length > 0" class="shadcn-card border-border/50">
      <div class="card-header border-b border-border bg-muted/5 flex justify-between items-center">
        <div>
          <h3 class="card-title font-semibold">{{ t('transcript_result') }}</h3>
          <p class="card-description">{{ t('transcript_desc') }}</p>
        </div>
        <div class="flex gap-2">
           <button @click="startCleanTranscript" :disabled="isCleaning" class="shadcn-btn shadcn-btn-outline" :class="isCleaned ? 'border-foreground text-foreground' : ''">
             <svg v-if="isCleaning" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
             <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path></svg>
             {{ isCleaning ? "Đang chuẩn hoá..." : (isCleaned ? "↩ Hoàn tác" : "✨ Chuẩn hoá hội thoại") }}
           </button>
           
           <button @click="openTaskModal" class="shadcn-btn bg-foreground text-background shadow-md shadow-foreground/20 hover:bg-foreground/90 transition-colors" :disabled="isExtracting">
             <svg v-if="isExtracting" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
             <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><polyline points="9 11 12 14 22 4"></polyline><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path></svg>
             {{ tasks.length > 0 ? "View Tasks" : t('extract_task') }}
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
