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

const numAttendees = ref(0) // 0 means auto
const vocabulary = ref('')
const meetingDate = ref(new Date().toLocaleString('vi-VN', { hour12: false }))
const meetingLocation = ref('')
const hostId = ref('')

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
    value: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - '),
    label: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ')
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

const audioUrl = computed(() => {
  return audioFile.value ? URL.createObjectURL(audioFile.value) : null
})

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
<div class="max-w-[1200px] mx-auto pb-xl pt-lg">
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
    
    <!-- LEFT COLUMN: Audio Analysis -->
    <div class="bg-surface-container/60 backdrop-blur-2xl border border-outline-variant/30 rounded-3xl p-6 shadow-2xl flex flex-col h-full">
      <h2 class="text-2xl font-bold text-on-surface mb-6 font-headline-md tracking-tight">Audio Analysis</h2>
      
      <!-- Dropzone -->
      <div class="relative border-2 border-dashed border-outline-variant/50 hover:bg-primary/5 hover:border-primary/50 rounded-2xl p-8 flex flex-col items-center justify-center cursor-pointer transition-all group flex-1 min-h-[250px]" :class="{ 'border-primary/50 bg-primary/5': audioFile }">
        <input type="file" accept="audio/*" @change="handleFileChange" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" />
        <div class="relative mb-6">
          <div class="absolute inset-0 bg-primary/20 blur-xl rounded-full scale-150 opacity-0 group-hover:opacity-100 transition-opacity"></div>
          <span class="material-symbols-outlined text-[80px] text-primary drop-shadow-[0_0_15px_rgba(192,193,255,0.3)] transition-transform group-hover:scale-110">cloud_upload</span>
          <div v-if="audioFile" class="absolute bottom-2 right-2 w-8 h-8 bg-surface rounded-full flex items-center justify-center shadow-lg border border-primary">
            <span class="material-symbols-outlined text-primary text-sm">play_arrow</span>
          </div>
        </div>
        
        <p class="font-body-md text-on-surface font-medium mb-4 text-center">Drag &amp; drop a file here, or click to select.</p>
        
        <div v-if="audioFile" class="flex items-center gap-2 bg-surface-container-highest/50 px-4 py-2 rounded-full border border-outline-variant/50 max-w-[90%] overflow-hidden">
           <span class="font-body-sm text-on-surface truncate">{{ audioFile.name }}</span>
           <span class="material-symbols-outlined text-[16px] text-on-surface-variant cursor-pointer hover:text-error" @click.stop.prevent="audioFile = null">close</span>
        </div>
      </div>

      <!-- Progress Bar -->
      <div v-if="isTranscribing || transcribeStatus" class="mt-6 space-y-3">
        <div class="h-4 bg-surface-container-highest rounded-full overflow-hidden relative shadow-inner border border-outline-variant/20">
          <div class="absolute inset-y-0 left-0 bg-gradient-to-r from-secondary to-primary transition-all duration-1000 rounded-full flex items-center justify-end pr-2" :style="{ width: transcribeProgress + '%' }">
             <div class="w-1.5 h-1.5 bg-white rounded-full shadow-[0_0_5px_white]"></div>
          </div>
        </div>
        <div class="flex justify-between items-center text-sm font-medium">
          <span class="text-primary">{{ transcribeProgress }}%</span>
          <span class="text-on-surface-variant flex items-center gap-2">
            <span class="material-symbols-outlined text-[16px] animate-spin">autorenew</span>
            {{ transcribeStatus || 'Preparing audio file for analysis...' }}
          </span>
        </div>
      </div>

      <!-- Audio Player -->
      <div v-if="audioUrl" class="mt-8 border-t border-outline-variant/30 pt-6">
        <div class="flex items-center gap-4 bg-surface-container-highest/30 rounded-2xl p-4 border border-outline-variant/20">
           <button class="w-12 h-12 rounded-full bg-gradient-to-br from-secondary to-primary flex items-center justify-center text-on-primary shadow-[0_0_15px_rgba(192,193,255,0.4)] hover:scale-105 transition-transform shrink-0">
              <span class="material-symbols-outlined">play_arrow</span>
           </button>
           <audio controls class="w-full h-10 custom-audio-player opacity-70 hover:opacity-100 transition-opacity" :src="audioUrl"></audio>
        </div>
      </div>
      
      <div class="mt-6 flex justify-center">
        <button @click="startTranscribe" :disabled="isTranscribing" class="w-full bg-gradient-to-r from-secondary/80 to-primary/80 hover:from-secondary hover:to-primary text-on-primary font-headline-md text-[18px] font-bold py-3.5 px-8 rounded-full shadow-lg transition-all hover:scale-[1.02] active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed flex justify-center items-center gap-3 border border-white/20">
          <span class="material-symbols-outlined text-[24px]" :class="{ 'animate-spin': isTranscribing }">{{ isTranscribing ? 'autorenew' : 'graphic_eq' }}</span>
          {{ isTranscribing ? t('analyzing') : t('analyze_voice') }}
        </button>
      </div>

    </div>

    <!-- RIGHT COLUMN: Meeting Details -->
    <div class="bg-surface-container/60 backdrop-blur-2xl border border-outline-variant/30 rounded-3xl p-6 shadow-2xl flex flex-col h-full space-y-6">
      <h2 class="text-2xl font-bold text-on-surface mb-2 font-headline-md tracking-tight">Meeting Details</h2>
      
      <!-- Language -->
      <div class="flex gap-4 items-start">
         <div class="w-12 h-12 rounded-2xl bg-error-container/30 flex items-center justify-center shrink-0 border border-error-container/50 shadow-sm">
            <span class="material-symbols-outlined text-error font-light text-[24px]">language</span>
         </div>
         <div class="flex-1">
            <label class="text-[13px] font-bold text-on-surface-variant mb-1 block">Language</label>
            <div class="relative">
               <select v-model="language" class="w-full bg-surface-container-highest/50 border border-outline-variant/40 rounded-xl px-4 py-3 text-body-md text-on-surface focus:outline-none focus:border-primary/70 transition-colors shadow-inner" style="-webkit-appearance: none; -moz-appearance: none; appearance: none;">
                  <option v-for="l in languages" :key="l.val" :value="l.val" class="bg-surface">{{ l.label }}</option>
               </select>
               <span class="material-symbols-outlined absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">keyboard_arrow_down</span>
            </div>
         </div>
      </div>

      <!-- Participants -->
      <div class="flex gap-4 items-start">
         <div class="w-12 h-12 rounded-2xl bg-secondary-container/30 flex items-center justify-center shrink-0 border border-secondary-container/50 shadow-sm">
            <span class="material-symbols-outlined text-secondary font-light text-[24px]">group</span>
         </div>
         <div class="flex-1">
            <label class="text-[13px] font-bold text-on-surface-variant mb-1 block">Participants</label>
            <input type="number" v-model="numAttendees" min="0" max="20" placeholder="0 = Tự động" class="w-full bg-surface-container-highest/50 border border-outline-variant/40 rounded-xl px-4 py-3 text-body-md text-on-surface focus:outline-none focus:border-primary/70 transition-colors shadow-inner">
         </div>
      </div>

      <!-- Keywords -->
      <div class="flex gap-4 items-start">
         <div class="w-12 h-12 rounded-2xl bg-tertiary-container/30 flex items-center justify-center shrink-0 border border-tertiary-container/50 shadow-sm">
            <span class="material-symbols-outlined text-tertiary font-light text-[24px]">format_list_bulleted</span>
         </div>
         <div class="flex-1">
            <label class="text-[13px] font-bold text-on-surface-variant mb-1 block">Keywords</label>
            <textarea v-model="vocabulary" class="w-full bg-surface-container-highest/50 border border-outline-variant/40 rounded-xl px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/40 focus:outline-none focus:border-primary/70 transition-colors shadow-inner resize-none min-h-[90px]" placeholder="Nhập từ khóa, tên dự án, thuật ngữ..." rows="2"></textarea>
         </div>
      </div>

      <!-- Meeting Info Header -->
      <div class="flex gap-4 items-center mt-2">
         <div class="w-12 h-12 rounded-2xl bg-primary-container/30 flex items-center justify-center shrink-0 border border-primary-container/50 shadow-sm">
            <span class="material-symbols-outlined text-primary font-light text-[24px]">event_note</span>
         </div>
         <h3 class="text-[15px] font-bold text-on-surface-variant uppercase tracking-wider">Meeting Info</h3>
      </div>
      
      <div class="pl-[64px] space-y-5 -mt-3">
         <!-- Date -->
         <div class="flex-1">
            <el-date-picker
               v-model="meetingDate"
               type="datetime"
               format="DD/MM/YYYY HH:mm"
               placeholder="08/07/2026 17:51"
               class="custom-el-date-premium w-full"
               style="width: 100%"
            />
         </div>
         
         <!-- Location -->
         <div class="flex-1">
            <label class="text-[12px] font-bold text-on-surface-variant/70 mb-1 block">Location</label>
            <input v-model="meetingLocation" class="w-full bg-surface-container-highest/30 border border-outline-variant/30 rounded-xl px-4 py-2.5 text-body-md text-on-surface placeholder:text-on-surface-variant/40 focus:outline-none focus:border-primary/70 transition-colors" placeholder="Nhập địa điểm..." type="text">
         </div>
         
         <!-- Host -->
         <div class="flex-1">
            <label class="text-[12px] font-bold text-on-surface-variant/70 mb-1 block">Host</label>
            <el-select
               v-model="hostId"
               filterable
               placeholder="Chọn người chủ trì..."
               class="custom-el-select-premium w-full"
            >
               <el-option
                  v-for="emp in dbEmployees"
                  :key="emp.user_id"
                  :label="[emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ')"
                  :value="emp.user_id"
               />
            </el-select>
         </div>
      </div>

    </div>
  </div>



<!-- STRANGER MAPPING CARD -->
<div v-if="unknownSpeakers.length > 0" class="bg-error-container/10 border border-error/20 rounded-xl p-lg shadow-sm">
  <div class="mb-lg border-b border-error/10 pb-md">
    <h3 class="font-headline-md text-headline-md text-error mb-xs flex items-center gap-sm">
      <span class="material-symbols-outlined">person_add</span>
      Gán tên người tham dự
    </h3>
    <p class="font-body-md text-body-md text-on-surface-variant">AI phát hiện giọng nói chưa xác định. Chọn tên nhân viên thực tế để gán vào biên bản và đăng ký vào hệ thống.</p>
  </div>
  <div class="flex flex-col gap-md">
    <div v-for="spk in unknownSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-md bg-surface border border-outline-variant/50 p-md rounded-lg shadow-sm hover:border-primary/50 transition-colors">
      <div class="flex items-center gap-sm min-w-[180px]">
        <div class="w-8 h-8 rounded-full bg-error/10 flex items-center justify-center text-error font-bold text-xs shrink-0">?</div>
        <span class="font-body-md text-body-md font-bold text-on-surface">{{ spk }}</span>
      </div>
      <el-select
        v-model="speakerMapping[spk]"
        filterable
        clearable
        allow-create
        default-first-option
        placeholder="Chọn nhân viên hoặc nhập tên..."
        style="flex: 1"
        class="custom-el-select-premium"
      >
        <el-option
          v-for="opt in employeeOptions"
          :key="opt.value"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
    </div>
    <div class="flex justify-end mt-sm">
      <button :disabled="isEnrollingMapped" @click="enrollMapped" class="bg-error hover:bg-error/90 text-on-error font-medium py-2.5 px-6 rounded-md shadow-sm transition-all disabled:opacity-50 flex items-center gap-sm">
        <span class="material-symbols-outlined text-[20px]">{{ isEnrollingMapped ? 'autorenew' : 'how_to_reg' }}</span>
        {{ isEnrollingMapped ? 'Đang xử lý...' : 'Cập nhật danh tính & Đăng ký giọng' }}
      </button>
    </div>
  </div>
</div>

<!-- TRANSCRIPT CARD -->
<div v-if="transcriptResults.length > 0" class="bg-surface-container border border-outline-variant rounded-xl p-lg md:p-xl shadow-sm flex flex-col h-[700px]">
  <div class="border-b border-outline-variant pb-md mb-md flex flex-col md:flex-row md:items-center justify-between gap-md shrink-0">
    <div>
      <h3 class="font-headline-md text-headline-md text-on-surface">{{ t('transcript_result') }}</h3>
      <p class="font-body-md text-body-md text-on-surface-variant mt-xs">{{ t('transcript_desc') }}</p>
    </div>
    <div class="flex flex-wrap gap-sm">
       <button @click="startCleanTranscript" :disabled="isCleaning" class="px-4 py-2 rounded-md font-medium flex items-center gap-sm border border-outline-variant hover:bg-surface-variant transition-colors text-body-sm" :class="isCleaned ? 'border-primary text-primary bg-primary/5' : 'text-on-surface'">
         <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isCleaning }">{{ isCleaning ? 'autorenew' : (isCleaned ? 'undo' : 'auto_fix_high') }}</span>
         {{ isCleaning ? "Đang chuẩn hoá..." : (isCleaned ? "Hoàn tác" : "Chuẩn hoá hội thoại") }}
       </button>
       
       <button @click="openTaskModal" class="px-4 py-2 bg-primary text-on-primary hover:bg-primary/90 rounded-md font-medium flex items-center gap-sm shadow-sm transition-colors text-body-sm" :disabled="isExtracting">
         <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isExtracting }">{{ isExtracting ? 'autorenew' : 'task_alt' }}</span>
         {{ tasks.length > 0 ? "Xem Task đã tạo" : t('extract_task') }}
       </button>
    </div>
  </div>
  
  <!-- Transcript Messages Area -->
  <div class="flex-1 overflow-y-auto space-y-md pr-sm rounded-lg relative scrollbar-premium">
    <div v-for="(seg, idx) in transcriptResults" :key="idx" class="flex flex-col gap-xs group hover:bg-surface-container-highest/30 p-md rounded-lg transition-colors border border-transparent hover:border-outline-variant/30">
       <div class="flex items-center gap-sm">
          <div class="flex items-center justify-center w-6 h-6 rounded-full bg-primary/20 text-primary font-label-caps text-[10px] tracking-wider font-bold shrink-0">
             {{ seg[2] ? seg[2].charAt(0).toUpperCase() : '?' }}
          </div>
          <span class="font-label-caps text-label-caps font-bold transition-colors" :class="seg[2].includes('Người lạ') ? 'text-error' : 'text-primary'">{{ seg[2] }}</span>
          <span class="font-label-caps text-[11px] text-on-surface-variant/60 bg-surface px-1.5 py-0.5 rounded border border-outline-variant/30">{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s</span>
       </div>
       <div class="pl-8">
          <p class="font-body-md text-body-md text-on-surface leading-relaxed">{{ seg[3] }}</p>
       </div>
    </div>
  </div>
</div>

</div>
</template>
