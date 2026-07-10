<script setup>
import { ref, computed } from 'vue'
import {
  audioFile, language, modelType, isTranscribing, transcribeStatus, transcriptResults,
  isCleaned, transcriptText, isExtracting, extractStatus, isCleaning,
  tasks, selectedAttendees, isReanalyzing, dict, uiLang,
  hrProjectsMap, dbEmployees, docxUrl, excelUrl, isTaskModalOpen
} from '../composables/useVoiceApp'

import { transcribeAudio, extractTasks, cleanTranscript, enrollMappedSpeakers, updateMeetingResults, checkMeetingStatus, checkExtractStatus } from '../api'
import { currentMeetingName, originalTranscriptResults, loadHistory } from '../composables/useVoiceApp'

const t = (key) => dict[uiLang.value][key] || key
const transcribeProgress = ref(0)

const numAttendees = ref(0)
const vocabulary = ref('')
const meetingDate = ref(new Date().toLocaleString('vi-VN', { hour12: false }))
const meetingLocation = ref('')
const hostId = ref('')

// ── ADMIN CHECK ────────────────────────────────────────────────────────────
const isAdmin = computed(() => {
  try {
    const roles = window.frappe?.boot?.user?.roles || []
    return roles.includes('System Manager') || roles.includes('Administrator')
  } catch { return false }
})

// ── STRANGER MAPPING ─────────────────────────────────────────────────────────
const speakerMapping = ref({})
const isEnrollingMapped = ref(false)
const hasSelectedMapping = computed(() => {
  return Object.values(speakerMapping.value).some(val => !!val)
})

// ── INLINE TRANSCRIPT EDIT ───────────────────────────────────────────────────
const editingIdx = ref(null)
const editingText = ref('')
const editingSpeaker = ref(null)
const editingSpeakerName = ref('')
const newSpeakerEmployee = ref('')

const startEditText = (idx) => {
  editingIdx.value = idx
  editingText.value = transcriptResults.value[idx][3]
}

const saveEditText = async (idx) => {
  if (editingIdx.value !== idx) return
  transcriptResults.value[idx][3] = editingText.value
  editingIdx.value = null
  if (currentMeetingName.value) {
    await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
  }
}

const startEditSpeaker = (idx) => {
  editingSpeaker.value = idx
  editingSpeakerName.value = transcriptResults.value[idx][2]
  newSpeakerEmployee.value = ''
}

const saveEditSpeaker = async (idx) => {
  const finalName = newSpeakerEmployee.value

  if (!finalName.trim()) { editingSpeaker.value = null; return }
  const oldName = transcriptResults.value[idx][2]
  for (const seg of transcriptResults.value) {
    if (seg[2] === oldName) seg[2] = finalName.trim()
  }
  for (const seg of originalTranscriptResults.value) {
    if (seg[2] === oldName) seg[2] = finalName.trim()
  }
  editingSpeaker.value = null
  if (currentMeetingName.value) {
    await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
  }
}

const addNewSegment = async () => {
  const newSeg = [0, 0, 'Người lạ (mới)', '']
  transcriptResults.value.push(newSeg)
  originalTranscriptResults.value.push([...newSeg])
  editingIdx.value = transcriptResults.value.length - 1
  if (currentMeetingName.value) {
    await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
  }
}

const insertSegmentAfter = async (idx) => {
  const time = transcriptResults.value[idx] ? transcriptResults.value[idx][0] : 0
  const newSeg = [time, time, 'Người lạ (mới)', '']
  transcriptResults.value.splice(idx + 1, 0, newSeg)
  originalTranscriptResults.value.splice(idx + 1, 0, [...newSeg])
  editingIdx.value = idx + 1
  if (currentMeetingName.value) {
    await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
  }
}

const deleteSegment = async (idx) => {
  if (!confirm("Bạn có chắc chắn muốn xóa đoạn hội thoại này?")) return
  transcriptResults.value.splice(idx, 1)
  originalTranscriptResults.value.splice(idx, 1)
  if (currentMeetingName.value) {
    await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
  }
}

// ── AUDIO PLAYER ─────────────────────────────────────────────────────────────
const audioPlayerRef = ref(null)
const isPlaying = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(1)
const playbackRate = ref(1)
let audioCtx = null, gainNode = null, mediaSource = null

const togglePlay = () => {
  if (!audioPlayerRef.value) return
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext
    audioCtx = new AudioContext()
    mediaSource = audioCtx.createMediaElementSource(audioPlayerRef.value)
    gainNode = audioCtx.createGain()
    gainNode.gain.value = volume.value
    mediaSource.connect(gainNode)
    gainNode.connect(audioCtx.destination)
  }
  if (audioCtx.state === 'suspended') audioCtx.resume()
  if (isPlaying.value) { audioPlayerRef.value.pause() } else { audioPlayerRef.value.play() }
  isPlaying.value = !isPlaying.value
}

const formatTime = (time) => {
  if (isNaN(time)) return '0:00'
  const m = Math.floor(time / 60), s = Math.floor(time % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

const onTimeUpdate = () => { if (audioPlayerRef.value) currentTime.value = audioPlayerRef.value.currentTime }
const onLoadedMetadata = () => { if (audioPlayerRef.value) duration.value = audioPlayerRef.value.duration }
const seek = () => { if (audioPlayerRef.value) audioPlayerRef.value.currentTime = currentTime.value }
const updateVolume = () => {
  if (gainNode) gainNode.gain.value = volume.value
  else if (audioPlayerRef.value) audioPlayerRef.value.volume = Math.min(volume.value, 1)
}
const setPlaybackRate = (rate) => {
  playbackRate.value = rate
  if (audioPlayerRef.value) audioPlayerRef.value.playbackRate = rate
}
const skip = (sec) => {
  if (audioPlayerRef.value) {
    audioPlayerRef.value.currentTime += sec
    currentTime.value = audioPlayerRef.value.currentTime
  }
}

const uniqueSpeakers = computed(() => {
  const speakers = new Set()
  for (const seg of transcriptResults.value) {
    if (seg[2]) speakers.add(seg[2])
  }
  return Array.from(speakers)
})

const employeeOptions = computed(() =>
  dbEmployees.value.map(emp => ({
    value: emp.employee_name,
    label: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ')
  }))
)

// Gán tên cho người lạ (KHÔNG enroll giọng) — ai cũng dùng được
const assignStrangerNames = async () => {
  const validMappings = {}
  for (const [spk, name] of Object.entries(speakerMapping.value)) {
    if (name) validMappings[spk] = name
  }
  if (Object.keys(validMappings).length === 0) { alert('Chưa chọn tên cho người lạ nào!'); return }
  for (const seg of transcriptResults.value) { if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]] }
  for (const seg of originalTranscriptResults.value) { if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]] }
  if (currentMeetingName.value) await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
  speakerMapping.value = {}
  alert('✅ Đã gán tên thành công!')
}

// Enroll giọng — CHỈ ADMIN
const enrollMapped = async () => {
  const validMappings = {}
  for (const [spk, name] of Object.entries(speakerMapping.value)) {
    if (name) validMappings[spk] = name
  }
  if (Object.keys(validMappings).length === 0) { alert('Chưa chọn tên cho người lạ nào!'); return }
  isEnrollingMapped.value = true
  try {
    if (currentMeetingName.value) {
      const res = await enrollMappedSpeakers(currentMeetingName.value, validMappings)
      const enrolled = res?.enrolled || [], errors = res?.errors || [], skipped = res?.skipped || []
      let msg = '✅ Đã cập nhật tên.'
      if (enrolled.length) msg += ` Đăng ký giọng: ${enrolled.join(', ')}.`
      if (skipped.length) msg += ` Đã có sẵn: ${skipped.join(', ')}.`
      if (errors.length) msg += ` Lỗi: ${errors.join(', ')}.`
      alert(msg)
    }
    for (const seg of transcriptResults.value) { if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]] }
    for (const seg of originalTranscriptResults.value) { if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]] }
    if (currentMeetingName.value) await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
    speakerMapping.value = {}
  } catch(e) { alert('❌ Lỗi: ' + e.message) }
  finally { isEnrollingMapped.value = false }
}

const languages = [
  { val: 'vi', label: 'Tiếng Việt' }, { val: 'en', label: 'English' },
  { val: 'ja', label: '日本語' }, { val: 'zh', label: '中文' },
  { val: 'ko', label: '한국어' }, { val: 'auto', label: 'Auto detect' }
]

const handleFileChange = (e) => { if (e.target.files.length > 0) audioFile.value = e.target.files[0] }
const audioUrl = computed(() => audioFile.value ? URL.createObjectURL(audioFile.value) : null)

const startTranscribe = async () => {
  if (!audioFile.value) { alert(t('alert_no_file')); return }
  isTranscribing.value = true
  transcribeProgress.value = 0
  transcribeStatus.value = t('status_transcribe_wait')
  transcriptResults.value = []; originalTranscriptResults.value = []
  isCleaned.value = false; transcriptText.value = ''; tasks.value = []; selectedAttendees.value = []
  try {
    const res = await transcribeAudio(audioFile.value, language.value)
    if (res.status === 'processing' && res.meeting_name) {
      currentMeetingName.value = res.meeting_name
      const pollTimer = setInterval(async () => {
        try {
          const pollRes = await checkMeetingStatus(currentMeetingName.value)
          if (pollRes.status === 'processing') {
            if (pollRes.progress_info) {
               if (pollRes.progress_info.stt !== undefined) {
                 const sttProg = pollRes.progress_info.stt.progress || 0
                 const spkProg = pollRes.progress_info.speaker ? pollRes.progress_info.speaker.progress : 0
                 transcribeProgress.value = Math.round((sttProg * 0.5) + (spkProg * 0.5))
                 transcribeStatus.value = sttProg < 100
                   ? (pollRes.progress_info.stt.msg || 'Đang xử lý STT...')
                   : (pollRes.progress_info.speaker ? pollRes.progress_info.speaker.msg : 'Đang xử lý Speaker...')
               } else {
                 transcribeProgress.value = pollRes.progress_info.progress || 0
                 transcribeStatus.value = pollRes.progress_info.message || 'Đang xử lý...'
               }
            }
          } else if (pollRes.status === 'success') {
            clearInterval(pollTimer)
            transcribeProgress.value = 100; transcribeStatus.value = t('status_transcribe_ok')
            transcriptResults.value = pollRes.results; originalTranscriptResults.value = [...pollRes.results]
            isCleaned.value = false; transcriptText.value = pollRes.final_text
            dbEmployees.value = pollRes.employees || []; loadHistory(); isTranscribing.value = false
          } else if (pollRes.status === 'error') {
            clearInterval(pollTimer); transcribeStatus.value = '❌ Error: ' + pollRes.message; isTranscribing.value = false
          }
        } catch (err) { console.error('Polling error', err) }
      }, 5000)
    } else if (res.status === 'success') {
      transcribeStatus.value = t('status_transcribe_ok')
      transcriptResults.value = res.results; originalTranscriptResults.value = [...res.results]
      isCleaned.value = false; transcriptText.value = res.final_text
      dbEmployees.value = res.employees || []; currentMeetingName.value = res.meeting_name || null
      if (res.meeting_name) loadHistory(); isTranscribing.value = false
    } else { transcribeStatus.value = '❌ Error: ' + res.message; isTranscribing.value = false }
  } catch (e) { transcribeStatus.value = t('error_connect'); isTranscribing.value = false }
}

const startCleanTranscript = async () => {
  if (isCleaned.value) { transcriptResults.value = [...originalTranscriptResults.value]; isCleaned.value = false; return }
  if (transcriptResults.value.length === 0) return
  isCleaning.value = true
  try {
    const res = await cleanTranscript(transcriptResults.value, modelType.value, currentMeetingName.value)
    if (res.status === 'success') {
      if (originalTranscriptResults.value.length === 0) originalTranscriptResults.value = [...transcriptResults.value]
      transcriptResults.value = res.cleaned_results; isCleaned.value = true
    } else { alert('❌ Lỗi lọc: ' + res.message) }
  } catch (e) { alert(t('error_connect')) }
  finally { isCleaning.value = false }
}

const openTaskModal = async () => {
   if (tasks.value.length === 0 && transcriptResults.value.length > 0) await startExtractTasks()
   isTaskModalOpen.value = true
}

const startExtractTasks = async () => {
  if (transcriptResults.value.length === 0) { alert(t('alert_no_transcript')); return }
  isExtracting.value = true; extractStatus.value = t('status_extract_wait')
  try {
    const res = await extractTasks(transcriptResults.value, modelType.value, currentMeetingName.value)
    if (res.status === 'processing') {
      const pollTimer = setInterval(async () => {
        try {
          const pollRes = await checkExtractStatus(currentMeetingName.value)
          if (pollRes.status === 'success') {
            clearInterval(pollTimer); extractStatus.value = t('status_extract_ok')
            tasks.value = pollRes.items || []; hrProjectsMap.value = pollRes.hr_projects_map || {}
            dbEmployees.value = pollRes.employees || []; docxUrl.value = pollRes.docx_url; excelUrl.value = pollRes.excel_url
            loadHistory(); isExtracting.value = false; isTaskModalOpen.value = true
          } else if (pollRes.status === 'error') {
            clearInterval(pollTimer); extractStatus.value = '❌ Error: ' + pollRes.message; isExtracting.value = false
          }
        } catch(err) { console.error('Polling extract error', err) }
      }, 5000)
    } else if (res.status === 'success') {
      extractStatus.value = t('status_extract_ok')
      tasks.value = res.items || []; hrProjectsMap.value = res.hr_projects_map || {}
      dbEmployees.value = res.employees || []; docxUrl.value = res.docx_url; excelUrl.value = res.excel_url
      loadHistory(); isExtracting.value = false; isTaskModalOpen.value = true
    } else { extractStatus.value = '❌ Error: ' + res.message; isExtracting.value = false }
  } catch (e) { extractStatus.value = t('error_connect'); isExtracting.value = false }
}
</script>

<template>
<div class="w-full max-w-[1600px] px-4 md:px-8 mx-auto pb-lg pt-md flex-1 min-h-0 h-full flex flex-col">
  <div class="grid grid-cols-1 xl:grid-cols-2 gap-4 items-stretch flex-1">
    
    <!-- LEFT COLUMN -->
    <div class="bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant/30 rounded-2xl p-4 shadow-sm flex flex-col h-full">
      <h2 class="text-xl font-bold text-gray-900 dark:text-on-surface mb-4 font-headline-md tracking-tight">Audio Analysis</h2>
      
      <div class="relative border-2 border-dashed border-outline-variant/50 rounded-xl p-6 flex flex-col items-center justify-center transition-all group flex-1 min-h-[150px] overflow-hidden" :class="{ 'border-primary/50 bg-primary/5': audioFile, 'hover:bg-primary/5 hover:border-primary/50 cursor-pointer': !isTranscribing }">
        <input v-if="!isTranscribing" type="file" accept="audio/*" @change="handleFileChange" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" />
        <div class="relative mb-4">
          <span class="material-symbols-outlined text-[48px] text-primary transition-transform group-hover:scale-110">cloud_upload</span>
        </div>
        <p class="font-body-md text-gray-900 dark:text-on-surface font-medium mb-2 text-center text-sm">Drag &amp; drop file here, or click to select.</p>
        <div v-if="audioFile" class="flex items-center gap-2 bg-white dark:bg-surface px-3 py-1.5 rounded-full border border-gray-300 dark:border-outline-variant/50 max-w-[90%] overflow-hidden relative z-20 shadow-sm">
           <span class="font-body-sm text-gray-900 dark:text-on-surface truncate font-bold text-xs">{{ audioFile.name }}</span>
           <span v-if="!isTranscribing" class="material-symbols-outlined text-[14px] text-gray-500 cursor-pointer hover:text-error" @click.stop.prevent="audioFile = null">close</span>
        </div>
        <div v-if="isTranscribing || transcribeStatus" class="absolute inset-0 bg-white/95 dark:bg-surface/95 backdrop-blur-md z-30 flex flex-col justify-end p-6">
          <div class="w-full space-y-2">
            <div class="h-3 bg-outline-variant/20 rounded-full overflow-hidden relative border border-outline-variant/20">
              <div class="absolute inset-y-0 left-0 bg-primary transition-all duration-1000 rounded-full" :style="{ width: transcribeProgress + '%' }"></div>
            </div>
            <div class="flex justify-between items-center text-xs font-medium text-on-surface-variant">
              <span>{{ transcribeProgress }}%</span>
              <span class="flex items-center gap-1"><span class="material-symbols-outlined text-[12px] animate-spin">autorenew</span> {{ transcribeStatus || 'Processing...' }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="audioUrl" class="mt-4 border-t border-gray-200 dark:border-outline-variant/30 pt-4">
        <div class="flex flex-col gap-2 bg-gray-50 dark:bg-surface rounded-xl p-3 border border-gray-200 dark:border-outline-variant/20 shadow-inner">
           <audio ref="audioPlayerRef" :src="audioUrl" @timeupdate="onTimeUpdate" @loadedmetadata="onLoadedMetadata" @ended="isPlaying = false" class="hidden"></audio>
           <div class="flex items-center gap-3">
             <button @click="togglePlay" class="w-10 h-10 rounded-full bg-primary text-white flex items-center justify-center shrink-0 hover:scale-105 transition-transform shadow-sm">
                <span class="material-symbols-outlined">{{ isPlaying ? 'pause' : 'play_arrow' }}</span>
             </button>
             <div class="flex-1 flex flex-col gap-1 min-w-0">
                <input type="range" min="0" :max="duration || 100" v-model="currentTime" @input="seek" class="w-full h-1 bg-outline-variant/30 rounded-full appearance-none cursor-pointer accent-primary" />
             </div>
             <span class="text-[10px] font-bold text-gray-500 dark:text-on-surface-variant w-auto sm:w-16 text-right whitespace-nowrap">{{ formatTime(currentTime) }} / {{ formatTime(duration) }}</span>
             <div class="flex items-center gap-1 border-l border-gray-300 dark:border-outline-variant/50 pl-2 ml-1">
               <span class="material-symbols-outlined text-[14px] text-gray-500 dark:text-on-surface-variant">{{ volume == 0 ? 'volume_off' : (volume > 1.5 ? 'volume_up' : 'volume_down') }}</span>
               <input type="range" min="0" max="3" step="0.1" v-model.number="volume" @input="updateVolume" class="w-12 sm:w-16 h-1 bg-outline-variant/30 rounded-full appearance-none cursor-pointer accent-primary" />
             </div>
           </div>
           <div class="flex items-center justify-center gap-6 mt-1 pt-2 border-t border-gray-200 dark:border-outline-variant/30">
             <button @click="skip(-30)" class="text-xs font-bold text-gray-500 hover:text-primary flex items-center gap-1 transition-colors group">
                <span class="material-symbols-outlined text-[18px] group-hover:-rotate-45 transition-transform">replay_30</span>
                <span class="hidden sm:inline">-30s</span>
             </button>
             <div class="flex items-center gap-1 bg-gray-200 dark:bg-surface-container-highest rounded-lg p-1">
               <button v-for="s in [0.5, 1, 1.5, 2]" :key="s" @click="setPlaybackRate(s)" class="px-2.5 py-0.5 rounded text-[11px] font-bold transition-all" :class="playbackRate === s ? 'bg-primary text-white shadow-sm' : 'text-gray-600 dark:text-on-surface-variant hover:bg-gray-300 dark:hover:bg-outline-variant/30'">{{ s }}x</button>
             </div>
             <button @click="skip(30)" class="text-xs font-bold text-gray-500 hover:text-primary flex items-center gap-1 transition-colors group">
                <span class="hidden sm:inline">+30s</span>
                <span class="material-symbols-outlined text-[18px] group-hover:rotate-45 transition-transform">forward_30</span>
             </button>
           </div>
        </div>
      </div>
      
      <button @click="startTranscribe" :disabled="!audioFile || isTranscribing" class="mt-4 w-full font-bold py-2.5 px-6 rounded-xl transition-all flex justify-center items-center gap-2" :class="audioFile && !isTranscribing ? 'bg-primary text-white shadow-lg shadow-primary/30 hover:opacity-90 active:scale-[0.98]' : 'bg-primary/30 text-white/50 cursor-not-allowed'">
        <span class="material-symbols-outlined text-[20px]" :class="{ 'animate-spin': isTranscribing }">{{ isTranscribing ? 'autorenew' : 'graphic_eq' }}</span>
        {{ isTranscribing ? 'Analyzing...' : 'Start Transcribe' }}
      </button>
    </div>

    <!-- RIGHT COLUMN: Meeting Details -->
    <div class="bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant/30 rounded-2xl p-4 shadow-sm flex flex-col h-full overflow-y-auto">
      <h2 class="text-xl font-bold text-gray-900 dark:text-on-surface mb-4 font-headline-md">Meeting Details</h2>
      <div class="space-y-1 mb-4">
         <label class="text-[11px] font-bold text-gray-500 dark:text-on-surface-variant uppercase">Language</label>
         <div class="w-full bg-white dark:bg-surface border border-gray-300 dark:border-outline-variant/30 rounded-lg px-1 py-0.5 text-sm focus-within:border-primary transition-colors overflow-hidden">
             <el-select v-model="language" class="w-full custom-el-override" style="width: 100%; --el-fill-color-blank: transparent; --el-bg-color: transparent; --el-input-bg-color: transparent; --el-input-border-color: transparent; --el-input-hover-border-color: transparent; --el-input-focus-border-color: transparent; --el-select-input-color: inherit;">
                <el-option v-for="l in languages" :key="l.val" :label="l.label" :value="l.val" />
             </el-select>
         </div>
      </div>
      <div class="space-y-1 mb-4">
         <label class="text-[11px] font-bold text-gray-500 dark:text-on-surface-variant uppercase">Participants</label>
         <input type="number" v-model="numAttendees" min="0" max="20" class="w-full bg-white dark:bg-surface border border-gray-300 dark:border-outline-variant/30 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-primary transition-colors">
      </div>
      <div class="space-y-1 mb-4">
         <label class="text-[11px] font-bold text-gray-500 dark:text-on-surface-variant uppercase">Keywords</label>
         <textarea v-model="vocabulary" class="w-full bg-white dark:bg-surface border border-gray-300 dark:border-outline-variant/30 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:border-primary transition-colors resize-none min-h-[60px]" placeholder="Nhập từ khóa, tên dự án, thuật ngữ..." rows="2"></textarea>
      </div>
      <div class="space-y-1 mb-4">
         <label class="text-[11px] font-bold text-gray-500 dark:text-on-surface-variant uppercase">Date</label>
         <div class="w-full bg-white dark:bg-surface border border-gray-300 dark:border-outline-variant/30 rounded-lg px-1 py-0.5 text-sm focus-within:border-primary transition-colors overflow-hidden">
            <el-date-picker v-model="meetingDate" type="datetime" format="DD/MM/YYYY HH:mm" placeholder="08/07/2026 17:51" class="w-full custom-el-override" style="width: 100%; --el-fill-color-blank: transparent; --el-input-bg-color: transparent; --el-input-border-color: transparent; --el-input-hover-border-color: transparent; --el-input-focus-border-color: transparent;" />
         </div>
      </div>
      <div class="flex-1 mb-3">
         <label class="text-[12px] font-bold text-gray-500 dark:text-on-surface-variant/70 mb-1 block">Location</label>
         <input v-model="meetingLocation" class="w-full bg-gray-50 dark:bg-surface-container-highest/30 border border-gray-300 dark:border-outline-variant/30 rounded-xl px-4 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-primary/70 transition-colors" placeholder="Nhập địa điểm..." type="text">
      </div>
      <div class="flex-1">
         <label class="text-[12px] font-bold text-gray-500 dark:text-on-surface-variant/70 mb-1 block">Host</label>
         <div class="w-full bg-gray-50 dark:bg-surface-container-highest/30 border border-gray-300 dark:border-outline-variant/30 rounded-xl px-1 py-1 transition-colors overflow-hidden">
            <el-select v-model="hostId" filterable placeholder="Chọn người chủ trì..." class="w-full custom-el-override" style="width: 100%; --el-fill-color-blank: transparent; --el-bg-color: transparent; --el-input-bg-color: transparent; --el-input-border-color: transparent; --el-input-hover-border-color: transparent; --el-input-focus-border-color: transparent; --el-select-input-color: inherit;" fit-input-width>
               <el-option v-for="emp in dbEmployees" :key="emp.user_id" :label="[emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ')" :value="emp.user_id">
                  <div class="truncate w-full block">{{ [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ') }}</div>
               </el-option>
            </el-select>
         </div>
      </div>
    </div>
  </div>

  <!-- STRANGER MAPPING CARD -->
  <div v-if="uniqueSpeakers.length > 0" class="bg-orange-50 dark:bg-orange-900/10 border border-orange-200 dark:border-orange-700/30 rounded-xl p-5 shadow-sm mt-4">
    <div class="mb-4 border-b border-orange-200/50 pb-3 flex items-start justify-between gap-4 flex-wrap">
      <div>
        <h3 class="font-bold text-orange-700 dark:text-orange-400 mb-1 flex items-center gap-2 text-base">
          <span class="material-symbols-outlined text-[20px]">person_add</span>
          Sửa / Gán tên người tham dự
        </h3>
        <p class="text-sm text-gray-600 dark:text-on-surface-variant">Phát hiện <strong>{{ uniqueSpeakers.length }}</strong> người tham gia. Bạn có thể chọn tên để gán lại nếu cần thiết.</p>
      </div>
      <span v-if="isAdmin" class="text-[10px] font-bold text-orange-600 bg-orange-100 dark:bg-orange-900/30 px-2 py-0.5 rounded-full border border-orange-300 self-start mt-1">ADMIN MODE</span>
    </div>
    <div class="flex flex-col gap-3">
      <div v-for="spk in uniqueSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-3 bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant/40 p-3 rounded-lg shadow-sm hover:border-orange-300 transition-colors">
        <div class="flex items-center gap-2 min-w-[180px]">
          <div class="w-8 h-8 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center text-orange-600 font-bold text-xs shrink-0">
            <span class="material-symbols-outlined text-[16px]">person</span>
          </div>
          <span class="font-bold text-gray-800 dark:text-on-surface text-sm">{{ spk }}</span>
        </div>
        <el-select
          v-model="speakerMapping[spk]"
          filterable clearable allow-create default-first-option
          placeholder="Chọn nhân viên hoặc nhập tên..."
          style="flex: 1; --el-fill-color-blank: transparent; --el-bg-color: transparent; --el-input-bg-color: transparent; --el-input-border-color: transparent;"
          class="w-full custom-el-override" fit-input-width
        >
          <el-option v-for="opt in employeeOptions" :key="opt.value" :label="opt.label" :value="opt.value">
            <div class="truncate w-full block" :title="opt.label">{{ opt.label }}</div>
          </el-option>
        </el-select>
      </div>
      <div class="flex justify-end gap-2 mt-1">
        <!-- Ai cũng thấy: chỉ gán tên, không enroll giọng -->
        <button :disabled="!hasSelectedMapping" @click="assignStrangerNames"
          class="font-medium py-2 px-5 rounded-lg transition-all flex items-center gap-2 text-sm"
          :class="hasSelectedMapping ? 'bg-orange-500 text-white hover:bg-orange-600 shadow-sm active:scale-[0.98]' : 'bg-gray-200 text-gray-400 cursor-not-allowed'">
          <span class="material-symbols-outlined text-[18px]">label</span>
          Gán tên
        </button>
        <!-- CHỈ ADMIN thấy: gán tên + enroll giọng vào database -->
        <button v-if="isAdmin" :disabled="!hasSelectedMapping || isEnrollingMapped" @click="enrollMapped"
          class="font-medium py-2 px-5 rounded-lg transition-all flex items-center gap-2 text-sm"
          :class="hasSelectedMapping && !isEnrollingMapped ? 'bg-primary text-white hover:bg-primary/90 shadow-sm active:scale-[0.98]' : 'bg-primary/30 text-white/50 cursor-not-allowed'">
          <span class="material-symbols-outlined text-[18px]">{{ isEnrollingMapped ? 'autorenew' : 'how_to_reg' }}</span>
          {{ isEnrollingMapped ? 'Đang xử lý...' : 'Gán tên & Đăng ký giọng' }}
        </button>
      </div>
    </div>
  </div>

  <!-- TRANSCRIPT CARD -->
  <div v-if="transcriptResults.length > 0" class="bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant/30 rounded-3xl p-6 shadow-2xl flex flex-col flex-1 min-h-[60vh] mt-4">
    <div class="border-b border-gray-200 dark:border-outline-variant pb-md mb-md flex flex-col md:flex-row md:items-center justify-between gap-md shrink-0">
      <div>
        <h3 class="font-headline-md text-headline-md text-gray-900 dark:text-on-surface">{{ t('transcript_result') }}</h3>
        <p class="font-body-sm text-body-sm text-gray-500 dark:text-on-surface-variant">
          {{ transcriptResults.length }} đoạn hội thoại
          <span class="ml-2 text-blue-400 text-[11px]">✏️ Click tên hoặc nội dung để sửa</span>
        </p>
      </div>
      <div class="flex flex-wrap gap-sm">
         <button @click="startCleanTranscript" :disabled="isCleaning" class="px-4 py-2 rounded-md font-medium flex items-center gap-sm border border-gray-300 dark:border-outline-variant hover:bg-gray-100 dark:hover:bg-surface-variant transition-colors text-body-sm" :class="isCleaned ? 'border-primary text-primary bg-primary/5' : 'text-gray-900 dark:text-on-surface'">
           <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isCleaning }">{{ isCleaning ? 'autorenew' : (isCleaned ? 'undo' : 'auto_fix_high') }}</span>
           {{ isCleaning ? "Đang chuẩn hoá..." : (isCleaned ? "Hoàn tác" : "Chuẩn hoá hội thoại") }}
         </button>
         <button @click="openTaskModal" class="px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-md font-medium flex items-center gap-sm shadow-sm transition-colors text-body-sm" :disabled="isExtracting">
           <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isExtracting }">{{ isExtracting ? 'autorenew' : 'task_alt' }}</span>
           {{ tasks.length > 0 ? "Xem Task đã tạo" : t('extract_task') }}
         </button>
      </div>
    </div>
    
    <div class="flex-1 overflow-y-auto space-y-1 pr-sm rounded-lg relative scrollbar-premium">
      <div v-for="(seg, idx) in transcriptResults" :key="idx"
        class="flex flex-col gap-1 group hover:bg-gray-50 dark:hover:bg-surface-container-highest/30 px-3 py-2 rounded-lg transition-colors border border-transparent hover:border-gray-200 dark:hover:border-outline-variant/30">
         <div class="flex items-center gap-2 flex-wrap">
            <div class="flex items-center justify-center w-6 h-6 rounded-full bg-primary/20 text-primary text-[10px] tracking-wider font-bold shrink-0">
               {{ seg[2] ? seg[2].charAt(0).toUpperCase() : '?' }}
            </div>
            
            <!-- Speaker name edit -->
            <template v-if="editingSpeaker === idx">
              <div class="flex items-center gap-1 flex-wrap">
                <el-select v-model="newSpeakerEmployee" filterable clearable allow-create default-first-option
                  placeholder="Chọn hoặc nhập tên..." size="small"
                  style="width: 190px; --el-fill-color-blank: transparent;" class="custom-el-override"
                  @change="saveEditSpeaker(idx)">
                  <el-option v-for="opt in employeeOptions" :key="opt.value" :label="opt.label" :value="opt.value">
                    <span class="text-xs">{{ opt.label }}</span>
                  </el-option>
                </el-select>
                <button @click="saveEditSpeaker(idx)" class="text-xs font-bold text-white bg-primary px-2 py-0.5 rounded hover:bg-primary/90 transition-colors ml-1">Lưu</button>
                <button @click="editingSpeaker = null" class="text-xs text-gray-400 hover:text-gray-600">Hủy</button>
              </div>
            </template>
            <template v-else>
              <span class="font-bold text-[12px] cursor-pointer hover:underline hover:opacity-80 transition-all"
                :class="seg[2] && seg[2].includes('Người lạ') ? 'text-orange-500' : 'text-primary'"
                @click="startEditSpeaker(idx)" title="Click để đổi tên">{{ seg[2] }}</span>
              <span class="text-[11px] text-gray-500 dark:text-on-surface-variant/60 bg-gray-100 dark:bg-surface px-1.5 py-0.5 rounded border border-gray-200 dark:border-outline-variant/30">{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s</span>
              <span class="material-symbols-outlined text-[13px] text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-primary ml-0.5" @click="startEditSpeaker(idx)" title="Đổi tên">edit</span>
              <span class="material-symbols-outlined text-[13px] text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-green-500 ml-1" @click="insertSegmentAfter(idx)" title="Chèn đoạn hội thoại mới xuống dưới">add_circle</span>
              <span class="material-symbols-outlined text-[13px] text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-error ml-1" @click="deleteSegment(idx)" title="Xóa đoạn hội thoại này">delete</span>
            </template>
         </div>
         
         <div class="pl-8">
            <template v-if="editingIdx === idx">
              <textarea v-model="editingText"
                class="w-full border border-primary/50 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-primary resize-none bg-white dark:bg-surface"
                rows="3"
                @keydown.ctrl.enter="saveEditText(idx)" @keyup.esc="editingIdx = null"></textarea>
              <div class="flex gap-2 mt-1">
                <button @click="saveEditText(idx)" class="text-xs font-bold text-white bg-primary px-3 py-1 rounded hover:bg-primary/90 transition-colors">Lưu (Ctrl+Enter)</button>
                <button @click="editingIdx = null" class="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded border border-gray-300 hover:bg-gray-50 transition-colors">Hủy</button>
              </div>
            </template>
            <template v-else>
              <p class="font-body-md text-body-md text-gray-900 dark:text-on-surface leading-relaxed cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/10 rounded px-1 -mx-1 transition-colors"
                @click="startEditText(idx)" title="Click để sửa nội dung">{{ seg[3] || '(Nhập nội dung hội thoại...)' }}</p>
            </template>
         </div>
      </div>
      
      <!-- Nút thêm người / thêm hội thoại (đã xóa theo yêu cầu) -->
    </div>
  </div>

</div>
</template>

<style>
.custom-el-override {
  --el-fill-color-blank: transparent !important;
  --el-input-bg-color: transparent !important;
  --el-bg-color: transparent !important;
  --el-bg-color-overlay: transparent !important;
  background-color: transparent !important;
}
.custom-el-override .el-input__wrapper,
.custom-el-override .el-select__wrapper {
  background-color: transparent !important;
  box-shadow: none !important;
  border: none !important;
}
.custom-el-override .el-input__inner,
.custom-el-override .el-select__placeholder { color: inherit !important; }
.dark .custom-el-override .el-input__inner,
.dark .custom-el-override .el-select__placeholder { color: white !important; }
.custom-el-override .el-input__inner::placeholder,
.custom-el-override .el-select__placeholder.is-transparent { color: rgba(128, 128, 128, 0.6) !important; }
.dark .custom-el-override .el-input__inner::placeholder,
.dark .custom-el-override .el-select__placeholder.is-transparent { color: rgba(255, 255, 255, 0.4) !important; }
.custom-el-override .el-input__prefix,
.custom-el-override .el-input__suffix,
.custom-el-override .el-select__caret { color: inherit !important; }
input[type="range"].accent-primary::-webkit-slider-thumb {
  background: var(--color-primary, #a8c7fa);
  border-radius: 50%;
  cursor: pointer;
}
input[type="range"].accent-primary::-moz-range-thumb {
  background: var(--color-primary, #a8c7fa);
  border-radius: 50%;
  cursor: pointer;
  border: none;
}
</style>
