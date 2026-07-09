<script setup>
import { defineProps, computed, ref } from 'vue'
import { 
  dbEmployees, tasks, isExtracting, extractStatus, isTaskModalOpen, 
  hrProjectsMap, docxUrl, excelUrl, loadHistory, modelType 
} from '../composables/useVoiceApp'
import { enrollMappedSpeakers, updateMeetingResults, extractTasks, checkExtractStatus } from '../api'

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
  window.open(url, '_blank');
}

// --- SPEAKER MAPPING LOGIC ---
const speakerMapping = ref({})
const isEnrollingMapped = ref(false)

const hasSelectedMapping = computed(() => {
  return Object.values(speakerMapping.value).some(val => !!val)
})

const unknownSpeakers = computed(() => {
  const speakers = new Set()
  for (const seg of parseSegments.value) {
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
    const res = await enrollMappedSpeakers(props.meeting.name, validMappings)
    const enrolled = res?.enrolled || []
    const errors = res?.errors || []
    const skipped = res?.skipped || []
    let msg = `✅ Đã cập nhật tên.`
    if (enrolled.length) msg += ` Đăng ký giọng: ${enrolled.join(', ')}.`
    if (skipped.length) msg += ` Đã có sẵn: ${skipped.join(', ')}.`
    if (errors.length) msg += ` Lỗi: ${errors.join(', ')}.`
    alert(msg)
    
    for (const seg of parseSegments.value) {
      if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]]
    }
    
    await updateMeetingResults(props.meeting.name, parseSegments.value)
    speakerMapping.value = {}
  } catch(e) {
    alert('❌ Lỗi: ' + e.message)
  } finally {
    isEnrollingMapped.value = false
  }
}

// --- EXTRACT TASKS LOGIC ---
const startExtractTasks = async () => {
  if (parseSegments.value.length === 0) {
    alert(props.t('alert_no_transcript'))
    return
  }
  isExtracting.value = true
  extractStatus.value = props.t('status_extract_wait')
  
  try {
    const res = await extractTasks(parseSegments.value, modelType.value, props.meeting.name)
    if (res.status === 'processing') {
      const pollTimer = setInterval(async () => {
        try {
          const pollRes = await checkExtractStatus(props.meeting.name)
          if (pollRes.status === 'success') {
            clearInterval(pollTimer)
            extractStatus.value = props.t('status_extract_ok')
            tasks.value = pollRes.items || []
            hrProjectsMap.value = pollRes.hr_projects_map || {}
            dbEmployees.value = pollRes.employees || []
            docxUrl.value = pollRes.docx_url
            excelUrl.value = pollRes.excel_url
            loadHistory()
            isExtracting.value = false
            isTaskModalOpen.value = true
          } else if (pollRes.status === 'error') {
            clearInterval(pollTimer)
            extractStatus.value = '❌ Error: ' + pollRes.message
            isExtracting.value = false
          }
        } catch(err) {
          console.error("Polling extract error", err)
        }
      }, 5000)
    } else if (res.status === 'success') {
      extractStatus.value = props.t('status_extract_ok')
      tasks.value = res.items || []
      hrProjectsMap.value = res.hr_projects_map || {}
      dbEmployees.value = res.employees || []
      docxUrl.value = res.docx_url
      excelUrl.value = res.excel_url
      loadHistory()
      isExtracting.value = false
      isTaskModalOpen.value = true
    } else {
      extractStatus.value = '❌ Error: ' + res.message
      isExtracting.value = false
    }
  } catch (e) {
    extractStatus.value = props.t('error_connect')
    isExtracting.value = false
  }
}

const openTaskModal = () => {
    if (tasks.value.length === 0 && parseSegments.value.length > 0) {
        startExtractTasks()
    } else {
        isTaskModalOpen.value = true
    }
}
</script>

<template>
  <div v-if="meeting" class="flex-1 w-full max-w-5xl mx-auto space-y-xl pb-10 mt-2 fade-in">
    <!-- Header Section -->
    <section class="flex flex-col gap-md">
      <div>
        <h2 class="font-headline-lg text-headline-lg text-gray-900 dark:text-on-surface">{{ meeting.title }}</h2>
        <div class="flex items-center gap-2 mt-2 text-body-sm text-gray-500 dark:text-on-surface-variant font-body-sm">
          <span>{{ meeting.date }}</span>
          <span>•</span>
          <span class="flex items-center gap-1"><span class="w-2 h-2 rounded-full bg-primary inline-block"></span> {{ meeting.status || 'Analyzed' }}</span>
        </div>
      </div>
      <div class="flex flex-wrap gap-3 mt-sm">
        <button @click="openTaskModal" class="flex items-center gap-2 px-4 py-2 bg-primary/10 border border-primary/20 rounded-lg text-primary hover:bg-primary/20 transition-colors font-body-sm text-body-sm font-bold shadow-sm" :disabled="isExtracting">
          <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isExtracting }">{{ isExtracting ? 'autorenew' : 'task_alt' }}</span>
          {{ isExtracting ? 'Đang trích xuất...' : (tasks.length > 0 ? 'Xem Task đã trích xuất' : 'Trích xuất Task') }}
        </button>

        <button v-if="meeting.minute_docx" @click="downloadFile(meeting.minute_docx, meeting.title + '.docx')" class="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-surface-container border border-gray-200 dark:border-outline-variant rounded-lg text-secondary hover:bg-gray-100 dark:hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[18px]">description</span> Tải Biên bản (Word)
        </button>
        <button v-if="meeting.task_xlsx" @click="downloadFile(meeting.task_xlsx, meeting.title + '.xlsx')" class="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-surface-container border border-gray-200 dark:border-outline-variant rounded-lg text-primary hover:bg-gray-100 dark:hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[18px]">download</span> Tải Tasks (Excel)
        </button>
      </div>
    </section>

    <!-- STRANGER MAPPING CARD -->
    <section v-if="unknownSpeakers.length > 0" class="bg-error-container/10 border border-error/20 rounded-xl p-lg shadow-sm">
      <div class="mb-lg border-b border-error/10 pb-md">
        <h3 class="font-headline-md text-headline-md text-error mb-xs flex items-center gap-sm">
          <span class="material-symbols-outlined">person_add</span>
          Gán tên người tham dự
        </h3>
        <p class="font-body-md text-body-md text-gray-500 dark:text-on-surface-variant">AI phát hiện giọng nói chưa xác định. Chọn tên nhân viên thực tế để gán vào biên bản và đăng ký vào hệ thống.</p>
      </div>
      <div class="flex flex-col gap-md">
        <div v-for="spk in unknownSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-md bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant/50 p-md rounded-lg shadow-sm hover:border-primary/50 transition-colors">
          <div class="flex items-center gap-sm min-w-[180px]">
            <div class="w-8 h-8 rounded-full bg-error/10 flex items-center justify-center text-error font-bold text-xs shrink-0">?</div>
            <span class="font-body-md text-body-md font-bold text-gray-900 dark:text-on-surface">{{ spk }}</span>
          </div>
          <el-select
            v-model="speakerMapping[spk]"
            filterable
            clearable
            allow-create
            default-first-option
            placeholder="Chọn nhân viên hoặc nhập tên..."
            style="flex: 1; --el-fill-color-blank: transparent; --el-input-bg-color: transparent; --el-input-border-color: transparent;"
            class="w-full custom-el-override"
            fit-input-width
          >
            <el-option
              v-for="opt in employeeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            >
              <div class="truncate w-full block" :title="opt.label">{{ opt.label }}</div>
            </el-option>
          </el-select>
        </div>
        <div class="flex justify-end mt-sm">
          <button :disabled="!hasSelectedMapping || isEnrollingMapped" @click="enrollMapped" class="font-medium py-2.5 px-6 rounded-md transition-all flex items-center gap-sm" :class="hasSelectedMapping && !isEnrollingMapped ? 'bg-error text-white hover:bg-error/90 shadow-md active:scale-[0.98]' : 'bg-error/30 text-white/50 cursor-not-allowed'">
            <span class="material-symbols-outlined text-[20px]">{{ isEnrollingMapped ? 'autorenew' : 'how_to_reg' }}</span>
            {{ isEnrollingMapped ? 'Đang xử lý...' : 'Cập nhật danh tính & Đăng ký giọng' }}
          </button>
        </div>
      </div>
    </section>

    <!-- Transcript Section (Adapted from the box style) -->
    <section v-if="parseSegments.length > 0" class="bg-white dark:bg-surface-container rounded-xl border border-gray-200 dark:border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low flex justify-between items-center">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> NỘI DUNG HỘI THOẠI
          </h3>
          <p class="text-body-sm text-gray-500 dark:text-on-surface-variant mt-1">{{ t('transcript_desc') }}</p>
        </div>
      </div>
      <div class="p-lg bg-white dark:bg-surface">
        <div class="transcript-log max-h-[600px] overflow-auto flex flex-col gap-4 pr-2">
          <div v-for="(seg, idx) in parseSegments" :key="idx" class="relative border-l-2 border-gray-300 dark:border-outline-variant pl-4 py-1">
            <div class="absolute -left-[5px] top-3 w-2 h-2 rounded-full bg-primary/50"></div>
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-sm tracking-wide" :class="seg[2].includes('Người lạ') ? 'text-red-600' : ''" :style="!seg[2].includes('Người lạ') ? { color: stringToColor(seg[2]) } : {}">{{ seg[2] }}</span>
              <span class="text-xs text-gray-500 dark:text-on-surface-variant font-label-caps">[{{ formatTime(seg[0]) }}]</span>
            </div>
            <p class="text-sm leading-relaxed text-gray-900 dark:text-on-surface whitespace-pre-wrap break-words m-0">{{ seg[3] }}</p>
          </div>
        </div>
      </div>
    </section>
    
    <section v-else-if="meeting.raw_results" class="bg-white dark:bg-surface-container rounded-xl border border-gray-200 dark:border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low flex justify-between items-center">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> NỘI DUNG HỘI THOẠI
          </h3>
          <p class="text-body-sm text-gray-500 dark:text-on-surface-variant mt-1">{{ t('transcript_desc') }}</p>
        </div>
      </div>
      <div class="p-lg bg-white dark:bg-surface">
        <pre class="whitespace-pre-wrap font-label-caps text-sm bg-gray-100 dark:bg-surface-container-high p-4 rounded-lg overflow-auto border border-gray-200 dark:border-outline-variant max-h-[600px] text-gray-900 dark:text-on-surface">{{ meeting.raw_results }}</pre>
      </div>
    </section>
    
    <section v-else-if="meeting.transcript" class="bg-white dark:bg-surface-container rounded-xl border border-gray-200 dark:border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low flex justify-between items-center">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> NỘI DUNG HỘI THOẠI
          </h3>
        </div>
      </div>
      <div class="p-lg bg-white dark:bg-surface">
        <pre class="whitespace-pre-wrap font-body-sm text-sm max-h-[600px] overflow-auto text-gray-900 dark:text-on-surface">{{ meeting.transcript }}</pre>
      </div>
    </section>
  </div>
  <div v-else class="flex h-full items-center justify-center text-gray-500 dark:text-on-surface-variant font-medium text-lg min-h-[400px]">
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
  background: #cbd5e1;
  border-radius: 3px;
}
.dark .transcript-log::-webkit-scrollbar-thumb {
  background: #464554;
}
.transcript-log::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
.dark .transcript-log::-webkit-scrollbar-thumb:hover {
  background: #908fa0;
}
</style>
