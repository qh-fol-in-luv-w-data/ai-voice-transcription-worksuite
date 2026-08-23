<script setup>
import { defineProps, computed, ref } from 'vue'
import { 
  dbEmployees, tasks, isExtracting, extractStatus, isTaskModalOpen, 
  hrProjectsMap, docxUrl, excelUrl, loadHistory, modelType,
  meetingSummary, meetingConclusion, currentMeetingName
} from '../composables/useVoiceApp'
import { enrollMappedSpeakers, updateMeetingResults, extractTasks, checkExtractStatus, reassignSpeakerFromSegment, rescanMeetingFromCurrentLabels, normalizeMeetingTranscript, exportDynamicDocx, saveMeetingDraft } from '../api'

const props = defineProps({
  meeting: Object,
  t: Function
})

const stringToColor = (str) => {
  if (!str) return '#888888';
  let hash = 0;
  for (const char of str) {
    hash = char.codePointAt(0) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
}

// --- LOCAL SEGMENTS FOR EDITING ---
const localSegments = ref([])
import { watch } from 'vue'

watch(() => props.meeting, (newVal) => {
  if (newVal && newVal.raw_results) {
    try {
      localSegments.value = typeof newVal.raw_results === 'string' ? JSON.parse(newVal.raw_results) : newVal.raw_results
    } catch {
      localSegments.value = []
    }
  } else {
    localSegments.value = []
  }
}, { immediate: true })

const formatTime = (seconds) => {
  if (seconds == null) return '0.00s'
  return (typeof seconds === 'number' ? seconds : Number.parseFloat(seconds)).toFixed(2) + 's'
}

const downloadFile = (url) => {
  if (!url) return;
  const link = document.createElement('a');
  link.href = url;
  const parts = url.split('/');
  link.download = parts[parts.length - 1] || 'file';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ── ADMIN CHECK ────────────────────────────────────────────────────────────
const isAdmin = computed(() => {
  try {
    const roles = window.frappe?.boot?.user?.roles || []
    return roles.includes('System Manager') || roles.includes('Administrator')
  } catch { return false }
})

// --- INLINE EDITING ---
const editingIdx = ref(null)
const editingText = ref('')
const editingSpeaker = ref(null)
const editingSpeakerName = ref('')
const newSpeakerEmployee = ref('')
const isRescanning = ref(false)
const isNormalizingTranscript = ref(false)
const rescanMessage = ref('')
const canRunAudioRescan = computed(() => !!props.meeting?.audio_file)

const undoStack = ref([])

const saveState = () => {
  undoStack.value.push(JSON.parse(JSON.stringify(localSegments.value)))
  if (undoStack.value.length > 50) undoStack.value.shift()
}

const undoAction = async () => {
  if (undoStack.value.length === 0) return
  const prevState = undoStack.value.pop()
  localSegments.value = prevState
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}

const deleteSpeaker = async (spk) => {
  if (!confirm(`Bạn có chắc chắn muốn xóa tên "${spk}" khỏi các đoạn hội thoại?`)) return
  saveState()
  for (const seg of localSegments.value) {
    if (seg[2] === spk) seg[2] = ''
  }
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}

const startEditText = (idx) => {
  editingIdx.value = idx
  editingText.value = localSegments.value[idx][3]
}
const saveEditText = async (idx) => {
  if (editingIdx.value !== idx) return
  saveState()
  localSegments.value[idx][3] = editingText.value
  editingIdx.value = null
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}
const startEditSpeaker = (idx) => {
  editingSpeaker.value = idx
  editingSpeakerName.value = localSegments.value[idx][2]
  newSpeakerEmployee.value = ''
  newSpeakerQuery.value = ''
}
const saveEditSpeaker = async (idx) => {
  const finalName = (newSpeakerEmployee.value || newSpeakerQuery.value || '').trim()
  if (!finalName) { editingSpeaker.value = null; return }
  const oldName = localSegments.value[idx][2]
  saveState()
  for (const seg of localSegments.value) {
    if (seg[2] === oldName) seg[2] = finalName
  }
  editingSpeaker.value = null
  newSpeakerEmployee.value = ''
  newSpeakerQuery.value = ''
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}
const saveAndRescanSpeaker = async (idx) => {
  const finalName = (newSpeakerEmployee.value || newSpeakerQuery.value || '').trim()
  if (!finalName) {
    ElMessage.warning('Chọn hoặc nhập tên người nói trước khi quét lại')
    return
  }
  if (!props.meeting?.name) { alert('Không tìm thấy meeting!'); return }
  if (!canRunAudioRescan.value) {
    alert('Meeting này không có audio gốc nên không thể quét lại AI.')
    return
  }

  editingSpeaker.value = null
  isRescanning.value = true
  rescanMessage.value = 'Đang trích xuất đặc trưng giọng nói...'

  try {
    const res = await reassignSpeakerFromSegment(props.meeting.name, idx, finalName)
    if (res && res.status === 'success') {
      localSegments.value = res.results
      newSpeakerEmployee.value = ''
      newSpeakerQuery.value = ''
      rescanMessage.value = res.message || 'Quét lại thành công!'
      setTimeout(() => { rescanMessage.value = '' }, 3000)
    } else {
      alert('❌ Lỗi: ' + (res?.message || 'Không xác định'))
      rescanMessage.value = ''
    }
  } catch (e) {
    alert('❌ Lỗi kết nối: ' + e.message)
    rescanMessage.value = ''
  } finally {
    isRescanning.value = false
  }
}

const rescanFromEditedTranscript = async () => {
  if (!props.meeting?.name) { alert('Không tìm thấy meeting!'); return }
  if (!canRunAudioRescan.value) {
    alert('Meeting này không có audio gốc nên không thể quét lại AI.')
    return
  }
  if (editingSpeaker.value !== null || editingIdx.value !== null) {
    alert('Lưu hoặc hủy phần đang chỉnh trước khi quét lại AI')
    return
  }

  isRescanning.value = true
  rescanMessage.value = 'Đang quét lại toàn bộ cuộc họp theo tên đã sửa...'

  try {
    saveState()
    const res = await rescanMeetingFromCurrentLabels(props.meeting.name)
    if (res && res.status === 'success') {
      localSegments.value = res.results || localSegments.value
      rescanMessage.value = res.message || 'Quét lại thành công!'
      setTimeout(() => { rescanMessage.value = '' }, 3000)
    } else {
      alert('❌ Lỗi: ' + (res?.message || 'Không xác định'))
      rescanMessage.value = ''
    }
  } catch (e) {
    alert('❌ Lỗi kết nối: ' + e.message)
    rescanMessage.value = ''
  } finally {
    isRescanning.value = false
  }
}

const normalizeTranscript = async () => {
  if (!props.meeting?.name) { alert('Không tìm thấy meeting!'); return }
  if (!canNormalizeTranscript.value) {
    alert('Vẫn còn người lạ trong transcript, gán hết tên rồi hãy chuẩn hoá hội thoại.')
    return
  }
  if (editingSpeaker.value !== null || editingIdx.value !== null) {
    alert('Lưu hoặc hủy phần đang chỉnh trước khi chuẩn hoá hội thoại')
    return
  }

  isNormalizingTranscript.value = true
  rescanMessage.value = 'Đang chuẩn hoá hội thoại...'

  try {
    saveState()
    const res = await normalizeMeetingTranscript(props.meeting.name)
    if (res && res.status === 'success') {
      localSegments.value = res.results || localSegments.value
      rescanMessage.value = res.message || 'Chuẩn hoá hội thoại thành công!'
      setTimeout(() => { rescanMessage.value = '' }, 3000)
    } else {
      alert('❌ Lỗi: ' + (res?.message || 'Không xác định'))
      rescanMessage.value = ''
    }
  } catch (e) {
    alert('❌ Lỗi kết nối: ' + e.message)
    rescanMessage.value = ''
  } finally {
    isNormalizingTranscript.value = false
  }
}
const addNewSegment = async () => {
  saveState()
  const newSeg = [0, 0, 'Người lạ (mới)', '']
  localSegments.value.push(newSeg)
  editingIdx.value = localSegments.value.length - 1
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}
const insertSegmentAfter = async (idx) => {
  saveState()
  const time = localSegments.value[idx] ? localSegments.value[idx][0] : 0
  const newSeg = [time, time, 'Người lạ (mới)', '']
  localSegments.value.splice(idx + 1, 0, newSeg)
  editingIdx.value = idx + 1
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}
const deleteSegment = async (idx) => {
  if (!confirm("Bạn có chắc chắn muốn xóa đoạn hội thoại này?")) return
  saveState()
  localSegments.value.splice(idx, 1)
  if (props.meeting?.name) {
    await updateMeetingResults(props.meeting.name, localSegments.value)
  }
}

// --- SPEAKER MAPPING LOGIC ---
const speakerMapping = ref({})
const isEnrollingMapped = ref(false)

const hasSelectedMapping = computed(() => {
  return Object.values(speakerMapping.value).some(val => !!val)
})

const uniqueSpeakers = computed(() => {
  const speakers = new Set()
  for (const seg of localSegments.value) {
    if (seg[2]) speakers.add(seg[2])
  }
  return Array.from(speakers)
})

const speakerStats = computed(() => {
  const known = new Set()
  const unknownGroups = new Set()
  let unknownSegments = 0
  for (const seg of localSegments.value) {
    const speaker = seg[2] || ''
    if (!speaker) continue
    if (speaker.includes('Speaker') || speaker.includes('Người lạ') || speaker.includes('Unknown') || speaker.includes('Không tên')) {
      unknownGroups.add(speaker)
      unknownSegments += 1
    } else {
      known.add(speaker)
    }
  }
  return {
    knownCount: known.size,
    unknownGroupCount: unknownGroups.size,
    unknownSegments
  }
})

const canNormalizeTranscript = computed(() =>
  localSegments.value.length > 0 && speakerStats.value.unknownSegments === 0
)

const formatEmployeeOption = (emp) => {
  const name = emp.employee_name || emp.user_id || ''
  const isVoiceSpeaker = emp.designation === 'Voice Speaker'
  const parts = [name]
  if (emp.user_id && emp.user_id !== name) parts.push(emp.user_id)
  if (emp.designation && !(isVoiceSpeaker && name.includes('Voice Speaker'))) parts.push(emp.designation)
  return parts.filter(Boolean).join(' - ')
}

const employeeOptions = computed(() =>
  dbEmployees.value.map(emp => {
    const label = formatEmployeeOption(emp)
    return { value: emp.employee_name || emp.user_id || label, label }
  })
)

const speakerQueries = ref({})
const filterSpeakerMapping = (spk, query) => {
  speakerQueries.value[spk] = query
}
const getFilteredEmployeeOptions = (spk) => {
  const query = speakerQueries.value[spk]
  if (!query) return employeeOptions.value
  const q = query.toLowerCase()
  return employeeOptions.value.filter(opt => opt.label.toLowerCase().includes(q))
}
const onSpeakerSelectVisibleChange = (spk, visible) => {
  if (!visible) speakerQueries.value[spk] = ''
}

const newSpeakerQuery = ref('')
const filterNewSpeakerEmployee = (query) => {
  newSpeakerQuery.value = query
}
const filteredNewSpeakerOptions = computed(() => {
  const query = newSpeakerQuery.value
  if (!query) return employeeOptions.value
  const q = query.toLowerCase()
  return employeeOptions.value.filter(opt => opt.label.toLowerCase().includes(q))
})
const onNewSpeakerSelectVisibleChange = (visible) => {
  if (visible) newSpeakerQuery.value = ''
}

const assignStrangerNames = async () => {
  const validMappings = {}
  for (const [spk, name] of Object.entries(speakerMapping.value)) {
    if (name) validMappings[spk] = name
  }
  if (Object.keys(validMappings).length === 0) { alert('Chưa chọn tên cho người lạ nào!'); return }
  saveState()
  for (const seg of localSegments.value) { if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]] }
  if (props.meeting?.name) await updateMeetingResults(props.meeting.name, localSegments.value)
  speakerMapping.value = {}
  alert('✅ Đã gán tên thành công!')
}

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
    if (res?.reassigned_count !== undefined) msg += ` Quét lại: ${res.reassigned_count} đoạn.`
    if (errors.length) msg += ` Lỗi: ${errors.join(', ')}.`
    alert(msg)
    
    saveState()
    if (res?.results) {
      localSegments.value = res.results
    } else {
      for (const seg of localSegments.value) {
        if (validMappings[seg[2]]) seg[2] = validMappings[seg[2]]
      }
      await updateMeetingResults(props.meeting.name, localSegments.value)
    }
    speakerMapping.value = {}
  } catch(e) {
    alert('❌ Lỗi: ' + e.message)
  } finally {
    isEnrollingMapped.value = false
  }
}

import { onSocketEvent, offSocketEvent } from '../utils/socket.js'

// --- EXTRACT TASKS LOGIC ---
import { ElMessage } from 'element-plus'

const isExporting = ref(false)

const handleExportDocx = async () => {
  if (!props.meeting?.name) return
  isExporting.value = true
  try {
    await saveMeetingDraft(
      props.meeting.name,
      meetingSummary.value,
      meetingConclusion.value,
      JSON.stringify(tasks.value)
    )
    const res = await exportDynamicDocx(props.meeting.name)
    if (res.status === 'success' && res.file_url) {
      downloadFile(res.file_url)
    } else {
      ElMessage.error(res.message || "Không thể xuất DOCX")
    }
  } catch (e) {
    ElMessage.error("Lỗi khi xuất DOCX")
  } finally {
    isExporting.value = false
  }
}

const startExtractTasks = async () => {
  if (localSegments.value.length === 0) {
    alert(props.t('alert_no_transcript'))
    return
  }
  isExtracting.value = true
  extractStatus.value = props.t('status_extract_wait')

  try {
    const res = await extractTasks(localSegments.value, modelType.value, props.meeting.name)
    if (res.status === 'processing') {
      extractStatus.value = '⏳ Đang chờ máy chủ xử lý...';
      
      // Fallback Polling if socket doesn't work
      const pollTimer = setInterval(async () => {
        if (!isExtracting.value) { clearInterval(pollTimer); return; }
        try {
          const statusRes = await checkExtractStatus(props.meeting.name);
          if (statusRes.message && statusRes.message.status) {
            // Frappe might return { message: { status: "success", ... } }
            Object.assign(statusRes, statusRes.message);
          }
          if (statusRes.status === 'success') {
            clearInterval(pollTimer);
            extractStatus.value = props.t('status_extract_ok');
            tasks.value = statusRes.items || [];
            hrProjectsMap.value = statusRes.hr_projects_map || {};
            dbEmployees.value = statusRes.employees || [];
            docxUrl.value = statusRes.docx_url;
            excelUrl.value = statusRes.excel_url;
            if (statusRes.meeting_summary) meetingSummary.value = statusRes.meeting_summary;
            if (statusRes.conclusion) meetingConclusion.value = statusRes.conclusion;
            loadHistory();
            isExtracting.value = false;
          } else if (statusRes.status === 'error') {
            clearInterval(pollTimer);
            extractStatus.value = '❌ Lỗi: ' + (statusRes.message || '');
            isExtracting.value = false;
          } else if (statusRes.status === 'processing' && statusRes.progress_info) {
            extractStatus.value = statusRes.progress_info;
          }
        } catch(e) {
          console.error(e);
        }
      }, 5000);
    } else if (res.status === 'success') {
      extractStatus.value = props.t('status_extract_ok')
      tasks.value = res.items || []
      hrProjectsMap.value = res.hr_projects_map || {}
      dbEmployees.value = res.employees || []
      docxUrl.value = res.docx_url
      excelUrl.value = res.excel_url
      if (res.meeting_summary) meetingSummary.value = res.meeting_summary
      if (res.conclusion) meetingConclusion.value = res.conclusion
      loadHistory()
      isExtracting.value = false
    } else {
      extractStatus.value = '❌ Lỗi: ' + res.message
      isExtracting.value = false
    }
  } catch(e) {
    extractStatus.value = props.t('error_connect')
    isExtracting.value = false
  }
}

const openTaskModal = () => {
    currentMeetingName.value = props.meeting?.name
    if (tasks.value.length === 0 && localSegments.value.length > 0) {
        startExtractTasks()
    } else {
        isTaskModalOpen.value = true
    }
}

const getProjectsForHR = (employeeName) => {
  if (!employeeName) return []
  const userId = dbEmployees.value.find(e => e.employee_name === employeeName)?.user_id
  if (!userId || !hrProjectsMap.value[userId]) return []
  return hrProjectsMap.value[userId].map(p => [p.project_name, p.name])
}

const addTask = () => {
  tasks.value.push({
    title: '',
    task_type: 'task',
    assignee_display: '',
    project: '',
    start_date: '',
    due_date: '',
    description: ''
  })
}

const removeTask = (idx) => {
  tasks.value.splice(idx, 1)
}
</script>

<template>
  <!-- Rescanning overlay -->
  <transition name="fade">
    <div v-if="isRescanning" class="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex flex-col items-center justify-center gap-4">
      <div class="bg-white dark:bg-surface rounded-2xl p-8 shadow-2xl flex flex-col items-center gap-4 max-w-sm w-full mx-4">
        <span class="material-symbols-outlined text-[48px] text-orange-500 animate-spin">manage_search</span>
        <p class="font-bold text-gray-900 dark:text-on-surface text-center">Đang quét lại giọng nói...</p>
        <p class="text-sm text-gray-500 dark:text-on-surface-variant text-center">{{ rescanMessage }}</p>
        <div class="w-full h-1.5 bg-gray-200 dark:bg-surface-container rounded-full overflow-hidden">
          <div class="h-full bg-orange-500 rounded-full animate-pulse" style="width: 60%"></div>
        </div>
      </div>
    </div>
  </transition>
  <!-- Rescan success toast -->
  <transition name="slide-fade">
    <div v-if="rescanMessage && !isRescanning" class="fixed bottom-6 right-6 z-50 bg-green-500 text-white px-4 py-3 rounded-xl shadow-lg flex items-center gap-2 font-bold text-sm">
      <span class="material-symbols-outlined text-[18px]">check_circle</span>
      {{ rescanMessage }}
    </div>
  </transition>
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

        <button @click="handleExportDocx" class="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-surface-container border border-gray-200 dark:border-outline-variant rounded-lg text-secondary hover:bg-gray-100 dark:hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm" :disabled="isExporting">
          <span class="material-symbols-outlined text-[18px]" :class="{ 'animate-spin': isExporting }">{{ isExporting ? 'autorenew' : 'description' }}</span> 
          {{ isExporting ? 'Đang xuất...' : 'Xuất Biên bản họp' }}
        </button>
        <button v-if="meeting.task_xlsx" @click="downloadFile(meeting.task_xlsx, meeting.title + '.xlsx')" class="flex items-center gap-2 px-4 py-2 bg-gray-50 dark:bg-surface-container border border-gray-200 dark:border-outline-variant rounded-lg text-primary hover:bg-gray-100 dark:hover:bg-surface-container-highest transition-colors font-body-sm text-body-sm">
          <span class="material-symbols-outlined text-[18px]">download</span> Tải Tasks (Excel)
        </button>
      </div>
    </section>

    <!-- Summary & Conclusion Section -->
    <section class="bg-white dark:bg-surface-container rounded-xl border border-gray-200 dark:border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low">
        <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
          <span class="material-symbols-outlined">summarize</span> TÓM TẮT & KẾT LUẬN
        </h3>
        <p class="text-body-sm text-gray-500 dark:text-on-surface-variant mt-1">Chỉnh sửa tóm tắt và kết luận (Hệ thống sẽ tự động lưu)</p>
      </div>
      <div class="p-lg bg-white dark:bg-surface flex flex-col gap-4">
        <div>
          <h4 class="text-md font-medium mb-2">Tóm tắt nội dung chính</h4>
          <el-input
            v-model="meetingSummary"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            resize="none"
            placeholder="Nhập tóm tắt cuộc họp..."
          />
        </div>
        <div>
          <h4 class="text-md font-medium mb-2">Kết luận cuộc họp</h4>
          <el-input
            v-model="meetingConclusion"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 10 }"
            resize="none"
            placeholder="Nhập kết luận cuộc họp..."
          />
        </div>
      </div>
      
      <!-- TASK LIST IN HISTORY -->
      <div class="border-t border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low p-lg flex justify-between items-center">
        <div>
          <h4 class="text-md font-medium">Danh sách Task (Action Items)</h4>
        </div>
        <el-button type="primary" plain @click="addTask" size="small">
          <span class="material-symbols-outlined text-[16px] mr-1">add</span> Thêm Task
        </el-button>
      </div>
      
      <div class="p-lg bg-white dark:bg-surface">
        <el-table :data="tasks" style="width: 100%" size="large" stripe class="custom-task-table" v-if="tasks && tasks.length > 0">
          <el-table-column type="index" label="#" width="50" align="center" />
          
          <el-table-column label="Tên nhiệm vụ" min-width="250">
            <template #default="{ row }">
              <el-input v-model="row.title" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" resize="none" placeholder="Tên nhiệm vụ" />
            </template>
          </el-table-column>
          
          <el-table-column label="Phân loại" min-width="130">
            <template #default="{ row }">
              <el-select v-model="row.task_type" placeholder="Phân loại">
                <el-option label="Task" value="task" />
                <el-option label="Thông báo" value="noti" />
              </el-select>
            </template>
          </el-table-column>
          
          <el-table-column label="Người thực hiện" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.assignee_display" filterable placeholder="Tìm người...">
                <el-option
                  v-for="item in employeeOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="Dự án" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.project" filterable placeholder="Trống" clearable>
                <el-option
                  v-for="p in getProjectsForHR(row.assignee_display)"
                  :key="p[1]"
                  :label="p[0]"
                  :value="p[1]"
                />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="Bắt đầu" width="160">
            <template #default="{ row }">
              <el-date-picker
                v-model="row.start_date"
                type="date"
                placeholder="Bắt đầu"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </template>
          </el-table-column>

          <el-table-column label="Hạn chót" width="160">
            <template #default="{ row }">
              <el-date-picker
                v-model="row.due_date"
                type="date"
                placeholder="Hạn chót"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </template>
          </el-table-column>

          <el-table-column label="Ghi chú" min-width="250">
            <template #default="{ row }">
              <el-input v-model="row.description" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" resize="none" placeholder="Mô tả chi tiết" />
            </template>
          </el-table-column>

          <el-table-column label="Xóa" width="70" align="center" fixed="right">
            <template #default="{ $index }">
              <el-button type="danger" circle @click="removeTask($index)">
                <span class="material-symbols-outlined text-[16px]">delete</span>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        <div v-else class="text-center py-6 text-gray-500 bg-gray-50 rounded-lg mt-4 border border-dashed border-gray-300">
          Chưa có task nào được trích xuất.
        </div>
      </div>
    </section>

    <!-- STRANGER MAPPING CARD -->
    <section v-if="uniqueSpeakers.length > 0" class="bg-error-container/10 border border-error/20 rounded-xl p-lg shadow-sm">
      <div class="mb-lg border-b border-error/10 pb-md flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 class="font-headline-md text-headline-md text-error mb-xs flex items-center gap-sm">
            <span class="material-symbols-outlined">person_add</span>
            Sửa / Gán tên người tham dự
          </h3>
          <p class="font-body-md text-body-md text-gray-500 dark:text-on-surface-variant">Đã nhận diện <strong>{{ speakerStats.knownCount }}</strong> người, còn <strong>{{ speakerStats.unknownGroupCount }}</strong> nhóm người lạ / <strong>{{ speakerStats.unknownSegments }}</strong> đoạn người lạ.</p>
        </div>
        <span v-if="isAdmin" class="text-[10px] font-bold text-error bg-error/10 px-2 py-0.5 rounded-full border border-error/30 self-start mt-1">ADMIN MODE</span>
      </div>
      <div class="flex flex-col gap-md">
        <div v-for="spk in uniqueSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-md bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant/50 p-md rounded-lg shadow-sm hover:border-primary/50 transition-colors">
          <div class="flex items-center gap-sm min-w-[180px]">
            <div class="w-8 h-8 rounded-full bg-error/10 flex items-center justify-center text-error font-bold text-xs shrink-0">
              <span class="material-symbols-outlined text-[16px]">person</span>
            </div>
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
            :filter-method="(q) => filterSpeakerMapping(spk, q)"
            @visible-change="(v) => onSpeakerSelectVisibleChange(spk, v)"
          >
            <el-option
              v-for="opt in getFilteredEmployeeOptions(spk)"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            >
              <div class="truncate w-full block" :title="opt.label">{{ opt.label }}</div>
            </el-option>
          </el-select>
          <button @click="deleteSpeaker(spk)" class="p-1.5 text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 rounded-lg transition-colors border border-red-200" title="Xóa tên người này khỏi các đoạn hội thoại">
            <span class="material-symbols-outlined text-[18px] block">person_remove</span>
          </button>
        </div>
        <div class="flex justify-end gap-2 mt-sm flex-wrap">
          <button @click="addNewSegment" class="font-medium py-2 px-4 rounded-lg transition-all flex items-center gap-2 text-sm bg-primary/10 text-primary hover:bg-primary/20 border border-primary/30 border-dashed hover:border-primary/60 mr-auto">
            <span class="material-symbols-outlined text-[18px]">person_add</span> Thêm người lạ
          </button>
          <!-- Ai cũng thấy: chỉ gán tên -->
          <button :disabled="!hasSelectedMapping" @click="assignStrangerNames"
            class="font-medium py-2 px-5 rounded-lg transition-all flex items-center gap-2 text-sm"
            :class="hasSelectedMapping ? 'bg-orange-500 text-white hover:bg-orange-600 shadow-sm active:scale-[0.98]' : 'bg-gray-200 text-gray-400 cursor-not-allowed'">
            <span class="material-symbols-outlined text-[18px]">label</span> Gán tên
          </button>
          <!-- CHỈ ADMIN thấy: gán tên + enroll giọng -->
          <button v-if="isAdmin" :disabled="!hasSelectedMapping || isEnrollingMapped || !canRunAudioRescan" @click="enrollMapped" 
            class="font-medium py-2 px-5 rounded-lg transition-all flex items-center gap-2 text-sm" 
            :class="hasSelectedMapping && !isEnrollingMapped && canRunAudioRescan ? 'bg-primary text-white hover:bg-primary/90 shadow-sm active:scale-[0.98]' : 'bg-primary/30 text-white/50 cursor-not-allowed'">
            <span class="material-symbols-outlined text-[18px]">{{ isEnrollingMapped ? 'autorenew' : 'how_to_reg' }}</span>
            {{ isEnrollingMapped ? 'Đang xử lý...' : 'Gán tên & Quét lại AI' }}
          </button>
        </div>
      </div>
    </section>

    <!-- Transcript Section (Adapted from the box style) -->
    <section v-if="localSegments.length > 0" class="bg-white dark:bg-surface-container rounded-xl border border-gray-200 dark:border-outline-variant overflow-hidden shadow-sm">
      <div class="p-lg border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low flex justify-between items-center flex-wrap gap-4">
        <div>
          <h3 class="font-headline-md text-headline-md text-primary flex items-center gap-2">
            <span class="material-symbols-outlined">forum</span> NỘI DUNG HỘI THOẠI
          </h3>
          <p class="text-body-sm text-gray-500 dark:text-on-surface-variant mt-1">{{ t('transcript_desc') }}</p>
        </div>
        <div>
          <div class="flex items-center gap-2 flex-wrap justify-end">
            <button
              @click="rescanFromEditedTranscript"
              :disabled="isRescanning || isNormalizingTranscript || !canRunAudioRescan"
              class="px-4 py-2 rounded-md font-medium flex items-center gap-2 border transition-colors text-sm"
              :class="(isRescanning || isNormalizingTranscript || !canRunAudioRescan) ? 'bg-primary/20 text-primary/50 border-primary/20 cursor-not-allowed' : 'bg-primary text-white border-primary hover:bg-primary/90'"
            >
              <span class="material-symbols-outlined text-[18px]">{{ isRescanning ? 'autorenew' : 'manage_search' }}</span>
              {{ isRescanning ? 'Đang quét lại...' : 'Quét lại AI theo tên đã sửa' }}
            </button>
            <button
              @click="normalizeTranscript"
              :disabled="isRescanning || isNormalizingTranscript || !canNormalizeTranscript"
              class="px-4 py-2 rounded-md font-medium flex items-center gap-2 border transition-colors text-sm"
              :class="(isRescanning || isNormalizingTranscript || !canNormalizeTranscript) ? 'bg-orange-200 text-orange-400 border-orange-200 cursor-not-allowed' : 'bg-orange-500 text-white border-orange-500 hover:bg-orange-600'"
            >
              <span class="material-symbols-outlined text-[18px]">{{ isNormalizingTranscript ? 'autorenew' : 'format_line_spacing' }}</span>
              {{ isNormalizingTranscript ? 'Đang chuẩn hoá...' : 'Chuẩn hoá hội thoại' }}
            </button>
            <button @click="undoAction" :disabled="undoStack.length === 0" class="px-4 py-2 rounded-md font-medium flex items-center gap-2 border border-gray-300 dark:border-outline-variant hover:bg-gray-100 dark:hover:bg-surface-variant transition-colors text-sm" :class="undoStack.length === 0 ? 'text-gray-400 cursor-not-allowed opacity-50' : 'text-gray-900 dark:text-on-surface'">
            <span class="material-symbols-outlined text-[18px]">undo</span> Hoàn tác
            </button>
          </div>
          <p class="text-xs text-orange-600 dark:text-orange-300 mt-2 text-right">
            Chỉ bấm <strong>Chuẩn hoá hội thoại</strong> khi bạn đã chắc transcript và tên người nói đều đúng, và không còn người lạ.
          </p>
          <p v-if="!canRunAudioRescan" class="text-xs text-red-500 dark:text-red-300 mt-1 text-right">
            Meeting này không có audio gốc nên các nút quét lại AI sẽ bị khóa.
          </p>
        </div>
      </div>
      <div class="p-lg bg-white dark:bg-surface">
        <div class="transcript-log max-h-[600px] overflow-auto flex flex-col gap-4 pr-2">
          <div v-for="(seg, idx) in localSegments" :key="idx" class="relative border-l-2 border-gray-300 dark:border-outline-variant pl-4 py-1 group">
            <div class="absolute -left-[5px] top-3 w-2 h-2 rounded-full bg-primary/50"></div>
            
            <div class="flex items-center gap-2 mb-1 flex-wrap">
              <template v-if="editingSpeaker === idx">
                <el-select v-model="newSpeakerEmployee" filterable clearable allow-create default-first-option placeholder="Chọn hoặc nhập tên..." size="small" style="width: 190px; --el-fill-color-blank: transparent;" class="custom-el-override" :filter-method="filterNewSpeakerEmployee" @visible-change="onNewSpeakerSelectVisibleChange">
                  <el-option v-for="opt in filteredNewSpeakerOptions" :key="opt.value" :label="opt.label" :value="opt.value">
                    <div class="truncate w-full block" :title="opt.label">{{ opt.label }}</div>
                  </el-option>
                </el-select>
                <button @click="saveEditSpeaker(idx)" class="text-xs font-bold text-white bg-primary px-2 py-0.5 rounded hover:bg-primary/90 ml-1">Lưu</button>
                <button @click="saveAndRescanSpeaker(idx)" :disabled="!canRunAudioRescan" class="text-xs font-bold text-white bg-orange-500 px-2 py-0.5 rounded hover:bg-orange-600 transition-colors flex items-center gap-0.5 disabled:opacity-50 disabled:cursor-not-allowed" title="Học giọng từ đoạn này và gán lại tên cho tất cả đoạn giống giọng">
                  <span class="material-symbols-outlined text-[12px]">manage_search</span>
                  Quét lại AI
                </button>
                <button @click="editingSpeaker = null" class="text-xs text-gray-400 hover:text-gray-600">Hủy</button>
              </template>
              <template v-else>
                <span class="font-bold text-sm tracking-wide cursor-pointer hover:underline" @click="startEditSpeaker(idx)" :class="seg[2] && seg[2].includes('Người lạ') ? 'text-red-600' : ''" :style="seg[2] && !seg[2].includes('Người lạ') ? { color: stringToColor(seg[2]) } : {}">{{ seg[2] || 'Không tên' }}</span>
                <span class="text-xs text-gray-500 dark:text-on-surface-variant font-label-caps">[{{ formatTime(seg[0]) }}]</span>
                <span class="material-symbols-outlined text-[13px] text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-primary ml-0.5" @click="startEditSpeaker(idx)" title="Đổi tên">edit</span>
                <span class="material-symbols-outlined text-[13px] text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-green-500 ml-1" @click="insertSegmentAfter(idx)" title="Chèn đoạn hội thoại mới xuống dưới">add_circle</span>
                <span class="material-symbols-outlined text-[13px] text-gray-300 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer hover:text-error ml-1" @click="deleteSegment(idx)" title="Xóa đoạn hội thoại này">delete</span>
              </template>
            </div>
            
            <template v-if="editingIdx === idx">
              <textarea v-model="editingText" class="w-full border border-primary/50 rounded-lg px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:border-primary resize-none bg-white dark:bg-surface mt-1" rows="3" @keydown.ctrl.enter="saveEditText(idx)" @keyup.esc="editingIdx = null"></textarea>
              <div class="flex gap-2 mt-1">
                <button @click="saveEditText(idx)" class="text-xs font-bold text-white bg-primary px-3 py-1 rounded hover:bg-primary/90">Lưu (Ctrl+Enter)</button>
                <button @click="editingIdx = null" class="text-xs text-gray-500 hover:text-gray-700 px-2 py-1 rounded border border-gray-300 hover:bg-gray-50">Hủy</button>
              </div>
            </template>
            <template v-else>
              <p class="text-sm leading-relaxed text-gray-900 dark:text-on-surface whitespace-pre-wrap break-words m-0 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/10 rounded px-1 -mx-1" @click="startEditText(idx)">{{ seg[3] || '(Nhập nội dung hội thoại...)' }}</p>
            </template>
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
