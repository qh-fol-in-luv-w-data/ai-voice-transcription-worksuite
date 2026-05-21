<script setup>
import { ref, onMounted, watch } from 'vue'
import { transcribeAudio, extractTasks, syncTasksToERP, getElevenLabsInfo, enrollVoice, getEnrolledSpeakers, getMeetingHistory, cleanTranscript, updateMeetingResults } from './api'
import { initSession, useSession } from './utils/session'
import CTSplashScreen from './components/CTSplashScreen.vue'
import CTAccessDenied from './components/CTAccessDenied.vue'

// Session
const { authState, currentUser, currentFullName } = useSession()

// States

// States
const audioFile = ref(null)
const language = ref('vi')
const modelType = ref('gpt-4o')

const isTranscribing = ref(false)
const transcribeStatus = ref('')
const transcriptResults = ref([]) // Raw tuples [start, end, spk, txt]
const originalTranscriptResults = ref([]) // Store original results for undo
const isCleaned = ref(false)
const transcriptText = ref('')    // Formatted text

const isExtracting = ref(false)
const extractStatus = ref('')
const isCleaning = ref(false)
const docxUrl = ref('')
const excelUrl = ref('')

const tasks = ref([])
const hrProjectsMap = ref({})
const dbEmployees = ref([])
const voiceDbSpeakers = ref([]) // Danh sách giọng đăng ký trong Voice DB
const selectedAttendees = ref([]) // Người được chọn tham dự cuộc họp
const newAttendeeName = ref('') // Tên thêm thủ công
const isReanalyzing = ref(false)
const isSyncing = ref(false)
const erpStatus = ref('')

const activeTab = ref('transcribe') // 'transcribe' | 'enroll' | 'history' | 'view_meeting'

const meetingHistory = ref([])
const currentMeetingName = ref(null)
const currentMeeting = ref(null)

const loadPastMeeting = (meeting) => {
  currentMeeting.value = meeting
  activeTab.value = 'view_meeting'
}

const enrollAudioFile = ref(null)
const enrollStatus = ref('')
const isEnrolling = ref(false)

const isRecording = ref(false)
const mediaRecorder = ref(null)
const audioChunks = ref([])
const recordedAudioUrl = ref('')

const languages = [
  { val: 'vi', label: 'Tiếng Việt' },
  { val: 'en', label: 'English' },
  { val: 'ja', label: '日本語' },
  { val: 'zh', label: '中文' },
  { val: 'ko', label: '한국어' },
  { val: 'auto', label: 'Auto detect' }
]

const isDark = ref(true)
const toggleDark = () => { isDark.value = !isDark.value }

watch(isDark, (val) => {
  if (val) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}, { immediate: true })

const uiLang = ref('vi')
const toggleLang = () => { uiLang.value = uiLang.value === 'vi' ? 'en' : 'vi' }

const dict = {
  vi: {
    title: "Phiên bản Tiên tiến",
    audio_processing: "Xử lý Âm thanh",
    audio_desc: "Tải lên file ghi âm để dịch và nhận diện người nói.",
    upload_empty: "Chọn hoặc thả file âm thanh vào đây",
    upload_support: "Hỗ trợ: MP3, WAV, M4A tối đa 50MB",
    target_lang: "Ngôn ngữ",
    analyze_voice: "Phân tích Giọng nói",
    reanalyze_voice: "Phân tích lại",
    attendees_title: "Người tham dự cuộc họp",
    attendees_desc: "Chọn những người có mặt trong cuộc họp để hệ thống nhận diện chính xác hơn.",
    attendees_placeholder: "Chọn người tham dự...",
    attendees_selected: (n) => `Đã chọn ${n} người`,
    btn_reanalyze: "Phân tích lại với danh sách này",
    reanalyzing: "Đang phân tích lại...",
    extract_task: "Trích xuất Task",
    analyzing: "Đang phân tích...",
    extracting: "Đang trích xuất...",
    transcript_result: "Nội dung cuộc họp",
    transcript_desc: "Nội dung cuộc họp và danh tính người nói.",
    empty_audio: "Chưa có dữ liệu âm thanh nào được tải lên...",
    task_list: "Danh sách Nhiệm vụ",
    task_desc: "Kiểm tra và hiệu chỉnh trước khi đồng bộ lên hệ thống ERPNext.",
    export_xlsx: "Xuất Task",
    export_docx: "Xuất Biên bản họp",
    add_task: "Thêm Task",
    col_name: "Tên nhiệm vụ",
    col_assignee: "Người thực hiện",
    col_project: "Dự án",
    col_start: "Bắt đầu",
    col_due: "Hạn chót",
    col_desc: "Mô tả chi tiết",
    col_del: "Xóa",
    btn_sync: "Đồng bộ lên ERPNext",
    status_transcribe_wait: "⏳ Đang khởi tạo máy chủ phân tích...",
    status_transcribe_ok: "✅ Dịch và nhận diện thành công!",
    status_extract_wait: "⏳ Đang trích xuất nhiệm vụ qua AI...",
    status_extract_ok: "✅ Trích xuất nhiệm vụ thành công!",
    status_sync_wait: "⏳ Đang đồng bộ dữ liệu lên ERPNext...",
    status_sync_ok: (c, e) => `✅ Đã đồng bộ: ${c} nhiệm vụ. Lỗi: ${e}`,
    status_sync_fail: "❌ Đồng bộ thất bại: ",
    alert_no_file: "Vui lòng chọn file âm thanh!",
    alert_no_transcript: "Chưa có nội dung hội thoại!",
    error_connect: "❌ Lỗi kết nối",
    empty_project: "-- Trống --",
    tab_transcribe: "Phân tích Hội thoại",
    tab_enroll: "Đăng ký Giọng nói",
    enroll_title: "Đăng ký Giọng nói",
    enroll_desc: "Thu âm hoặc tải lên giọng nói. Hệ thống tự động liên kết với tài khoản đang đăng nhập.",
    btn_record: "Bắt đầu thu âm",
    btn_stop: "Dừng thu âm",
    btn_enroll: "Đăng ký Hệ thống"
  },
  en: {
    title: "Advanced Edition",
    audio_processing: "Audio Processing",
    audio_desc: "Upload an audio file to transcribe and identify speakers.",
    upload_empty: "Click or drag audio file here",
    upload_support: "Supports: MP3, WAV, M4A up to 50MB",
    target_lang: "Language",
    analyze_voice: "Analyze Voice",
    reanalyze_voice: "Re-analyze",
    attendees_title: "Meeting Attendees",
    attendees_desc: "Select who was in the meeting for more accurate speaker identification.",
    attendees_placeholder: "Select attendees...",
    attendees_selected: (n) => `${n} selected`,
    btn_reanalyze: "Re-analyze with selected attendees",
    reanalyzing: "Re-analyzing...",
    extract_task: "Extract Tasks",
    analyzing: "Analyzing...",
    extracting: "Extracting...",
    transcript_result: "Meeting Content",
    transcript_desc: "Meeting content and speaker identities.",
    empty_audio: "No audio data uploaded yet...",
    task_list: "Task List",
    task_desc: "Review and edit before syncing to ERPNext system.",
    export_xlsx: "Export Task",
    export_docx: "Export Minutes",
    add_task: "Add Task",
    col_name: "Task Name",
    col_assignee: "Assignee",
    col_project: "Project",
    col_start: "Start Date",
    col_due: "Due Date",
    col_description: "Description",
    col_del: "Delete",
    btn_sync: "Sync to ERPNext",
    status_transcribe_wait: "⏳ Initializing analysis server...",
    status_transcribe_ok: "✅ Translation and identification successful!",
    status_extract_wait: "⏳ Extracting tasks via AI...",
    status_extract_ok: "✅ Tasks extracted successfully!",
    status_sync_wait: "⏳ Syncing data to ERPNext...",
    status_sync_ok: (c, e) => `✅ Synced: ${c} tasks. Errors: ${e}`,
    status_sync_fail: "❌ Sync failed: ",
    alert_no_file: "Please select an audio file!",
    alert_no_transcript: "No conversation content available!",
    error_connect: "❌ Connection error",
    empty_project: "-- Empty --",
    tab_transcribe: "Transcribe Voice",
    tab_enroll: "Voice Enrollment",
    enroll_title: "Voice Enrollment",
    enroll_desc: "Record or upload your voice. The system will automatically link it to your current account.",
    btn_record: "Start Recording",
    btn_stop: "Stop Recording",
    btn_enroll: "Enroll Voice"
  }
}

const t = (key) => dict[uiLang.value][key] || key

// Actions
const checkBalance = async () => {
  try {
    const info = await getElevenLabsInfo()
    console.log(`Số dư ElevenLabs: ${info.balance}`)
  } catch (e) {
    console.error("Lỗi check số dư")
  }
}

const handleFileChange = (e) => {
  if (e.target.files.length > 0) {
    audioFile.value = e.target.files[0]
  }
}

const handleEnrollFileChange = (e) => {
  if (e.target.files.length > 0) {
    enrollAudioFile.value = e.target.files[0]
    recordedAudioUrl.value = ''
  }
}

const toggleRecording = async () => {
  if (isRecording.value) {
    mediaRecorder.value.stop()
    isRecording.value = false
    return
  }
  
  try {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("Trình duyệt không hỗ trợ hoặc bạn đang truy cập bằng HTTP. Vui lòng sử dụng HTTPS để cấp quyền Micro.");
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mediaRecorder.value = new MediaRecorder(stream)
    audioChunks.value = []
    
    mediaRecorder.value.ondataavailable = e => {
      if (e.data.size > 0) audioChunks.value.push(e.data)
    }
    
    mediaRecorder.value.onstop = () => {
      const blob = new Blob(audioChunks.value, { type: 'audio/wav' })
      enrollAudioFile.value = blob
      enrollAudioFile.value.name = 'recorded_audio.wav'
      recordedAudioUrl.value = URL.createObjectURL(blob)
      stream.getTracks().forEach(t => t.stop())
    }
    
    mediaRecorder.value.start()
    isRecording.value = true
  } catch(e) {
    alert("Lỗi truy cập Micro: " + e.message)
  }
}

const submitEnrollment = async () => {
  if (!enrollAudioFile.value) {
    alert(t('alert_no_file'))
    return
  }
  isEnrolling.value = true
  enrollStatus.value = "⏳ Đang đăng ký..."
  
  try {
    const msg = await enrollVoice(enrollAudioFile.value)
    enrollStatus.value = "✅ " + msg
  } catch(e) {
    if (e.response?.data?.message) {
      enrollStatus.value = "❌ " + e.response.data.message
    } else {
      enrollStatus.value = "❌ " + t('error_connect')
    }
  } finally {
    isEnrolling.value = false
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

const reAnalyzeWithAttendees = async () => {
  if (!audioFile.value || selectedAttendees.value.length === 0) return
  isReanalyzing.value = true
  transcribeStatus.value = t('reanalyzing')
  
  try {
    const res = await transcribeAudio(audioFile.value, language.value, selectedAttendees.value)
    if (res.status === 'success') {
      transcribeStatus.value = t('status_transcribe_ok')
      transcriptResults.value = res.results
      originalTranscriptResults.value = [...res.results]
      isCleaned.value = false
      transcriptText.value = res.final_text
      currentMeetingName.value = res.meeting_name || currentMeetingName.value
    } else {
      transcribeStatus.value = '❌ Error: ' + res.message
    }
  } catch (e) {
    transcribeStatus.value = t('error_connect')
  } finally {
    isReanalyzing.value = false
  }
}


const addCustomAttendee = () => {
  const name = newAttendeeName.value.trim()
  if (name && !selectedAttendees.value.includes(name)) {
    selectedAttendees.value.push(name)
  }
  newAttendeeName.value = ''
}

const removeAttendee = (name) => {
  selectedAttendees.value = selectedAttendees.value.filter(n => n !== name)
}

const toggleAttendee = (name) => {
  if (selectedAttendees.value.includes(name)) {
    removeAttendee(name)
  } else {
    selectedAttendees.value.push(name)
  }
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

const startCleanTranscript = async () => {
  if (isCleaned.value) {
    // Hoàn tác lọc — khôi phục kết quả gốc
    transcriptResults.value = [...originalTranscriptResults.value]
    isCleaned.value = false
    // Cập nhật raw_results trong Meeting về dữ liệu gốc
    if (currentMeetingName.value) {
      try {
        await updateMeetingResults(currentMeetingName.value, originalTranscriptResults.value)
      } catch(e) {
        console.warn('Could not update meeting results on undo', e)
      }
    }
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

const addTask = () => {
  tasks.value.push({
    title: '',
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

const getProjectsForHR = (displayStr) => {
  if (!displayStr) return []
  // Extract HR code e.g. "Nguyen Van A (HR-EMP-001)"
  const match = displayStr.match(/\((HR[-_]EMP[-_][^)]+)\)/i)
  let hrCode = ''
  if (match) hrCode = match[1]
  else if (displayStr.startsWith('HR_EMP_') || displayStr.startsWith('HR-EMP-')) hrCode = displayStr.trim()
  
  return hrProjectsMap.value[hrCode] || []
}

const syncToERP = async () => {
  if (tasks.value.length === 0) return
  isSyncing.value = true
  erpStatus.value = t('status_sync_wait')
  
  try {
    const res = await syncTasksToERP(tasks.value)
    if (res.status === 'success') {
      const report = res.report
      const created = report.created_tasks ? report.created_tasks.length : 0
      const errs = report.errors ? report.errors.length : 0
      erpStatus.value = dict[uiLang.value].status_sync_ok(created, errs)
    } else {
      erpStatus.value = t('status_sync_fail') + res.message
    }
  } catch (e) {
    erpStatus.value = t('error_connect')
  } finally {
    isSyncing.value = false
  }
}

const fetchEnrolledSpeakers = async () => {
  try {
    const res = await getEnrolledSpeakers()
    if (res.status === 'success') {
      voiceDbSpeakers.value = res.speakers || []
    }
  } catch (e) {
    console.error("Failed to load Voice DB speakers", e)
  }
}

const loadHistory = async () => {
  try {
    const res = await getMeetingHistory()
    if (res && res.status === 'success') {
      meetingHistory.value = res.meetings || []
    }
  } catch (e) {
    console.error("Failed to load meeting history", e)
  }
}

const currentLocalDate = () => {
  const d = new Date()
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const year = d.getFullYear()
  return `${day}-${month}-${year}`
}

const parseMeetingSegments = (rawResults) => {
  if (!rawResults) return [];
  try {
    return typeof rawResults === 'string' ? JSON.parse(rawResults) : rawResults;
  } catch(e) {
    return [];
  }
}

/**
 * Tải file qua BE endpoint (tránh vấn đề xác thực của đường dẫn trực tiếp)
 * @param {string} meetingName  - tên meeting (VD: MEETING-0001)
 * @param {'docx'|'xlsx'} fileType
 */
const downloadViaBackend = (meetingName, fileType) => {
  if (!meetingName) return;
  const url = `/api/method/voice_app.api.download_meeting_file?meeting_name=${encodeURIComponent(meetingName)}&file_type=${fileType}`;
  const a = document.createElement('a');
  a.href = url;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  setTimeout(() => document.body.removeChild(a), 200);
}

onMounted(async () => {
  await initSession('/api/method/voice_app.api.get_context')
  if (authState.value !== 'authorized') return

  checkBalance()
  try {
    const res = await getEnrolledSpeakers()
    if (res && res.speakers) voiceDbSpeakers.value = res.speakers
  } catch(e) { console.warn('Could not load enrolled speakers', e) }
  
  loadHistory()
})
</script>

<template>
  <CTSplashScreen v-if="authState === 'loading'" />
  <CTAccessDenied v-else-if="authState === 'denied'" />
  <div v-else class="flex h-screen w-full bg-background overflow-hidden text-foreground">
  
    <!-- SIDEBAR -->
    <aside class="w-[260px] border-r border-border bg-muted/10 flex flex-col h-full shrink-0">
      <!-- Logo -->
      <div class="h-16 flex items-center px-6 border-b border-border">
         <h1 class="font-bold text-lg tracking-tight" style="color: hsl(var(--foreground));">AI CT Worksuit <span class="text-muted-foreground font-normal text-sm">v3.0</span></h1>
      </div>

      <!-- Navigation Menu -->
      <div class="p-4 flex-1 overflow-y-auto space-y-8">
        
        <!-- Module Group 1 -->
        <div>
          <span class="text-[11px] font-bold text-muted-foreground uppercase tracking-wider mb-2 block px-2">Audio Intelligence</span>
          <ul class="space-y-1" style="list-style-type: none; margin: 0; padding: 0;">
            <li>
              <button @click="activeTab='transcribe'" :class="activeTab==='transcribe' ? 'text-primary font-medium' : 'text-muted-foreground hover:bg-muted/30'" class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors text-left bg-transparent border-none shadow-none focus:outline-none cursor-pointer" style="background: none; border: none; box-shadow: none;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg>
                {{ t('tab_transcribe') }}
              </button>
            </li>
            <li>
              <button @click="activeTab='enroll'" :class="activeTab==='enroll' ? 'text-primary font-medium' : 'text-muted-foreground hover:bg-muted/30'" class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors text-left bg-transparent border-none shadow-none focus:outline-none cursor-pointer" style="background: none; border: none; box-shadow: none;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><line x1="19" x2="19" y1="8" y2="14"></line><line x1="22" x2="16" y1="11" y2="11"></line></svg>
                {{ t('tab_enroll') }}
              </button>
            </li>
          </ul>
        </div>

        <!-- Module Group 2: History -->
        <div class="mt-8" v-if="meetingHistory.length > 0">
          <span class="text-[11px] font-bold text-muted-foreground uppercase tracking-wider mb-2 block px-2">Lịch sử cuộc họp</span>
          <ul class="space-y-1" style="list-style-type: none; margin: 0; padding: 0;">
            <li v-for="meeting in meetingHistory" :key="meeting.name">
              <button @click="loadPastMeeting(meeting)" :class="activeTab==='view_meeting' && currentMeeting?.name === meeting.name ? 'bg-muted/30 text-primary font-medium' : 'text-muted-foreground hover:bg-muted/30'" class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors text-left bg-transparent border-none shadow-none focus:outline-none cursor-pointer" style="background: none; border: none; box-shadow: none;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-history shrink-0"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
                <span class="truncate block w-full">{{ meeting.title }}</span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </aside>

    <!-- MAIN CONTENT -->
    <div class="flex-1 flex flex-col h-full overflow-hidden relative">
      
      <!-- Topbar -->
      <header class="h-[72px] w-full flex items-center justify-end px-8 border-b border-border bg-background/80 backdrop-blur shrink-0 z-40">
        <div class="flex items-center gap-6">
          <!-- Toggle Buttons -->
          <button @click="toggleDark" class="btn-ghost-icon" style="color: hsl(var(--foreground));">
            <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>
            <svg v-else xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>
          </button>
          <button @click="toggleLang" class="btn-ghost-icon font-bold text-base" style="color: hsl(var(--foreground)); width: 36px;">
            {{ uiLang === 'vi' ? 'EN' : 'VI' }}
          </button>

          <div v-if="currentUser === 'Guest'" class="flex items-center gap-3 bg-muted/30 px-4 py-2 rounded-full border border-border">
             <div class="avatar" style="width:32px; height:32px; background: hsl(var(--primary)); border-radius: 50%;"></div>
             <span class="text-sm font-medium">Guest</span>
          </div>
          <div v-else class="flex items-center gap-3 bg-muted/30 px-4 py-2 rounded-full border border-border">
             <div class="avatar flex items-center justify-center font-bold text-white bg-primary" style="width:32px; height:32px; border-radius: 50%;">
                {{ currentFullName.charAt(0).toUpperCase() }}
             </div>
             <div class="flex flex-col">
                <span class="text-sm font-bold leading-tight">{{ currentFullName }}</span>
                <span class="text-xs text-muted-foreground leading-tight">{{ currentUser }}</span>
             </div>
          </div>
        </div>
      </header>

      <!-- Scrollable content area -->
      <main class="flex-1 overflow-y-auto p-6 bg-muted/5 relative">
      <template v-if="activeTab === 'transcribe'">
        <div class="w-full flex flex-col gap-8 pb-10 mt-2">
          <!-- TRANSCRIBE SETTINGS CARD -->
          <div class="shadcn-card glow-effect">
            <div class="card-header border-b border-border bg-muted/10">
              <h3 class="card-title">{{ t('audio_processing') }}</h3>
              <p class="card-description">{{ t('audio_desc') }}</p>
            </div>
            
            <div class="card-content flex flex-col gap-6 mt-6">
               <div class="flex flex-col gap-1.5">
                 <label class="text-xs font-bold text-muted-foreground uppercase tracking-wider">{{ t('target_lang') }}</label>
                 <select v-model="language" class="h-10 bg-transparent max-w-xs cursor-pointer font-medium transition-colors" style="color: inherit; background: transparent url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23888888' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E&quot;) no-repeat right center; background-size: 16px; padding-right: 24px; border: none; outline: none; box-shadow: none; padding-left: 0; font-size: 1rem; -webkit-appearance: none; -moz-appearance: none; appearance: none;">
                   <option v-for="l in languages" :key="l.val" :value="l.val">{{ l.label }}</option>
                 </select>
               </div>
               
               <div class="h-px bg-border my-2"></div>
               
               <div class="upload-zone" :class="{ 'active': audioFile }">
                 <input type="file" id="audio-upload" @change="handleFileChange" accept="audio/*" class="hidden-input" />
                 <label for="audio-upload" class="upload-label py-12">
                   <svg class="mb-4 text-muted-foreground" xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96M14 13v4h-4v-4H7l5-5 5 5z"></path></svg>
                   <p class="text-base font-medium mb-1">Drag & drop a file here, or click to select</p>
                   <span class="upload-primary-text text-sm">{{ audioFile ? audioFile.name : t('upload_support') }}</span>
                 </label>
               </div>
            </div>
            
            <div class="card-footer border-t border-border bg-muted/20 flex flex-col gap-3 mt-4">
               <button @click="startTranscribe" :disabled="isTranscribing || !audioFile" class="shadcn-btn shadcn-btn-primary w-full h-12 text-lg">
                  {{ isTranscribing ? t('analyzing') : t('analyze_voice') }}
               </button>
               <div v-if="transcribeStatus && !isTranscribing" class="text-center text-sm font-medium mt-1 text-primary">
                  {{ transcribeStatus }}
               </div>
            </div>
          </div>
          
          <!-- EXTRACT BUTTON ROW -->
          <div v-if="transcriptResults.length > 0" class="flex justify-end mt-4">
              <button @click="startExtractTasks" :disabled="isExtracting || transcriptResults.length === 0" class="shadcn-btn shadcn-btn-outline w-full max-w-[300px]" :style="{ opacity: transcriptResults.length === 0 ? 0.5 : 1 }">
                 <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="mr-2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon></svg>
                 {{ isExtracting ? t('extracting') : t('extract_task') }}
              </button>
          </div>
          <div v-if="extractStatus" class="text-primary text-sm font-medium text-center bg-primary/10 py-2 rounded-md border border-primary/20">
             {{ extractStatus }}
          </div>
          
          <!-- TRANSCRIPT RESULTS -->
          <div v-if="transcriptResults.length > 0" class="shadcn-card">
            <div class="card-header border-b border-border flex justify-between items-center bg-muted/10">
              <div>
                <h3 class="card-title">{{ t('transcript_result') }}</h3>
                <p class="card-description">{{ t('transcript_desc') }}</p>
              </div>
              <button @click="startCleanTranscript" :disabled="isCleaning" class="shadcn-btn shadcn-btn-outline h-8 px-3 text-xs" :class="{'border-primary text-primary': isCleaned}">
                 <svg v-if="!isCleaning && !isCleaned" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16"/><path d="M16 16h5v5"/></svg>
                 <svg v-else-if="!isCleaning && isCleaned" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M3 7v6h6"/><path d="M21 17v-6h-6"/><path d="M18.37 7.63A9 9 0 0 0 5.41 5.41L3 8"/><path d="M5.63 16.37A9 9 0 0 0 18.59 18.59L21 16"/></svg>
                 <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                 {{ isCleaning ? 'Đang xử lý...' : (isCleaned ? 'Hoàn tác Lọc' : 'AI Lọc hội thoại') }}
              </button>
            </div>
            <div class="card-content p-0">
               <div class="log-view p-6 space-y-6 max-h-[250px] overflow-auto">
                  <div v-for="(seg, idx) in transcriptResults" :key="idx" class="log-entry">
                     <div class="log-meta">
                        <span class="log-speaker">{{ seg[2] }}</span>
                        <span class="log-time">[{{ seg[0].toFixed(2) }}s]</span>
                     </div>
                     <p class="log-text">{{ seg[3] }}</p>
                  </div>
               </div>
            </div>
          </div>

          <!-- ATTENDEES PANEL -->
          <div v-if="transcriptResults.length > 0" class="shadcn-card" style="border-color: hsl(var(--primary)/0.3);">
            <div class="card-header border-b border-border" style="background: hsl(var(--primary)/0.05);">
              <div class="flex-between">
                <div>
                  <h3 class="card-title flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                    {{ t('attendees_title') }}
                  </h3>
                  <p class="card-description">{{ t('attendees_desc') }}</p>
                </div>
                <button
                  v-if="selectedAttendees.length > 0"
                  @click="reAnalyzeWithAttendees"
                  :disabled="isReanalyzing || !audioFile"
                  class="shadcn-btn shadcn-btn-primary"
                >
                  <svg v-if="!isReanalyzing" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                  {{ isReanalyzing ? t('reanalyzing') : t('btn_reanalyze') }}
                </button>
              </div>
            </div>
            <div class="card-content p-4">
              <div class="flex flex-wrap items-center gap-2">
                <!-- Tags -->
                <span
                  v-for="name in selectedAttendees"
                  :key="name"
                  class="attendee-chip attendee-chip--active"
                >
                  <span class="attendee-avatar">{{ name.charAt(0).toUpperCase() }}</span>
                  <span>{{ name }}</span>
                  <button @click="removeAttendee(name)" class="attendee-remove" title="Xóa">
                    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                  </button>
                </span>

                <!-- Dropdown (Searchable Input) -->
                <input
                  list="voice_db_speakers_list"
                  @change="(e) => { 
                    const val = e.target.value.trim();
                    if(val) { 
                      const valid = voiceDbSpeakers.find(s => s.speaker_name === val);
                      if (valid) {
                        toggleAttendee(val);
                      }
                      e.target.value = '';
                    }
                  }"
                  :disabled="voiceDbSpeakers.length === 0"
                  class="attendee-add-input cursor-text"
                  :placeholder="voiceDbSpeakers.length > 0 ? '+ Tìm & thêm người...' : 'Trống'"
                />
                <datalist id="voice_db_speakers_list">
                  <option
                    v-for="spk in voiceDbSpeakers"
                    :key="spk.speaker_name"
                    :value="spk.speaker_name"
                  >{{ spk.email ? spk.email : '' }}</option>
                </datalist>
              </div>
              
              <p v-if="selectedAttendees.length === 0" class="text-xs text-muted-foreground italic mt-3">Chưa chọn ai. Thêm người vào danh sách để phân tích chính xác hơn.</p>
            </div>
          </div>

          <!-- TASK EXTRACTOR -->
          <div v-if="transcriptResults.length > 0" class="shadcn-card">
             <div class="card-header border-b border-border flex-between bg-muted/10">
                <div>
                  <h3 class="card-title">{{ t('task_list') }}</h3>
                  <p class="card-description">{{ t('task_desc') }}</p>
                </div>
                <div class="flex gap-2">
                  <button v-if="excelUrl && currentMeetingName" @click="downloadViaBackend(currentMeetingName, 'xlsx')" class="shadcn-btn shadcn-btn-ghost">
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                     {{ t('export_xlsx') }}
                  </button>
                  <button v-if="docxUrl && currentMeetingName" @click="downloadViaBackend(currentMeetingName, 'docx')" class="shadcn-btn shadcn-btn-ghost">
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                     {{ t('export_docx') }}
                  </button>
                  <button @click="addTask" class="shadcn-btn shadcn-btn-outline">
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                     {{ t('add_task') }}
                  </button>
                </div>
             </div>
             <div class="card-content p-0 bg-background" style="max-height: 60vh; overflow-y: auto;">
                <table class="shadcn-table w-full text-sm">
                   <thead class="bg-muted/20 border-b border-border sticky top-0 z-10">
                      <tr>
                         <th class="p-4 text-left font-medium text-muted-foreground w-12">#</th>
                         <th class="p-4 text-left font-medium text-muted-foreground min-w-[250px]">{{ t('col_name') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground min-w-[180px]">{{ t('col_assignee') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground min-w-[200px]">{{ t('col_project') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-40">{{ t('col_start') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-40">{{ t('col_due') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground min-w-[350px]">{{ t('col_desc') }}</th>
                         <th class="p-4 text-center font-medium text-muted-foreground w-16">{{ t('col_del') }}</th>
                      </tr>
                   </thead>
                   <tbody>
                      <tr v-for="(task, idx) in tasks" :key="idx" class="border-b border-border hover:bg-muted/10 transition-colors">
                         <td class="p-4 font-mono text-xs text-muted-foreground">{{ idx + 1 }}</td>
                         <td class="p-3"><input v-model="task.title" :title="task.title" class="shadcn-table-input" /></td>
                         <td class="p-3">
                           <input
                             v-model="task.assignee_display"
                             list="erp_employee_list"
                             :title="task.assignee_display"
                             class="shadcn-table-input"
                             placeholder="Tìm người thực hiện..."
                           />
                         </td>
                         <td class="p-3">
                            <select v-model="task.project" class="shadcn-table-select">
                              <option value="">{{ t('empty_project') }}</option>
                              <option v-for="p in getProjectsForHR(task.assignee_display)" :key="p[1]" :value="p[1]">
                                {{ p[0] }}
                              </option>
                            </select>
                         </td>
                         <td class="p-3"><input v-model="task.start_date" type="date" class="shadcn-table-input px-2" /></td>
                         <td class="p-3"><input v-model="task.due_date" type="date" class="shadcn-table-input px-2" /></td>
                         <td class="p-3"><textarea v-model="task.description" class="shadcn-table-input resize-y min-h-[80px] py-2"></textarea></td>
                         <td class="p-4 text-center">
                            <button @click="removeTask(idx)" class="btn-ghost-icon text-destructive hover:bg-destructive/10">
                               <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
                            </button>
                         </td>
                      </tr>
                   </tbody>
                </table>
                <datalist id="erp_employee_list">
                  <option v-for="emp in dbEmployees" :key="emp.name" :value="emp.employee_name + ' (' + emp.name + ')'">{{ emp.user_id ? emp.user_id : '' }}</option>
                </datalist>
             </div>
             <div class="card-footer border-t border-border bg-muted/20 flex-between">
                <span class="text-sm text-muted-foreground font-mono" v-if="erpStatus">{{ erpStatus }}</span>
                <span v-else></span>
                <button @click="syncToERP" :disabled="isSyncing || tasks.length === 0" class="shadcn-btn shadcn-btn-primary">
                   {{ t('btn_sync') }}
                </button>
             </div>
          </div>
        </div>
      </template>

      <template v-if="activeTab === 'enroll'">
         <div class="w-full flex flex-col gap-8 pb-10 mt-2">
            <div class="shadcn-card glow-effect">
                <div class="card-header border-b border-border bg-muted/10">
                   <h3 class="card-title">{{ t('enroll_title') }}</h3>
                   <p class="card-description">{{ t('enroll_desc') }}</p>
                </div>
                
                <div class="card-content flex flex-col gap-6 mt-6">
                    <div class="reading-script bg-muted/20 p-4 rounded-md border border-border mt-2">
                       <h4 class="text-sm font-bold text-primary mb-2">Văn bản mẫu (đọc to và rõ ràng):</h4>
                       <p class="text-sm text-muted-foreground italic leading-relaxed">
                          "Chào hệ thống, tôi đang thực hiện ghi âm để cung cấp mẫu dữ liệu giọng nói cho trợ lý AI. 
                          Việc cung cấp một đoạn âm thanh rõ ràng và tự nhiên sẽ giúp AI dễ dàng nhận diện và phân biệt được giọng nói 
                          của tôi trong các cuộc họp trực tuyến hoặc khi thảo luận công việc với đồng nghiệp. 
                          Tôi hy vọng đoạn ghi âm này đủ độ dài và chi tiết để hệ thống học được các đặc trưng riêng biệt trong chất giọng của tôi."
                       </p>
                    </div>
                
                    <button @click="toggleRecording" class="shadcn-btn w-full font-bold h-12" :class="isRecording ? 'shadcn-btn-destructive' : 'shadcn-btn-outline'">
                       <svg v-if="!isRecording" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" x2="12" y1="19" y2="22"></line></svg>
                       <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="currentColor" class="mr-2 text-white"><rect width="18" height="18" x="3" y="3" rx="2"></rect></svg>
                       {{ isRecording ? t('btn_stop') : t('btn_record') }}
                    </button>
                    
                    <div v-if="recordedAudioUrl" class="w-full bg-muted/30 p-4 rounded-md border border-border">
                       <audio :src="recordedAudioUrl" controls class="w-full"></audio>
                    </div>
                    
                    <div class="flex items-center gap-4">
                        <div class="h-px bg-border flex-1"></div>
                        <span class="text-xs text-muted-foreground uppercase font-bold tracking-wider">Hoặc</span>
                        <div class="h-px bg-border flex-1"></div>
                    </div>
                    
                    <div class="upload-zone" :class="{ 'active': enrollAudioFile && !recordedAudioUrl }">
                      <input type="file" id="enroll-audio-upload" @change="handleEnrollFileChange" accept="audio/*" class="hidden-input" />
                      <label for="enroll-audio-upload" class="upload-label py-12">
                        <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mb-4 text-muted-foreground"><path d="M19.35 10.04C18.67 6.59 15.64 4 12 4 9.11 4 6.6 5.64 5.35 8.04 2.34 8.36 0 10.91 0 14c0 3.31 2.69 6 6 6h13c2.76 0 5-2.24 5-5 0-2.64-2.05-4.78-4.65-4.96M14 13v4h-4v-4H7l5-5 5 5z"></path></svg>
                        <p class="text-base font-medium mb-1">Drag & drop a file here, or click to select</p>
                        <span class="upload-primary-text text-sm">{{ (enrollAudioFile && !recordedAudioUrl) ? enrollAudioFile.name : 'Supported: .mp3, .wav' }}</span>
                      </label>
                    </div>
                </div>
                
                <div class="card-footer border-t border-border bg-muted/20 flex flex-col gap-3 mt-4">
                    <button @click="submitEnrollment" :disabled="isEnrolling || !enrollAudioFile" class="shadcn-btn shadcn-btn-primary w-full h-12 text-lg">
                       {{ isEnrolling ? "⏳ Đang xử lý..." : t('btn_enroll') }}
                    </button>
                    <div v-if="enrollStatus" class="text-center text-sm font-medium mt-1" :class="enrollStatus.includes('✅') ? 'text-primary' : 'text-destructive'">
                       {{ enrollStatus }}
                    </div>
                </div>
            </div>
         </div>
      </template>

      <template v-if="activeTab === 'view_meeting'">
         <div class="w-full flex flex-col gap-8 pb-10 mt-2">
            <div class="shadcn-card glow-effect">
                <div class="card-header border-b border-border bg-muted/10">
                  <h3 class="card-title">{{ currentMeeting?.title }}</h3>
                  <p class="card-description">{{ currentMeeting?.date }} &middot; Trạng thái: {{ currentMeeting?.status }}</p>
                </div>
                
                <div class="card-content flex flex-col gap-6 mt-6">
                  <!-- Actions -->
                  <div class="flex flex-wrap items-center gap-4 p-4 bg-muted/30 rounded-lg border border-border">
                     <a v-if="currentMeeting?.audio_file" :href="currentMeeting.audio_file" target="_blank" class="shadcn-btn shadcn-btn-outline flex items-center gap-2">
                       <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
                       Nghe lại Audio
                     </a>
                     
                     <button v-if="currentMeeting?.minute_docx" @click="downloadViaBackend(currentMeeting.name, 'docx')" class="shadcn-btn shadcn-btn-outline flex items-center gap-2 text-primary border-primary/20 hover:bg-primary/10">
                       <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                       Tải Biên bản (Word)
                     </button>
                     
                     <button v-if="currentMeeting?.task_xlsx" @click="downloadViaBackend(currentMeeting.name, 'xlsx')" class="shadcn-btn shadcn-btn-outline flex items-center gap-2 text-green-500 border-green-500/20 hover:bg-green-500/10">
                       <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><path d="M8 13h2"></path><path d="M8 17h2"></path><path d="M14 13h2"></path><path d="M14 17h2"></path></svg>
                       Tải Tasks (Excel)
                     </button>
                  </div>

                  <!-- Parsed JSON Transcript (raw_results) -->
                  <div class="mt-4" v-if="currentMeeting?.raw_results">
                    <h4 class="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">Nội dung hội thoại</h4>
                    <div class="bg-muted/10 border border-border rounded-lg max-h-[550px] overflow-y-auto">
                      <div class="log-view p-6 space-y-4">
                        <div
                          v-for="(seg, idx) in parseMeetingSegments(currentMeeting.raw_results)"
                          :key="idx"
                          class="log-entry"
                        >
                          <div class="log-meta">
                            <span class="log-speaker">{{ seg[2] }}</span>
                            <span class="log-time">[{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s]</span>
                          </div>
                          <p class="log-text">{{ seg[3] }}</p>
                        </div>
                        <div v-if="parseMeetingSegments(currentMeeting.raw_results).length === 0" class="text-sm text-muted-foreground italic text-center py-4">
                          Không có dữ liệu hội thoại.
                        </div>
                      </div>
                    </div>
                  </div>

                  <!-- Fallback plain transcript -->
                  <div class="mt-4" v-else-if="currentMeeting?.transcript">
                    <h4 class="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">Nội dung hội thoại</h4>
                    <div class="bg-muted/10 border border-border rounded-lg p-6 max-h-[500px] overflow-y-auto">
                       <pre class="font-sans text-sm whitespace-pre-wrap leading-relaxed">{{ currentMeeting.transcript }}</pre>
                    </div>
                  </div>
                </div>
            </div>
         </div>
      </template>

    </main>
    </div>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --background: 0 0% 100%;
  --foreground: 240 10% 3.9%;
  
  --card: 0 0% 100%;
  --card-foreground: 240 10% 3.9%;
  
  --popover: 0 0% 100%;
  --popover-foreground: 240 10% 3.9%;
  
  --primary: 274 100% 61%;
  --primary-foreground: 0 0% 100%;
  
  --secondary: 240 4.8% 95.9%;
  --secondary-foreground: 240 5.9% 10%;
  
  --muted: 240 4.8% 95.9%;
  --muted-foreground: 240 3.8% 46.1%;
  
  --accent: 240 4.8% 95.9%;
  --accent-foreground: 240 5.9% 10%;
  
  --destructive: 0 84.2% 60.2%;
  --destructive-foreground: 0 0% 98%;
  
  --border: 240 5.9% 90%;
  --input: 240 5.9% 90%;
  --ring: 240 10% 3.9%;
  
  --radius: 0.5rem;
}

.dark {
  color-scheme: dark;
  --background: 240 10% 4%;
  --foreground: 0 0% 98%;
  
  --card: 240 10% 6%;
  --card-foreground: 0 0% 98%;
  
  --popover: 240 10% 4%;
  --popover-foreground: 0 0% 98%;
  
  --primary: 274 100% 61%;
  --primary-foreground: 0 0% 100%;
  
  --secondary: 240 4% 16%;
  --secondary-foreground: 0 0% 98%;
  
  --muted: 240 4% 16%;
  --muted-foreground: 240 5% 65%;
  
  --accent: 240 4% 16%;
  --accent-foreground: 0 0% 98%;
  
  --destructive: 0 62.8% 30.6%;
  --destructive-foreground: 0 0% 98%;
  
  --border: 240 4% 16%;
  --input: 240 4% 16%;
  --ring: 240 5% 84%;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: 'Inter', system-ui, sans-serif;
  background-color: hsl(var(--background));
  color: hsl(var(--foreground));
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
}

/* Utilities */
.flex { display: flex; }
.flex-col { flex-direction: column; }
.items-center { align-items: center; }
.justify-between { justify-content: space-between; }
.justify-end { justify-content: flex-end; }
.flex-between { display: flex; justify-content: space-between; align-items: center; }
.gap-2 { gap: 0.5rem; } .gap-3 { gap: 0.75rem; } .gap-4 { gap: 1rem; } .gap-6 { gap: 1.5rem; }
.space-y-1 > * + * { margin-top: 0.25rem; }
.space-y-1\.5 > * + * { margin-top: 0.375rem; }
.space-y-2 > * + * { margin-top: 0.5rem; }
.space-y-4 > * + * { margin-top: 1rem; }
.space-y-6 > * + * { margin-top: 1.5rem; }
.mb-3 { margin-bottom: 0.75rem; }
.mb-4 { margin-bottom: 1rem; }
.mb-6 { margin-bottom: 1.5rem; }
.mt-4 { margin-top: 1rem; }
.mt-6 { margin-top: 1.5rem; }
.w-full { width: 100%; }
.h-full { height: 100%; }
.h-screen { height: 100vh; }
.flex-1 { flex: 1 1 0%; }
.p-0 { padding: 0; }
.p-3 { padding: 0.75rem; }
.p-4 { padding: 1rem; }
.p-6 { padding: 1.5rem; }
.py-0 { padding-top: 0; padding-bottom: 0; }
.py-2 { padding-top: 0.5rem; padding-bottom: 0.5rem; }
.mr-2 { margin-right: 0.5rem; }
.-ml-1 { margin-left: -0.25rem; }

/* Text */
.font-bold { font-weight: 700; }
.font-medium { font-weight: 500; }
.font-normal { font-weight: 400; }
.font-mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.text-sm { font-size: 0.875rem; line-height: 1.25rem; }
.text-xs { font-size: 0.75rem; line-height: 1rem; }
.text-lg { font-size: 1.125rem; line-height: 1.75rem; }
.text-2xl { font-size: 1.5rem; line-height: 2rem; }
.tracking-tight { letter-spacing: -0.025em; }
.tracking-wider { letter-spacing: 0.05em; }
.uppercase { text-transform: uppercase; }
.text-muted-foreground { color: hsl(var(--muted-foreground)); }
.text-primary { color: hsl(var(--primary)); }
.text-destructive { color: #f87171; }

/* Colors */
.bg-background { background-color: hsl(var(--background)); }
.bg-secondary\/50 { background-color: hsla(var(--secondary), 0.5); border-radius: var(--radius); }
.bg-primary\/10 { background-color: hsla(var(--primary), 0.1); }
.bg-muted\/10 { background-color: hsla(var(--muted), 0.1); }
.bg-muted\/20 { background-color: hsla(var(--muted), 0.2); }
.border-l-2 { border-left-width: 2px; }
.border-l-primary { border-left-color: hsl(var(--primary)); }

.modal-overlay {
  position: fixed; inset: 0; z-index: 50;
  background: hsla(var(--background), 0.8);
  backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.modal-card {
  width: 350px; max-width: 90vw;
  box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1), 0 8px 10px -6px rgba(0,0,0,0.1);
}

/* Layout Grid - Tràn viền (Edge to Edge) */
.shadcn-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}
.shadcn-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 1rem 1.5rem;
  border-bottom: 1px solid hsl(var(--border));
  background: hsl(var(--background) / 0.8);
  backdrop-filter: blur(12px);
  position: sticky; top: 0; z-index: 40;
}
.shadcn-main {
  flex: 1;
  padding: 2rem;
  width: 100%;
}
.grid-full-width {
  display: grid;
  grid-template-columns: 1fr 2fr;
  gap: 2rem;
  width: 100%;
}
@media (max-width: 1024px) {
  .grid-full-width { grid-template-columns: 1fr; }
}

/* Base Components */
.logo-box {
  background: hsl(var(--primary)); color: hsl(var(--primary-foreground));
  padding: 0.25rem; border-radius: 6px;
}
.badge-outline {
  border: 1px solid hsl(var(--border));
  padding: 0.25rem 0.75rem;
  font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
  border-radius: 9999px; color: hsl(var(--muted-foreground));
}
.avatar {
  width: 32px; height: 32px; border-radius: 50%;
  background: linear-gradient(135deg, #a855f7, #ec4899);
}

/* Cards */
.shadcn-card {
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: var(--radius);
  color: hsl(var(--card-foreground));
  box-shadow: 0 1px 2px 0 rgb(0 0 0 / 0.05);
  transition: border-color 0.2s ease;
}
.glow-effect {
  position: relative;
}
.glow-effect::before {
  content: ""; position: absolute; inset: -1px;
  background: linear-gradient(135deg, hsla(var(--primary),0.3), transparent 60%);
  border-radius: calc(var(--radius) + 1px);
  z-index: -1; pointer-events: none;
}

.card-header { padding: 1.5rem; }
.card-title { font-size: 1.125rem; font-weight: 600; margin: 0 0 0.25rem 0; letter-spacing: -0.025em; }
.card-description { font-size: 0.875rem; color: hsl(var(--muted-foreground)); margin: 0; }
.card-content { padding: 1.5rem; padding-top: 0; }
.card-footer { padding: 1.5rem; display: flex; align-items: center; border-bottom-left-radius: var(--radius); border-bottom-right-radius: var(--radius); }
.border-b { border-bottom: 1px solid hsl(var(--border)); }
.border-t { border-top: 1px solid hsl(var(--border)); }

/* Forms & Inputs */
.shadcn-label {
  font-weight: 500;
  color: hsl(var(--foreground)); display: block;
}
.shadcn-input, .shadcn-select {
  display: flex; height: 2.5rem; width: 100%;
  border-radius: calc(var(--radius) - 2px);
  border: 1px solid hsl(var(--input));
  background: hsl(var(--background));
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  color: hsl(var(--foreground));
  transition: border-color 0.2s;
}
.shadcn-input:focus, .shadcn-select:focus {
  outline: none;
  border-color: hsl(var(--ring));
}
.shadcn-select {
  appearance: none;
  background-image: url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%24%2024%22%20fill%3D%22none%22%20stroke%3D%22%23a1a1aa%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpolyline%20points%3D%226%209%2012%2015%2018%209%22%3E%3C%2Fpolyline%3E%3C%2Fsvg%3E");
  background-repeat: no-repeat; background-position: right 0.5rem center; background-size: 1em;
  padding-right: 2rem;
}
.h-8 { height: 2rem; }
.h-9 { height: 2.25rem; }
.min-h-\[80px\] { min-height: 80px; }

/* Upload Zone */
.upload-zone {
  border: 1px dashed hsl(var(--border));
  border-radius: var(--radius);
  transition: all 0.2s;
  background: hsl(var(--muted)/0.3);
}
.upload-zone:hover { border-color: hsl(var(--ring)); background: hsl(var(--muted)/0.5); }
.upload-zone.active { border-color: hsl(var(--ring)); border-style: solid; }
.hidden-input { display: none; }
.upload-label {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 2.5rem 1.5rem; cursor: pointer; text-align: center;
}
.upload-primary-text { font-size: 0.875rem; font-weight: 500; margin-bottom: 0.25rem; }
.upload-secondary-text { font-size: 0.75rem; }

/* Buttons */
.shadcn-btn {
  display: inline-flex; align-items: center; justify-content: center;
  border-radius: calc(var(--radius) - 2px);
  font-size: 0.875rem; font-weight: 500;
  height: 2.5rem; padding: 0 1rem;
  transition: all 0.2s; cursor: pointer; border: none; text-decoration: none;
  white-space: nowrap;
}
.shadcn-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.shadcn-btn-primary {
  background: hsl(var(--primary)); color: hsl(var(--primary-foreground));
  box-shadow: 0 0 15px hsla(var(--primary), 0.2);
}
.shadcn-btn-primary:hover:not(:disabled) { background: hsl(var(--primary) / 0.9); }
.shadcn-btn-destructive {
  background: hsl(var(--destructive)); color: hsl(var(--destructive-foreground));
  box-shadow: 0 0 15px hsla(var(--destructive), 0.2);
}
.shadcn-btn-destructive:hover:not(:disabled) { background: hsl(var(--destructive) / 0.9); }
.shadcn-btn-outline {
  background: transparent; border: 1px solid hsl(var(--border));
  color: hsl(var(--foreground));
}
.shadcn-btn-outline:hover:not(:disabled) { background: hsl(var(--accent)); color: hsl(var(--accent-foreground)); }
.shadcn-btn-ghost {
  background: transparent; color: hsl(var(--foreground));
}
.shadcn-btn-ghost:hover:not(:disabled) { background: hsl(var(--accent)); color: hsl(var(--accent-foreground)); }
.btn-ghost-icon {
  background: transparent; border: none; cursor: pointer;
  padding: 0.25rem; border-radius: 4px; display: inline-flex; align-items: center; justify-content: center;
  transition: background-color 0.2s;
}

/* Transcripts & Logs */
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; min-height: 200px; }
.log-view { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }
.log-entry { border-left: 2px solid hsl(var(--border)); padding-left: 1rem; position: relative; }
.log-entry::before { content: ""; position: absolute; left: -5px; top: 0.5rem; width: 8px; height: 8px; border-radius: 50%; background: hsl(var(--ring)); }
.log-meta { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; }
.log-speaker { font-size: 0.75rem; font-weight: 600; color: hsl(var(--primary)); letter-spacing: 0.05em; }
.log-time { font-size: 0.75rem; color: hsl(var(--muted-foreground)); }
.log-text { font-size: 0.875rem; line-height: 1.5; margin: 0; color: hsl(var(--foreground)); }

/* Attendee Chips */
.attendee-chip {
  display: inline-flex; align-items: center; gap: 0.4rem;
  padding: 0.35rem 0.75rem; border-radius: 9999px;
  font-size: 0.8125rem; font-weight: 500; cursor: pointer;
  border: 1.5px solid hsl(var(--border));
  background: hsl(var(--muted)/0.3);
  color: hsl(var(--foreground));
  transition: all 0.15s ease;
}
.attendee-chip:hover { border-color: hsl(var(--primary)/0.6); background: hsl(var(--primary)/0.08); }
.attendee-chip--active {
  border-color: hsl(var(--primary));
  background: hsl(var(--primary)/0.15);
  color: hsl(var(--primary));
}
.attendee-avatar {
  width: 18px; height: 18px; border-radius: 50%;
  background: hsl(var(--primary)/0.2); color: hsl(var(--primary));
  font-size: 0.6rem; font-weight: 700;
  display: inline-flex; align-items: center; justify-content: center;
}
.attendee-chip--active .attendee-avatar { background: hsl(var(--primary)); color: white; }
.attendee-add-input {
  background-color: hsl(var(--primary)/0.05);
  color: hsl(var(--primary));
  border: 1px dashed hsl(var(--primary)/0.4);
  border-radius: 9999px;
  padding: 0.35rem 1rem;
  font-size: 0.8125rem;
  font-weight: 500;
  outline: none;
  transition: all 0.2s;
  width: 250px;
}
.attendee-add-input::placeholder {
  color: hsl(var(--primary));
  opacity: 0.8;
}
.attendee-add-input:hover, .attendee-add-input:focus {
  background-color: hsl(var(--primary)/0.12);
  border-style: solid;
}
.attendee-add-input:disabled { opacity: 0.4; cursor: not-allowed; }
.attendee-remove {
  background: none; border: none; padding: 0; cursor: pointer;
  display: inline-flex; align-items: center; justify-content: center;
  color: hsl(var(--primary)/0.7); border-radius: 50%; width: 14px; height: 14px;
  transition: color 0.15s, background 0.15s;
}
.attendee-remove:hover { color: hsl(var(--destructive)); }

/* Table Layout */
.shadcn-table { border-collapse: collapse; text-align: left; }
.shadcn-table th { white-space: nowrap; }
.shadcn-table-input, .shadcn-table-select {
  width: 100%; min-height: 2.75rem;
  background: transparent; border: 1px solid transparent;
  border-radius: calc(var(--radius) - 2px);
  color: hsl(var(--foreground)); font-size: 0.95rem;
  padding: 0.5rem 0.75rem; transition: all 0.2s;
}
.shadcn-table-input:hover, .shadcn-table-select:hover { border-color: hsl(var(--input)); background: hsl(var(--background)); }
.shadcn-table-input:focus, .shadcn-table-select:focus { outline: none; border-color: hsl(var(--ring)); background: hsl(var(--background)); }
.shadcn-table-select {
  appearance: none;
  background-image: url("data:image/svg+xml;charset=US-ASCII,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2224%22%20height%3D%2224%22%20viewBox%3D%220%200%24%2024%22%20fill%3D%22none%22%20stroke%3D%22%23a1a1aa%22%20stroke-width%3D%222%22%20stroke-linecap%3D%22round%22%20stroke-linejoin%3D%22round%22%3E%3Cpolyline%20points%3D%226%209%2012%2015%2018%209%22%3E%3C%2Fpolyline%3E%3C%2Fsvg%3E");
  background-repeat: no-repeat; background-position: right 0.25rem center; background-size: 1em; padding-right: 1.5rem;
}
.resize-y { resize: vertical; }
.min-h-\[80px\] { min-height: 80px; }
.w-12 { width: 3rem; }
.w-16 { width: 4rem; }
.w-40 { width: 10rem; }
.min-w-\[180px\] { min-width: 180px; }
.min-w-\[200px\] { min-width: 200px; }
.min-w-\[250px\] { min-width: 250px; }
.min-w-\[350px\] { min-width: 350px; }
.px-2 { padding-left: 0.5rem; padding-right: 0.5rem; }

/* Alert */
.shadcn-alert {
  background: hsl(var(--accent));
  border: 1px solid hsl(var(--border));
  padding: 1rem; border-radius: var(--radius);
  font-size: 0.875rem; font-weight: 500;
}

/* Grid System */
.grid { display: grid; }
.grid-cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }

/* Animations */
.animate-spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.sticky { position: sticky; }
.top-0 { top: 0; }
.z-10 { z-index: 10; }
.backdrop-blur { backdrop-filter: blur(8px); }

::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: hsl(var(--border)); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: hsl(var(--muted-foreground)); }

/* Custom visible scrollbar for log-view */
.log-view::-webkit-scrollbar { width: 10px; }
.log-view::-webkit-scrollbar-track { background: hsl(var(--muted)); border-radius: 6px; }
.log-view::-webkit-scrollbar-thumb { background: hsl(var(--primary) / 0.8); border-radius: 6px; border: 2px solid hsl(var(--background)); }
.log-view::-webkit-scrollbar-thumb:hover { background: hsl(var(--primary)); }
</style>
