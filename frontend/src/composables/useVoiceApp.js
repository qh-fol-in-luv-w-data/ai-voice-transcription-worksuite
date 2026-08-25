import { ref, watch, onMounted } from 'vue'
import { transcribeAudio, extractTasks, syncTasksToERP, enrollVoice, getEnrolledSpeakers, getMeetingHistory, getMeetingDetail } from '../api'

// Global UI State
const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
export const isDark = ref(prefersDark)
export const uiLang = ref('vi')
export const activeTab = ref('transcribe')

// Global App State
export const audioFile = ref(null)
export const language = ref('auto')
export const modelType = ref('gpt-4o-mini')

export const isTranscribing = ref(false)
export const transcribeStatus = ref('')
export const transcriptResults = ref([])
export const originalTranscriptResults = ref([])
export const isCleaned = ref(false)
export const transcriptText = ref('')

export const isExtracting = ref(false)
export const extractStatus = ref('')
export const isCleaning = ref(false)
export const docxUrl = ref('')
export const excelUrl = ref('')

export const meetingSummary = ref('')
export const meetingConclusion = ref('')

export const tasks = ref([])
export const hrProjectsMap = ref({})
export const dbEmployees = ref([])
export const voiceDbSpeakers = ref([])
export const selectedAttendees = ref([])
export const newAttendeeName = ref('')
export const isReanalyzing = ref(false)
export const isSyncing = ref(false)
export const erpStatus = ref('')

export const meetingHistory = ref([])
export const currentMeetingName = ref(null)
export const currentMeeting = ref(null)

export const enrollAudioFile = ref(null)
export const enrollStatus = ref('')
export const isEnrolling = ref(false)

export const isRecording = ref(false)
export const mediaRecorder = ref(null)
export const audioChunks = ref([])
export const recordedAudioUrl = ref('')
export const isTaskModalOpen = ref(false)

export const voiceTaskHistory = ref(JSON.parse(localStorage.getItem('voiceTaskHistory') || '[]'))
export const saveVoiceTaskHistory = () => {
  localStorage.setItem('voiceTaskHistory', JSON.stringify(voiceTaskHistory.value))
}
export const selectedVoiceTaskHistoryItem = ref(null)

// Dictionary for i18n
export const dict = {
  vi: {
    title: "2AS Worksuite",
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
    task_desc: "Kiểm tra và hiệu chỉnh trước khi đồng bộ lên hệ thống Worksuite.",
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
    btn_sync: "Đồng bộ lên Worksuite",
    status_transcribe_wait: "⏳ Đang xử lý, vui lòng đợi...",
    status_transcribe_ok: "✅ Dịch và nhận diện thành công!",
    status_extract_wait: "⏳ Đang trích xuất nhiệm vụ qua AI...",
    status_extract_ok: "✅ Trích xuất nhiệm vụ thành công!",
    status_sync_wait: "⏳ Đang đồng bộ dữ liệu lên Worksuite...",
    status_sync_ok: (c, e) => `✅ Đã đồng bộ: ${c} nhiệm vụ. Lỗi: ${e}`,
    status_sync_fail: "❌ Đồng bộ thất bại: ",
    alert_no_file: "Vui lòng chọn file âm thanh!",
    alert_no_transcript: "Chưa có nội dung hội thoại!",
    error_connect: "❌ Lỗi kết nối",
    empty_project: "-- Trống --",
    tab_transcribe: "Phân tích Hội thoại",
    tab_enroll: "Đăng ký Giọng nói",
    tab_history: "Lịch sử Cuộc họp",
    tab_voicetask: "Giao việc bằng giọng nói",
    voice_task_title: "Giao việc bằng giọng nói",
    voice_task_desc: "Tạo nhanh công việc trên Worksuite chỉ bằng cách nói ra yêu cầu.",
    voice_task_placeholder: "'Tạo task thiết kế giao diện đăng nhập cho dự án A, giao cho Quân, hạn chót thứ 6 tuần này...'",
    voice_task_success: "✅ Tạo nhiệm vụ thành công!",
    voice_task_transcribing: "⏳ Đang xử lý âm thanh...",
    enroll_title: "Đăng ký Nhận diện Giọng nói",
    enroll_desc: "Thu âm hoặc tải lên giọng nói. Hệ thống tự động liên kết với tài khoản đang đăng nhập.",
    btn_record: "Bắt đầu thu âm",
    btn_stop: "Dừng thu âm",
    btn_enroll: "Đăng ký Hệ thống",
    menu_main: "Menu Chính",
    meeting_history: "Lịch sử cuộc họp",
    no_history: "Chưa có lịch sử"
  },
  en: {
    title: "2AS Worksuite",
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
    task_desc: "Review and edit before syncing to Worksuite system.",
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
    btn_sync: "Sync to Worksuite",
    status_transcribe_wait: "⏳ Processing, please wait...",
    status_transcribe_ok: "✅ Translation and identification successful!",
    status_extract_wait: "⏳ Extracting tasks via AI...",
    status_extract_ok: "✅ Tasks extracted successfully!",
    status_sync_wait: "⏳ Syncing data to Worksuite...",
    status_sync_ok: (c, e) => `✅ Synced: ${c} tasks. Errors: ${e}`,
    status_sync_fail: "❌ Sync failed: ",
    alert_no_file: "Please select an audio file!",
    alert_no_transcript: "No conversation content available!",
    error_connect: "❌ Connection error",
    empty_project: "-- Empty --",
    tab_transcribe: "Conversation Analysis",
    tab_enroll: "Voice Enrollment",
    tab_history: "Meeting History",
    tab_voicetask: "Voice to Task",
    voice_task_title: "Voice to Task",
    voice_task_desc: "Create Worksuite tasks quickly by speaking out your requirements.",
    voice_task_placeholder: "'Create a UI design task for Project A, assign to Quan, due this Friday...'",
    voice_task_success: "✅ Task created successfully!",
    voice_task_transcribing: "⏳ Processing audio...",
    enroll_title: "Register Voice ID",
    enroll_desc: "Record or upload your voice. The system will automatically link it to your current account.",
    btn_record: "Start Recording",
    btn_stop: "Stop Recording",
    btn_enroll: "Enroll Voice",
    menu_main: "Main Menu",
    meeting_history: "Meeting History",
    no_history: "No history yet"
  }
}

export const t = (key) => {
  if (!dict[uiLang.value]) return key
  return dict[uiLang.value][key] || key
}

export const toggleDark = () => { isDark.value = !isDark.value }
export const toggleLang = () => { uiLang.value = uiLang.value === 'vi' ? 'en' : 'vi' }

// Watcher to apply dark mode class to html element
watch(isDark, (val) => {
  if (val) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}, { immediate: true })

export const loadHistory = async () => {
  try {
    const res = await getMeetingHistory()
    if (res && res.status === 'success') {
      meetingHistory.value = res.meetings || []
    }
  } catch (e) {
    console.error("Failed to load meeting history", e)
  }
}

export const loadPastMeeting = async (meeting) => {
  let detail = meeting
  if (meeting?.name && !meeting.raw_results && !meeting.transcript) {
    const res = await getMeetingDetail(meeting.name)
    if (res?.status === 'success' && res.meeting) {
      detail = res.meeting
    }
  }
  currentMeeting.value = detail
  activeTab.value = 'view_meeting'
  meetingSummary.value = detail.meeting_summary || ''
  meetingConclusion.value = detail.conclusion || ''
  if (detail.tasks_json) {
    try {
      tasks.value = typeof detail.tasks_json === 'string'
        ? JSON.parse(detail.tasks_json)
        : detail.tasks_json
    } catch (e) {
      console.error("Failed to parse tasks_json", e)
      tasks.value = []
    }
  } else {
    tasks.value = []
  }
}

export const currentLocalDate = () => {
  const d = new Date()
  const day = String(d.getDate()).padStart(2, '0')
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const year = d.getFullYear()
  return `${day}-${month}-${year}`
}

import { saveMeetingDraft } from '../api'

let saveTimeout = null
watch([meetingSummary, meetingConclusion, tasks], () => {
  if (saveTimeout) clearTimeout(saveTimeout)
  saveTimeout = setTimeout(async () => {
    if (!currentMeetingName.value) return
    try {
      await saveMeetingDraft(
        currentMeetingName.value,
        meetingSummary.value,
        meetingConclusion.value,
        JSON.stringify(tasks.value)
      )
    } catch(e) {
      console.error("Auto-save failed", e)
    }
  }, 1500)
}, { deep: true })
