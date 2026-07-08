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

const numAttendees = ref('Tự động')
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
<div class="max-w-[1000px] mx-auto space-y-lg pb-xl pt-lg">
<!-- Section 1: Xử lý Âm thanh -->
<section class="bg-surface-container border border-outline-variant rounded-xl p-lg md:p-xl shadow-sm">
<div class="mb-lg">
<h2 class="font-headline-md text-headline-md text-on-surface mb-xs">Xử lý Âm thanh</h2>
<p class="font-body-md text-body-md text-on-surface-variant">Tải lên file ghi âm để dịch và nhận diện người nói.</p>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 gap-lg mb-lg">
<div class="flex flex-col gap-xs">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">NGÔN NGỮ</label>
<div class="relative">
<select v-model="language" class="w-full bg-surface border border-outline-variant rounded-md px-md py-2.5 text-body-md font-body-md text-on-surface appearance-none focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-shadow">
<option v-for="l in languages" :key="l.val" :value="l.val">{{ l.label }}</option>
</select>
<span class="material-symbols-outlined absolute right-md top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">expand_more</span>
</div>
</div>
<div class="flex flex-col gap-xs">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">SỐ NGƯỜI THAM DỰ</label>
<div class="relative">
<select v-model="numAttendees" class="w-full bg-surface border border-outline-variant rounded-md px-md py-2.5 text-body-md font-body-md text-on-surface appearance-none focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-shadow">
<option>Tự động</option>
<option>1</option>
<option>2</option>
<option>3</option>
<option>4+</option>
</select>
<span class="material-symbols-outlined absolute right-md top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">unfold_more</span>
</div>
</div>
</div>
<div class="flex flex-col gap-xs">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider flex justify-between">
<span class="">TỪ VỰNG ĐẶC BIỆT (TÙY CHỌN)</span>
</label>
<textarea v-model="vocabulary" class="w-full bg-surface border border-outline-variant rounded-md px-md py-sm text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-shadow resize-y" placeholder="Nhập các từ khóa, tên dự án, thuật ngữ... phân cách bằng dấu phẩy để hệ thống nhận diện chính xác hơn." rows="2"></textarea>
</div>
</section>
<!-- Section 2: Thông tin cuộc họp -->
<section class="bg-surface-container border border-outline-variant rounded-xl p-lg md:p-xl shadow-sm">
<div class="mb-lg">
<h2 class="font-headline-md text-headline-md text-on-surface mb-xs">Thông tin cuộc họp (Dùng cho Biên bản)</h2>
</div>
<div class="grid grid-cols-1 md:grid-cols-2 gap-lg">
<div class="flex flex-col gap-xs">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">NGÀY GIỜ BẮT ĐẦU</label>
<div class="relative">
<span class="material-symbols-outlined absolute left-md top-1/2 -translate-y-1/2 text-on-surface-variant text-[20px]">schedule</span>
<input v-model="meetingDate" class="w-full bg-surface border border-outline-variant rounded-md pl-10 pr-md py-2.5 text-body-md font-body-md text-on-surface focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-shadow" type="text" />
</div>
</div>
<div class="flex flex-col gap-xs">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">ĐỊA ĐIỂM</label>
<input v-model="meetingLocation" class="w-full bg-surface border border-outline-variant rounded-md px-md py-2.5 text-body-md font-body-md text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-shadow" placeholder="Nhập địa điểm..." type="text">
</div>
<div class="flex flex-col gap-xs md:col-span-2">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">NGƯỜI CHỦ TRÌ</label>
<div class="relative">
<select v-model="hostId" class="w-full bg-surface border border-outline-variant rounded-md px-md py-2.5 text-body-md font-body-md text-on-surface appearance-none focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-shadow text-on-surface-variant">
<option disabled value="">Chọn người chủ trì...</option>
<option v-for="emp in dbEmployees" :key="emp.user_id" :value="emp.user_id">{{ emp.employee_name }}</option>
</select>
<span class="material-symbols-outlined absolute right-md top-1/2 -translate-y-1/2 text-on-surface-variant pointer-events-none">expand_more</span>
</div>
</div>
</div>
</section>
<!-- Section 3: Upload & Progress -->
<section class="space-y-lg">
<!-- Dropzone -->
<div class="relative border-2 border-dashed border-outline-variant bg-surface-container/50 hover:bg-surface-container hover:border-primary rounded-xl p-xl flex flex-col items-center justify-center cursor-pointer transition-all min-h-[200px] group">
<input type="file" accept="audio/*" @change="handleFileChange" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-10" />
<div class="w-16 h-16 rounded-full bg-surface-variant flex items-center justify-center mb-md group-hover:bg-primary/20 transition-colors">
<span class="material-symbols-outlined text-4xl text-on-surface-variant group-hover:text-primary transition-colors">cloud_upload</span>
</div>
<p class="font-body-md text-body-md text-on-surface font-medium mb-xs">Drag &amp; drop a file here, or click to select</p>
<p v-if="audioFile" class="font-body-sm text-body-sm text-primary">{{ audioFile.name }}</p>
<p v-else class="font-body-sm text-body-sm text-on-surface-variant/50">Chưa chọn file</p>
</div>

<div class="flex justify-end gap-md items-center">
<div class="flex items-center gap-xs">
<label class="font-label-caps text-label-caps text-on-surface-variant uppercase">Model:</label>
<select v-model="modelType" class="bg-surface border border-outline-variant rounded-md px-md py-1.5 text-body-md font-body-md text-on-surface focus:outline-none focus:border-primary">
  <option value="gpt-4o-mini">GPT-4o-mini</option>
  <option value="gpt-4o">GPT-4o</option>
</select>
</div>
<button @click="startTranscribe" :disabled="isTranscribing" class="bg-primary hover:bg-primary/90 text-on-primary font-bold py-2.5 px-6 rounded-md shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2">
  <span class="material-symbols-outlined">{{ isTranscribing ? 'autorenew' : 'play_arrow' }}</span>
  {{ isTranscribing ? t('analyzing') : t('analyze_voice') }}
</button>
</div>

<!-- Progress Bar -->
<div v-if="isTranscribing || transcribeStatus" class="bg-surface-container border border-outline-variant rounded-xl overflow-hidden shadow-sm relative">
  <div class="absolute inset-0 bg-primary/10" :class="{ 'animate-pulse': isTranscribing }"></div>
  <div class="absolute top-0 left-0 bottom-0 bg-primary/80 transition-all duration-1000" :style="{ width: transcribeProgress + '%' }"></div>
  <div class="relative z-10 flex items-center justify-between px-md py-2">
    <div class="flex items-center gap-sm">
      <span class="material-symbols-outlined text-primary text-[18px]" :class="{ 'animate-spin': isTranscribing }">autorenew</span>
      <span class="font-body-sm text-body-sm font-medium text-primary">Đang phân tích... {{ transcribeProgress }}%</span>
    </div>
    <div class="flex items-center gap-sm text-on-surface-variant opacity-80">
      <span class="text-xs font-body-sm">{{ transcribeStatus }}</span>
    </div>
  </div>
</div>

</section>

<!-- STRANGER MAPPING CARD -->
<div v-if="unknownSpeakers.length > 0" class="bg-surface-container border border-primary rounded-xl p-lg shadow-sm">
  <div class="mb-lg">
    <h3 class="font-headline-md text-headline-md text-on-surface mb-xs flex items-center gap-2">
      <span class="material-symbols-outlined">person_add</span>
      Gán tên người tham dự
    </h3>
    <p class="font-body-md text-body-md text-on-surface-variant">AI phát hiện giọng nói chưa xác định. Chọn tên nhân viên thực tế để gán vào biên bản và đăng ký vào hệ thống.</p>
  </div>
  <div class="flex flex-col gap-3">
    <div v-for="spk in unknownSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-3 bg-background border border-outline-variant p-3 rounded-lg">
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
    <div class="flex justify-end mt-2">
      <button :disabled="isEnrollingMapped" @click="enrollMapped" class="bg-primary hover:bg-primary/90 text-on-primary font-medium py-2 px-4 rounded-md shadow-sm transition-all disabled:opacity-50">
        Cập nhật danh tính & Đăng ký giọng
      </button>
    </div>
  </div>
</div>

<!-- TRANSCRIPT CARD -->
<div v-if="transcriptResults.length > 0" class="bg-surface-container border border-outline-variant rounded-xl p-lg md:p-xl shadow-sm">
  <div class="border-b border-outline-variant pb-md mb-md flex justify-between items-center">
    <div>
      <h3 class="font-headline-md text-headline-md text-on-surface">{{ t('transcript_result') }}</h3>
      <p class="font-body-md text-body-md text-on-surface-variant mt-1">{{ t('transcript_desc') }}</p>
    </div>
    <div class="flex gap-3">
       <button @click="startCleanTranscript" :disabled="isCleaning" class="px-4 py-2 rounded-md font-medium flex items-center gap-2 border border-outline-variant hover:bg-surface-variant transition-colors" :class="isCleaned ? 'border-primary text-primary' : 'text-on-surface'">
         <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isCleaning }">{{ isCleaning ? 'autorenew' : (isCleaned ? 'undo' : 'auto_fix_high') }}</span>
         {{ isCleaning ? "Đang chuẩn hoá..." : (isCleaned ? "Hoàn tác" : "Chuẩn hoá hội thoại") }}
       </button>
       
       <button @click="openTaskModal" class="px-4 py-2 bg-inverse-primary text-background rounded-md font-medium flex items-center gap-2 shadow-sm hover:opacity-90 transition-opacity" :disabled="isExtracting">
         <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isExtracting }">{{ isExtracting ? 'autorenew' : 'task_alt' }}</span>
         {{ tasks.length > 0 ? "View Tasks" : t('extract_task') }}
       </button>
    </div>
  </div>
  <div class="log-view p-4 space-y-6 max-h-[600px] overflow-auto relative bg-background rounded-lg border border-outline-variant">
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
</template>
