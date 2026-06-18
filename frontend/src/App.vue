<script setup>
import { ref, onMounted, watch, computed } from 'vue'
import { transcribeAudio, extractTasks, syncTasksToERP, getElevenLabsInfo, enrollVoice, getEnrolledSpeakers, getMeetingHistory, cleanTranscript, updateMeetingResults, voiceToTask, getEmployees, enrollMappedSpeakers } from './api'
import { initSession, useSession } from './utils/session'

import CTSplashScreen from './components/CTSplashScreen.vue'
import CTAccessDenied from './components/CTAccessDenied.vue'

// Session
const { authState, currentUser, currentFullName } = useSession()

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

const audioDuration = ref(0)
const meetingStartTime = ref(new Date())
const meetingLocation = ref('')
const meetingChairperson = ref('')

const globalEmployees = ref([])
const employeeOptions = computed(() => {
  return globalEmployees.value.map(emp => ({
    value: emp.employee_name + ' (' + emp.name + ')',
    label: emp.employee_name + ' (' + emp.name + ')' + (emp.user_id ? ' - ' + emp.user_id : '')
  }))
})

const speakerMapping = ref({})

const unknownSpeakers = computed(() => {
  if (!transcriptResults.value) return []
  const speakers = new Set()
  for (const seg of transcriptResults.value) {
    if (seg[2] && (seg[2].startsWith('👤 Người lạ') || seg[2].startsWith('Người lạ'))) {
      speakers.add(seg[2])
    }
  }
  return Array.from(speakers)
})

const updateIdentities = async () => {
  let changed = false
  const mappingsToSave = {}
  
  for (const seg of transcriptResults.value) {
    if (speakerMapping.value[seg[2]]) {
      mappingsToSave[seg[2]] = speakerMapping.value[seg[2]]
      seg[2] = speakerMapping.value[seg[2]]
      changed = true
    }
  }
  if (changed) {
    // Update original as well
    for (const seg of originalTranscriptResults.value) {
      if (speakerMapping.value[seg[2]]) {
        seg[2] = speakerMapping.value[seg[2]]
      }
    }
    // Update backend if meeting exists
    if (currentMeetingName.value) {
      try {
        const enrollRes = await enrollMappedSpeakers(currentMeetingName.value, mappingsToSave)
        await updateMeetingResults(currentMeetingName.value, transcriptResults.value)
        
        let msg = '✅ Đã cập nhật danh tính thành công!\n'
        if (enrollRes && typeof enrollRes === 'object') {
           if (enrollRes.enrolled && enrollRes.enrolled.length > 0) {
             msg += `\n🎙️ Đã tự động lưu ${enrollRes.enrolled.length} mẫu giọng mới.`
             // refresh voice db speakers so they show up in UI
             await fetchEnrolledSpeakers()
           }
           if (enrollRes.skipped && enrollRes.skipped.length > 0) {
             msg += `\n⏭️ Đã bỏ qua ${enrollRes.skipped.length} nhân viên (đã có mẫu giọng).`
           }
           if (enrollRes.errors && enrollRes.errors.length > 0) {
             msg += `\n⚠️ Không thể lấy mẫu giọng cho ${enrollRes.errors.length} người (âm thanh quá ngắn).`
           }
        }
        alert(msg)
      } catch(e) {
        console.warn('Could not save updated identities to server', e)
        alert('✅ Đã cập nhật danh tính thành công trên giao diện, nhưng có lỗi lưu lên server.')
      }
    } else {
      alert('✅ Đã cập nhật danh tính thành công!')
    }
  } else {
    alert('Chưa có thay đổi nào được áp dụng.')
  }
}

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

// Voice Task Module States
const voiceTaskAudioFile = ref(null)
const voiceTaskRecordedUrl = ref('')
const voiceTaskIsRecording = ref(false)
const voiceTaskMediaRecorder = ref(null)
const voiceTaskChunks = ref([])

const isVoiceTaskProcessing = ref(false)
const voiceTaskStatus = ref('')
const voiceTaskTranscript = ref('')
const parsedVoiceTask = ref(null)
const voiceTaskProjects = ref([])
const voiceTaskEmployees = ref([])

const voiceTaskSyncStatus = ref('')
const isVoiceTaskSyncing = ref(false)

// Conversational Refinement States
const voiceTaskClarification = ref('')
const voiceTaskMissingFields = ref([])
const voiceTaskRefineAudioFile = ref(null)
const voiceTaskRefineRecordedUrl = ref('')
const voiceTaskRefineIsRecording = ref(false)
const voiceTaskRefineMediaRecorder = ref(null)
const voiceTaskRefineChunks = ref([])

const languages = [
  { val: 'vi', label: 'Tiếng Việt' },
  { val: 'en', label: 'Tiếng Anh' },
  { val: 'ja', label: 'Tiếng Nhật' },
  { val: 'zh', label: 'Tiếng Trung' },
  { val: 'ko', label: 'Tiếng Hàn' },
  { val: 'auto', label: 'Tự động phát hiện' }
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
    col_weight: "Tỉ trọng (%)",
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
    btn_enroll: "Đăng ký Hệ thống",
    tab_voice_task: "Tự tạo Task qua Voice",
    voice_task_title: "Tự tạo Task bằng Giọng nói",
    voice_task_desc: "Nói hoặc tải lên câu lệnh giọng nói để AI tự động trích xuất tên task, dự án, thời gian bắt đầu, kết thúc và mô tả.",
    voice_task_recording: "Đang ghi âm câu lệnh...",
    voice_task_transcribing: "Đang chuyển giọng nói thành văn bản...",
    voice_task_parsing: "AI đang phân tích thông tin tạo Task...",
    voice_task_success: "✅ Phân tích câu lệnh thành công!",
    voice_task_empty: "Chưa có câu lệnh giọng nói nào được phân tích...",
    voice_task_sync_success: "✅ Đồng bộ Task thành công!",
    voice_task_sync_error: "❌ Đồng bộ Task thất bại: ",
    voice_task_placeholder: "Ví dụ: 'Tạo nhiệm vụ thiết kế giao diện cho dự án 2AS Worksuite bắt đầu từ ngày mai đến hết thứ sáu tuần này, mô tả là cần làm giao diện thật đẹp mắt.'"
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
    col_weight: "Weight (%)",
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
    btn_enroll: "Enroll Voice",
    tab_voice_task: "Voice Task Creator",
    voice_task_title: "Create Task via Voice",
    voice_task_desc: "Speak or upload a voice command for AI to automatically extract task name, project, start date, due date, and description.",
    voice_task_recording: "Recording command...",
    voice_task_transcribing: "Transcribing voice to text...",
    voice_task_parsing: "AI parsing details...",
    voice_task_success: "✅ Command parsed successfully!",
    voice_task_empty: "No voice commands parsed yet...",
    voice_task_sync_success: "✅ Task synced successfully!",
    voice_task_sync_error: "❌ Failed to sync task: ",
    voice_task_placeholder: "Example: 'Create a task to design the UI for 2AS Worksuite project starting tomorrow until this Friday, description is to make it look premium.'"
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
    const url = URL.createObjectURL(audioFile.value)
    const audio = new Audio(url)
    audio.onloadedmetadata = () => {
      audioDuration.value = audio.duration
    }
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
  enrollStatus.value = "" // Chỉ hiển thị "Đang xử lý..." trên nút, xóa status bên dưới
  
  try {
    const resMsg = await enrollVoice(enrollAudioFile.value)
    // resMsg là object {"status": "...", "message": "..."}
    const displayMsg = (typeof resMsg === 'object' && resMsg.message) ? resMsg.message : resMsg
    enrollStatus.value = (resMsg?.status === 'error' ? "❌ " : "✅ ") + displayMsg
  } catch(e) {
    if (e.response?.data?.message) {
      const errMsg = e.response.data.message
      enrollStatus.value = "❌ " + ((typeof errMsg === 'object' && errMsg.message) ? errMsg.message : errMsg)
    } else {
      enrollStatus.value = "❌ " + t('error_connect')
    }
  } finally {
    isEnrolling.value = false
  }
}

const handleVoiceTaskFileChange = (e) => {
  if (e.target.files.length > 0) {
    voiceTaskAudioFile.value = e.target.files[0]
    voiceTaskRecordedUrl.value = ''
  }
}

const toggleVoiceTaskRecording = async () => {
  if (voiceTaskIsRecording.value) {
    voiceTaskMediaRecorder.value.stop()
    voiceTaskIsRecording.value = false
    return
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    voiceTaskMediaRecorder.value = new MediaRecorder(stream)
    voiceTaskChunks.value = []
    
    voiceTaskMediaRecorder.value.ondataavailable = e => {
      if (e.data.size > 0) voiceTaskChunks.value.push(e.data)
    }
    
    voiceTaskMediaRecorder.value.onstop = () => {
      const blob = new Blob(voiceTaskChunks.value, { type: 'audio/wav' })
      voiceTaskAudioFile.value = blob
      voiceTaskAudioFile.value.name = 'voice_task_command.wav'
      voiceTaskRecordedUrl.value = URL.createObjectURL(blob)
      stream.getTracks().forEach(t => t.stop())
    }
    
    voiceTaskMediaRecorder.value.start()
    voiceTaskIsRecording.value = true
  } catch(e) {
    alert("Lỗi truy cập Micro: " + e)
  }
}

const submitVoiceTask = async () => {
  if (!voiceTaskAudioFile.value) {
    alert(t('alert_no_file'))
    return
  }
  isVoiceTaskProcessing.value = true
  voiceTaskStatus.value = t('voice_task_transcribing')
  voiceTaskTranscript.value = ''
  parsedVoiceTask.value = null
  voiceTaskSyncStatus.value = ''
  voiceTaskClarification.value = ''
  voiceTaskMissingFields.value = []
  
  try {
    const res = await voiceToTask(voiceTaskAudioFile.value)
    if (res.status === 'success') {
      voiceTaskStatus.value = t('voice_task_success')
      voiceTaskTranscript.value = res.transcript
      
      let assignee = res.task.assignee_display || '';
      if (!assignee && currentUser.value && res.employees) {
        const emp = res.employees.find(e => e.user_id === currentUser.value);
        if (emp) assignee = emp.employee_name + ' (' + emp.name + ')';
      }
      
      parsedVoiceTask.value = {
        title: res.task.task_name || '',
        assignee_display: assignee,
        assignee_hr_code: '',
        assignee_email: '',
        project: res.task.project_id || '',
        start_date: res.task.start_date || '',
        due_date: res.task.end_date || '',
        weight: 0,
        description: res.task.description || ''
      }
      
      voiceTaskProjects.value = res.projects || []
      voiceTaskEmployees.value = res.employees || []
      
      voiceTaskClarification.value = res.task.clarification_question || ''
      voiceTaskMissingFields.value = res.task.missing_fields || []
    } else {
      voiceTaskStatus.value = '❌ Lỗi: ' + res.message
    }
  } catch(e) {
    voiceTaskStatus.value = '❌ Lỗi: ' + t('error_connect')
  } finally {
    isVoiceTaskProcessing.value = false
  }
}

const handleVoiceTaskRefineFileChange = (e) => {
  if (e.target.files.length > 0) {
    voiceTaskRefineAudioFile.value = e.target.files[0]
    voiceTaskRefineRecordedUrl.value = ''
  }
}

const toggleVoiceTaskRefineRecording = async () => {
  if (voiceTaskRefineIsRecording.value) {
    voiceTaskRefineMediaRecorder.value.stop()
    voiceTaskRefineIsRecording.value = false
    return
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    voiceTaskRefineMediaRecorder.value = new MediaRecorder(stream)
    voiceTaskRefineChunks.value = []
    
    voiceTaskRefineMediaRecorder.value.ondataavailable = e => {
      if (e.data.size > 0) voiceTaskRefineChunks.value.push(e.data)
    }
    
    voiceTaskRefineMediaRecorder.value.onstop = () => {
      const blob = new Blob(voiceTaskRefineChunks.value, { type: 'audio/wav' })
      voiceTaskRefineAudioFile.value = blob
      voiceTaskRefineAudioFile.value.name = 'voice_task_refine.wav'
      voiceTaskRefineRecordedUrl.value = URL.createObjectURL(blob)
      stream.getTracks().forEach(t => t.stop())
    }
    
    voiceTaskRefineMediaRecorder.value.start()
    voiceTaskRefineIsRecording.value = true
  } catch(e) {
    alert("Lỗi truy cập Micro: " + e)
  }
}

const submitVoiceTaskRefine = async () => {
  if (!voiceTaskRefineAudioFile.value) {
    alert(t('alert_no_file'))
    return
  }
  isVoiceTaskProcessing.value = true
  voiceTaskStatus.value = t('voice_task_parsing')
  
  try {
    const res = await voiceToTask(voiceTaskRefineAudioFile.value, parsedVoiceTask.value)
    if (res.status === 'success') {
      voiceTaskStatus.value = t('voice_task_success')
      voiceTaskTranscript.value += ` -> ${res.transcript}`
      
      let assignee = res.task.assignee_display || '';
      if (!assignee && currentUser.value && res.employees) {
        const emp = res.employees.find(e => e.user_id === currentUser.value);
        if (emp) assignee = emp.employee_name + ' (' + emp.name + ')';
      }
      
      parsedVoiceTask.value = {
        title: res.task.task_name || '',
        assignee_display: assignee,
        assignee_hr_code: '',
        assignee_email: '',
        project: res.task.project_id || '',
        start_date: res.task.start_date || '',
        due_date: res.task.end_date || '',
        weight: 0,
        description: res.task.description || ''
      }
      
      voiceTaskProjects.value = res.projects || []
      voiceTaskEmployees.value = res.employees || []
      
      voiceTaskClarification.value = res.task.clarification_question || ''
      voiceTaskMissingFields.value = res.task.missing_fields || []
      
      voiceTaskRefineAudioFile.value = null
      voiceTaskRefineRecordedUrl.value = ''
    } else {
      voiceTaskStatus.value = '❌ Lỗi: ' + res.message
    }
  } catch(e) {
    voiceTaskStatus.value = '❌ Lỗi: ' + t('error_connect')
  } finally {
    isVoiceTaskProcessing.value = false
  }
}

const syncVoiceTaskToERP = async () => {
  if (!parsedVoiceTask.value) return
  isVoiceTaskSyncing.value = true
  voiceTaskSyncStatus.value = t('status_sync_wait')
  
  try {
    const displayStr = parsedVoiceTask.value.assignee_display
    if (displayStr) {
      const match = displayStr.match(/\((HR[-_]EMP[-_][^)]+)\)/i)
      if (match) parsedVoiceTask.value.assignee_hr_code = match[1]
      
      const matchedEmp = voiceTaskEmployees.value.find(e => e.employee_name + ' (' + e.name + ')' === displayStr)
      if (matchedEmp) {
        parsedVoiceTask.value.assignee_email = matchedEmp.user_id
        parsedVoiceTask.value.assignee_hr_code = matchedEmp.name
      }
    }

    const res = await syncTasksToERP([parsedVoiceTask.value])
    if (res.status === 'success') {
      const created = res.report.created_tasks ? res.report.created_tasks.length : 0
      if (created > 0) {
        voiceTaskSyncStatus.value = t('voice_task_sync_success')
      } else {
        voiceTaskSyncStatus.value = t('voice_task_sync_error') + (res.report.errors ? res.report.errors.join(', ') : '')
      }
    } else {
      voiceTaskSyncStatus.value = t('voice_task_sync_error') + res.message
    }
  } catch (e) {
    voiceTaskSyncStatus.value = t('error_connect')
  } finally {
    isVoiceTaskSyncing.value = false
  }
}

const stringToColor = (str) => {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash);
  }
  const c = (hash & 0x00FFFFFF).toString(16).toUpperCase();
  return '#' + '00000'.substring(0, 6 - c.length) + c;
}

const parseTranscript = (text) => {
  if (!text) return []
  const lines = text.split('\n')
  const messages = []
  let currentMsg = null
  for (const line of lines) {
    const speakerMatch = line.match(/^\*\*(.*?)\*\*\s+\[(.*?)\]/)
    if (speakerMatch) {
      if (currentMsg) messages.push(currentMsg)
      let name = speakerMatch[1].replace('👤', '').trim()
      name = name.replace(/\s*-\s*\d+%$/, '').trim()
      name = name.replace(/\s+/g, ' ')
      currentMsg = {
        speaker: name,
        time: speakerMatch[2].trim(),
        text: ''
      }
    } else if (currentMsg && line.trim()) {
      currentMsg.text += (currentMsg.text ? '\n' : '') + line.trim()
    } else if (!currentMsg && line.trim()) {
      currentMsg = { speaker: 'Hệ thống', time: '', text: line.trim() }
    }
  }
  if (currentMsg) messages.push(currentMsg)
  return messages
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
  if (!meetingStartTime.value) {
    meetingStartTime.value = new Date()
  }
  isExtracting.value = true
  extractStatus.value = t('status_extract_wait')
  
  try {
    let endTimeStr = ''
    if (meetingStartTime.value && audioDuration.value) {
      const start = new Date(meetingStartTime.value)
      const end = new Date(start.getTime() + audioDuration.value * 1000)
      
      const pad = (n) => String(n).padStart(2, '0')
      endTimeStr = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}T${pad(end.getHours())}:${pad(end.getMinutes())}`
    }

    let startFormatted = ''
    if (meetingStartTime.value) {
      const d = new Date(meetingStartTime.value)
      const pad = (n) => String(n).padStart(2, '0')
      startFormatted = `${pad(d.getHours())}:${pad(d.getMinutes())} ngày ${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`
    }
    let endFormatted = ''
    if (endTimeStr) {
      const d = new Date(endTimeStr)
      const pad = (n) => String(n).padStart(2, '0')
      endFormatted = `${pad(d.getHours())}:${pad(d.getMinutes())} ngày ${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`
    }

    const res = await extractTasks(
      transcriptResults.value, 
      modelType.value, 
      currentMeetingName.value,
      startFormatted,
      endFormatted,
      meetingLocation.value,
      meetingChairperson.value
    )
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
    weight: 0,
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
      const errList = report.errors || []
      erpStatus.value = dict[uiLang.value].status_sync_ok(created, errList.length)
      if (errList.length > 0) {
        erpStatus.value += '\n' + errList.join('\n')
      }
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
  
  try {
    const res = await getEmployees()
    if (res && res.employees) globalEmployees.value = res.employees
  } catch(e) { console.warn('Could not load employees', e) }
  
  loadHistory()
})
</script>

<template>
  <CTSplashScreen v-if="authState === 'loading'" />
  <CTAccessDenied v-else-if="authState === 'denied'" />
  <div v-else class="flex flex-col h-screen w-full bg-background overflow-hidden text-foreground">
  
    <!-- UNIFIED TOPBAR -->
    <header class="h-[72px] w-full flex items-center border-b border-border bg-background/80 backdrop-blur shrink-0 z-40 px-6">
      <div class="w-[260px] shrink-0"></div>
      <div class="flex-1 flex justify-center items-center">
         <h1 class="font-bold text-lg tracking-tight text-primary m-0">2AS Worksuite</h1>
      </div>
      <div class="w-[260px] shrink-0 flex items-center justify-end gap-6">
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

    <div class="flex flex-1 overflow-hidden w-full">
      <!-- SIDEBAR -->
      <aside class="w-[260px] border-r border-border bg-muted/10 flex flex-col h-full shrink-0">
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
              <button @click="activeTab='voice_task'" :class="activeTab==='voice_task' ? 'text-primary font-medium' : 'text-muted-foreground hover:bg-muted/30'" class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors text-left bg-transparent border-none shadow-none focus:outline-none cursor-pointer" style="background: none; border: none; box-shadow: none;">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2c-1.7 0-3 1.2-3 2.6v6.8c0 1.4 1.3 2.6 3 2.6s3-1.2 3-2.6V4.6C15 3.2 13.7 2 12 2z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="m9 17 3 3 5-5"/></svg>
                {{ t('tab_voice_task') }}
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
      <!-- Scrollable content area -->
      <main class="flex-1 overflow-y-auto p-6 bg-muted/5 relative">
      <template v-if="activeTab === 'transcribe'">
        <div class="w-full flex flex-col gap-8 pb-10 mt-2">
          <!-- TRANSCRIBE SETTINGS CARD -->
          <el-card shadow="never" class="glow-effect">
            <template #header>
              <div>
                <h3 class="text-lg font-medium m-0">{{ t('audio_processing') }}</h3>
                <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('audio_desc') }}</p>
              </div>
            </template>
            
            <div class="flex flex-col gap-6">
               <div class="flex flex-col gap-1.5">
                 <label class="text-xs font-bold text-muted-foreground uppercase tracking-wider">{{ t('target_lang') }}</label>
                 <el-select v-model="language" style="width: 200px">
                   <el-option v-for="l in languages" :key="l.val" :label="l.label" :value="l.val" />
                 </el-select>
               </div>
               
               <el-divider class="my-2" />
               
               <!-- Meeting Info -->
               <div class="flex flex-col gap-3">
                 <span class="text-sm font-bold text-foreground">Thông tin cuộc họp (Dùng cho Biên bản)</span>
                 <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                   <div class="flex flex-col gap-1.5" style="min-width: 220px;">
                     <label class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Ngày giờ bắt đầu</label>
                     <el-date-picker v-model="meetingStartTime" type="datetime" format="DD/MM/YYYY HH:mm" style="width: 100%" />
                   </div>
                   <div class="flex flex-col gap-1.5" style="min-width: 220px;">
                     <label class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Địa điểm</label>
                     <el-input v-model="meetingLocation" placeholder="Nhập địa điểm..." />
                   </div>
                   <div class="flex flex-col gap-1.5" style="min-width: 220px;">
                     <label class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Người chủ trì</label>
                     <el-select v-model="meetingChairperson" filterable placeholder="Chọn người chủ trì..." style="width: 100%">
                       <el-option v-for="emp in employeeOptions" :key="emp.value" :label="emp.label" :value="emp.value" />
                     </el-select>
                   </div>
                 </div>
               </div>
               
               <el-divider class="my-2" />
               
               <el-upload
                 drag
                 action="#"
                 :auto-upload="false"
                 :show-file-list="false"
                 accept="audio/*"
                 @change="file => handleFileChange({ target: { files: [file.raw] } })"
                 class="upload-zone w-full"
               >
                 <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                 <div class="el-upload__text">
                   Drag & drop a file here, or click to select
                   <div class="mt-2 text-primary font-medium">{{ audioFile ? audioFile.name : t('upload_support') }}</div>
                 </div>
               </el-upload>
            </div>
            
            <template #footer>
               <el-button type="primary" size="large" class="w-full h-12 text-lg" @click="startTranscribe" :loading="isTranscribing" :disabled="!audioFile">
                  {{ isTranscribing ? t('analyzing') : t('analyze_voice') }}
               </el-button>
               <div v-if="transcribeStatus && !isTranscribing" class="text-center text-sm font-medium mt-2 text-primary">
                  {{ transcribeStatus }}
               </div>
            </template>
          </el-card>
          
          <!-- AI FILTER + EXTRACT BUTTON ROW -->
          <div v-if="transcriptResults.length > 0" class="flex flex-wrap gap-3 items-center mt-2">
            <el-button
              @click="startCleanTranscript"
              :loading="isCleaning"
              :type="isCleaned ? 'primary' : 'default'"
              :plain="isCleaned"
              size="large"
              class="flex-1"
              style="min-width:180px;"
            >
              <template #icon v-if="!isCleaning">
                <el-icon v-if="isCleaned"><RefreshLeft /></el-icon>
                <el-icon v-else><MagicStick /></el-icon>
              </template>
              {{ isCleaning ? 'Đang lọc AI...' : (isCleaned ? '↩ Hoàn tác lọc' : '✨ AI Lọc hội thoại') }}
            </el-button>
            <el-button 
              type="primary" 
              size="large"
              @click="startExtractTasks" 
              :loading="isExtracting"
              :disabled="transcriptResults.length === 0" 
              class="flex-1" 
              style="min-width:180px;"
            >
              <template #icon v-if="!isExtracting"><Connection /></template>
              {{ isExtracting ? t('extracting') : t('extract_task') }}
            </el-button>
          </div>
          <el-alert v-if="extractStatus" :title="extractStatus" type="success" :closable="false" center />

          <!-- TRANSCRIPT RESULTS -->
          <el-card v-if="transcriptResults.length > 0" shadow="never">
            <template #header>
              <div class="flex justify-between items-center">
                <div>
                  <h3 class="text-lg font-medium m-0">{{ t('transcript_result') }}</h3>
                  <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('transcript_desc') }}</p>
                </div>
              </div>
            </template>
            <div class="log-view p-6 space-y-6 max-h-[250px] overflow-auto">
               <div v-for="(seg, idx) in transcriptResults" :key="idx" class="log-entry">
                  <div class="log-meta">
                     <span class="log-speaker">{{ seg[2] }}</span>
                     <span class="log-time">[{{ seg[0].toFixed(2) }}s]</span>
                  </div>
                  <p class="log-text">{{ seg[3] }}</p>
               </div>
            </div>
          </el-card>

          <!-- ATTENDEES PANEL -->
          <el-card v-if="transcriptResults.length > 0" shadow="never" style="border-color: var(--el-border-color)">
            <template #header>
              <div class="flex justify-between items-center">
                <div>
                  <h3 class="text-lg font-medium m-0 flex items-center gap-2">
                    <el-icon><User /></el-icon>
                    {{ t('attendees_title') }}
                  </h3>
                  <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('attendees_desc') }}</p>
                </div>
                <el-button
                  v-if="selectedAttendees.length > 0"
                  type="primary"
                  @click="reAnalyzeWithAttendees"
                  :loading="isReanalyzing"
                  :disabled="!audioFile"
                >
                  <template #icon v-if="!isReanalyzing"><RefreshRight /></template>
                  {{ isReanalyzing ? t('reanalyzing') : t('btn_reanalyze') }}
                </el-button>
              </div>
            </template>
            <div class="flex flex-wrap items-center gap-2">
              <el-tag
                v-for="name in selectedAttendees"
                :key="name"
                closable
                size="large"
                @close="removeAttendee(name)"
                effect="light"
              >
                {{ name }}
              </el-tag>

              <el-select
                :model-value="''"
                filterable
                placeholder="+ Tìm & thêm người..."
                style="width: 240px"
                @change="(val) => { if(val) { toggleAttendee(val); } }"
                :disabled="voiceDbSpeakers.length === 0"
              >
                <el-option
                  v-for="spk in voiceDbSpeakers"
                  :key="spk.speaker_name"
                  :label="spk.speaker_name"
                  :value="spk.speaker_name"
                >
                  <span style="float: left">{{ spk.speaker_name }}</span>
                  <span style="float: right; color: var(--el-text-color-secondary); font-size: 13px">{{ spk.email }}</span>
                </el-option>
              </el-select>
            </div>
            <p v-if="selectedAttendees.length === 0" class="text-xs text-muted-foreground italic mt-3">Chưa chọn ai. Thêm người vào danh sách để phân tích chính xác hơn.</p>
          </el-card>

          <!-- UNKNOWN SPEAKERS MAPPING -->
          <el-card v-if="unknownSpeakers.length > 0" shadow="never" style="border-color: var(--el-color-primary); border-width: 2px;">
            <template #header>
              <div>
                <h3 class="text-lg font-medium m-0 flex items-center gap-2 text-primary">
                  <el-icon><UserFilled /></el-icon>
                  Gán tên người tham dự
                </h3>
                <p class="text-sm text-muted-foreground m-0 mt-1">AI phát hiện các giọng nói chưa xác định được danh tính. Bạn vui lòng chọn tên nhân viên thực tế để hệ thống ghi chú vào Biên bản và Task.</p>
              </div>
            </template>
            <div class="flex flex-col gap-4">
              <div v-for="spk in unknownSpeakers" :key="spk" class="flex flex-col md:flex-row md:items-center gap-3 bg-muted/20 p-3 rounded-lg border border-border">
                <span class="font-bold text-sm min-w-[120px]">{{ spk }}</span>
                <el-select
                  v-model="speakerMapping[spk]"
                  filterable
                  placeholder="Chọn nhân viên..."
                  class="flex-1"
                >
                  <el-option v-for="emp in employeeOptions" :key="emp.value" :label="emp.label" :value="emp.value" />
                </el-select>
              </div>
              <div class="flex justify-end mt-2">
                <el-button type="primary" @click="updateIdentities">
                  Cập nhật danh tính
                </el-button>
              </div>
            </div>
          </el-card>

          <!-- TASK EXTRACTOR -->
          <!-- TASK EXTRACTOR -->
          <el-card v-if="transcriptResults.length > 0" shadow="never">
            <template #header>
              <div class="flex justify-between items-center">
                <div>
                  <h3 class="text-lg font-medium m-0">{{ t('task_list') }}</h3>
                  <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('task_desc') }}</p>
                </div>
                <div class="flex gap-2">
                  <el-button v-if="excelUrl && currentMeetingName" @click="downloadViaBackend(currentMeetingName, 'xlsx')" plain>
                     <template #icon><Download /></template>
                     {{ t('export_xlsx') }}
                  </el-button>
                  <el-button v-if="docxUrl && currentMeetingName" @click="downloadViaBackend(currentMeetingName, 'docx')" plain>
                     <template #icon><Document /></template>
                     {{ t('export_docx') }}
                  </el-button>
                  <el-button type="primary" plain @click="addTask">
                     <template #icon><Plus /></template>
                     {{ t('add_task') }}
                  </el-button>
                </div>
              </div>
            </template>
            <el-table :data="tasks" style="width: 100%" border size="small" class="task-table" :cell-style="{ verticalAlign: 'top', padding: '6px' }">
              <el-table-column header-align="center" type="index" label="#" width="50" align="center" />
              <el-table-column header-align="center" :label="t('col_name')" min-width="200">
                <template #default="{ row }">
                  <el-input v-model="row.title" />
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_assignee')" min-width="180">
                <template #default="{ row }">
                  <el-select v-model="row.assignee_display" filterable placeholder="Tìm người..." style="width: 100%">
                    <el-option v-for="emp in employeeOptions" :key="emp.value" :label="emp.label" :value="emp.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_project')" min-width="150">
                <template #default="{ row }">
                  <el-select v-model="row.project" style="width: 100%">
                    <el-option label="[Không có]" value="" />
                    <el-option v-for="p in getProjectsForHR(row.assignee_display)" :key="p[1]" :label="p[0]" :value="p[1]" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_start')" width="130">
                <template #default="{ row }">
                  <el-date-picker v-model="row.start_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" />
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_due')" width="130">
                <template #default="{ row }">
                  <el-date-picker v-model="row.due_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" />
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_weight')" width="90">
                <template #default="{ row }">
                  <el-input-number v-model="row.weight" :min="0" :max="100" :controls="false" style="width: 100%" />
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_desc')" min-width="200">
                <template #default="{ row }">
                  <el-input v-model="row.description" type="textarea" :rows="2" resize="none" />
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_del')" width="70" align="center">
                <template #default="{ $index }">
                  <el-button type="danger" circle plain @click="removeTask($index)">
                    <template #icon><Delete /></template>
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
            <template #footer>
               <div class="flex flex-col gap-3 w-full">
                 <div v-if="erpStatus"
                   class="w-full p-3 rounded-lg text-sm border font-mono whitespace-pre-line"
                   :class="erpStatus.includes('❌') ? 'bg-destructive/10 text-destructive border-destructive/20' : (erpStatus.includes('⏳') ? 'bg-muted text-foreground border-border' : 'bg-primary/10 text-primary border-primary/20')"
                 >{{ erpStatus }}</div>
                 <div class="flex justify-end">
                   <el-button type="primary" @click="syncToERP" :loading="isSyncing" :disabled="tasks.length === 0">
                     {{ t('btn_sync') }}
                   </el-button>
                 </div>
               </div>
            </template>
          </el-card>
        </div>
      </template>

      <template v-if="activeTab === 'enroll'">
         <div class="w-full flex flex-col gap-8 pb-10 mt-2">
            <el-card shadow="never" class="glow-effect">
                <template #header>
                   <div class="flex justify-between items-center">
                     <div>
                       <h3 class="text-lg font-medium m-0">{{ t('enroll_title') }}</h3>
                       <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('enroll_desc') }}</p>
                     </div>
                   </div>
                </template>
                
                <div class="flex flex-col gap-6">
                    <div class="bg-muted/20 p-4 rounded-md border border-border">
                       <h4 class="text-sm font-bold text-primary mb-2">Văn bản mẫu (đọc to và rõ ràng):</h4>
                       <p class="text-sm text-muted-foreground italic leading-relaxed">
                          "Chào hệ thống, tôi đang thực hiện ghi âm để cung cấp mẫu dữ liệu giọng nói cho trợ lý AI. 
                          Việc cung cấp một đoạn âm thanh rõ ràng và tự nhiên sẽ giúp AI dễ dàng nhận diện và phân biệt được giọng nói 
                          của tôi trong các cuộc họp trực tuyến hoặc khi thảo luận công việc với đồng nghiệp. 
                          Tôi hy vọng đoạn ghi âm này đủ độ dài và chi tiết để hệ thống học được các đặc trưng riêng biệt trong chất giọng của tôi."
                       </p>
                    </div>
                
                    <el-button @click="toggleRecording" :type="isRecording ? 'danger' : 'default'" :plain="!isRecording" size="large" class="w-full font-bold h-12 text-lg">
                       <template #icon>
                         <el-icon v-if="!isRecording"><Microphone /></el-icon>
                         <el-icon v-else><VideoPause /></el-icon>
                       </template>
                       {{ isRecording ? t('btn_stop') : t('btn_record') }}
                    </el-button>
                    
                    <div v-if="recordedAudioUrl" class="w-full bg-muted/30 p-4 rounded-md border border-border">
                       <audio :src="recordedAudioUrl" controls class="w-full"></audio>
                    </div>
                    
                    <el-divider>Hoặc</el-divider>
                    
                    <el-upload
                      drag
                      action="#"
                      :auto-upload="false"
                      :show-file-list="false"
                      accept="audio/*"
                      @change="file => handleEnrollFileChange({ target: { files: [file.raw] } })"
                      class="upload-zone w-full"
                    >
                      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                      <div class="el-upload__text">
                        Drag & drop a file here, or click to select
                        <div class="mt-2 text-primary font-medium">{{ (enrollAudioFile && !recordedAudioUrl) ? enrollAudioFile.name : 'Supported: .mp3, .wav' }}</div>
                      </div>
                    </el-upload>
                </div>
                
                <template #footer>
                    <el-button @click="submitEnrollment" type="primary" size="large" :loading="isEnrolling" :disabled="!enrollAudioFile" class="w-full h-12 text-lg">
                       {{ isEnrolling ? "⏳ Đang xử lý..." : t('btn_enroll') }}
                    </el-button>
                    <div v-if="enrollStatus" class="text-center text-sm font-medium mt-2" :class="enrollStatus.includes('✅') ? 'text-primary' : 'text-danger'">
                       {{ enrollStatus }}
                    </div>
                </template>
            </el-card>
         </div>
      </template>

      <template v-if="activeTab === 'voice_task'">
         <div class="w-full flex flex-col gap-8 pb-10 mt-2">
            <!-- VOICE TASK SETTINGS CARD -->
            <el-card shadow="never" class="glow-effect">
                <template #header>
                   <div class="flex justify-between items-center">
                     <div>
                       <h3 class="text-lg font-medium m-0">{{ t('voice_task_title') }}</h3>
                       <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('voice_task_desc') }}</p>
                     </div>
                   </div>
                </template>
                
                <div class="flex flex-col gap-6">
                    <div class="bg-primary/5 p-4 rounded-md border border-primary/20">
                       <h4 class="text-sm font-bold text-primary mb-2">Gợi ý câu lệnh mẫu:</h4>
                       <p class="text-sm text-muted-foreground italic leading-relaxed font-sans">
                          "{{ t('voice_task_placeholder') }}"
                       </p>
                    </div>
                
                    <el-button @click="toggleVoiceTaskRecording" :type="voiceTaskIsRecording ? 'danger' : 'default'" :plain="!voiceTaskIsRecording" size="large" class="w-full font-bold h-12 text-lg transition-all">
                       <template #icon>
                         <el-icon v-if="!voiceTaskIsRecording"><Microphone /></el-icon>
                         <el-icon v-else><VideoPause /></el-icon>
                       </template>
                       {{ voiceTaskIsRecording ? t('btn_stop') : t('btn_record') }}
                    </el-button>
                    
                    <el-divider>Hoặc</el-divider>
                    
                    <el-upload
                      drag
                      action="#"
                      :auto-upload="false"
                      :show-file-list="false"
                      accept="audio/*"
                      @change="file => handleVoiceTaskFileChange({ target: { files: [file.raw] } })"
                      class="upload-zone w-full"
                    >
                      <el-icon class="el-icon--upload"><upload-filled /></el-icon>
                      <div class="el-upload__text">
                        Kéo thả file vào đây hoặc bấm để chọn
                        <div class="mt-2 text-primary font-medium">{{ (voiceTaskAudioFile && !voiceTaskRecordedUrl) ? voiceTaskAudioFile.name : 'Hỗ trợ: .mp3, .wav' }}</div>
                      </div>
                    </el-upload>
                </div>
                
                <template #footer>
                    <el-button @click="submitVoiceTask" type="primary" size="large" :loading="isVoiceTaskProcessing" :disabled="!voiceTaskAudioFile" class="w-full h-12 text-lg">
                       {{ isVoiceTaskProcessing ? t('voice_task_parsing') : 'Bắt đầu xử lý lệnh giọng nói' }}
                    </el-button>
                    <div v-if="voiceTaskStatus" class="text-center text-sm font-medium mt-2" :class="voiceTaskStatus.includes('✅') ? 'text-primary' : 'text-danger'">
                       {{ voiceTaskStatus }}
                    </div>
                </template>
            </el-card>



            <!-- AI ASSISTANT CHAT BUBBLE (LUÔN HIỆN KHI CÓ TASK ĐỂ CHỈNH SỬA) -->
            <el-card v-if="parsedVoiceTask" shadow="hover" style="background: hsla(var(--primary)/0.03); margin-top: 1rem; border-color: var(--el-color-primary-light-7);">
                <template #header>
                   <div class="flex items-center gap-3">
                     <el-avatar :size="36" style="background: linear-gradient(135deg, #a855f7, #6366f1); font-size: 18px;">🤖</el-avatar>
                     <div>
                        <h3 class="text-primary font-medium m-0 flex items-center gap-2">Trợ lý AI</h3>
                        <p v-if="voiceTaskMissingFields && voiceTaskMissingFields.length > 0" class="text-sm text-danger m-0 font-medium">Phát hiện thông tin tạo Task chưa đầy đủ</p>
                        <p v-else class="text-sm m-0" style="color: #10b981; font-weight: 500;">Thông tin đã đầy đủ, bạn có thể lưu hoặc tiếp tục tinh chỉnh</p>
                     </div>
                   </div>
                </template>
                <div class="flex flex-col gap-4">
                   <!-- Missing Fields Badges -->
                   <div v-if="voiceTaskMissingFields && voiceTaskMissingFields.length > 0" class="flex flex-wrap gap-2 items-center">
                      <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Thông tin còn thiếu:</span>
                      <el-tag v-if="voiceTaskMissingFields.includes('project')" type="danger" effect="light" round>
                         <el-icon><Warning /></el-icon> Thiếu Dự án
                      </el-tag>
                      <el-tag v-if="voiceTaskMissingFields.includes('assignee')" type="danger" effect="light" round>
                         <el-icon><Warning /></el-icon> Thiếu Người phụ trách
                      </el-tag>
                      <el-tag v-if="voiceTaskMissingFields.includes('end_date')" type="danger" effect="light" round>
                         <el-icon><Warning /></el-icon> Thiếu Hạn chót
                      </el-tag>
                   </div>

                   <!-- AI Clarification Question -->
                   <div class="p-4 bg-background border border-border rounded-lg leading-relaxed text-base font-medium font-sans">
                      "{{ (voiceTaskMissingFields && voiceTaskMissingFields.length > 0) ? voiceTaskClarification : 'Tất cả thông tin cốt lõi đã sẵn sàng! Bạn muốn bổ sung hay thay đổi gì nữa không?' }}"
                   </div>

                   <el-divider style="margin: 4px 0" />

                   <!-- Voice Refinement input -->
                   <div class="flex flex-col gap-3">
                      <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Nói hoặc tải lên câu lệnh để chỉnh sửa:</span>
                      
                      <el-button @click="toggleVoiceTaskRefineRecording" :type="voiceTaskRefineIsRecording ? 'danger' : 'default'" :plain="!voiceTaskRefineIsRecording" size="large" class="w-full font-bold h-11 transition-all">
                         <template #icon>
                           <el-icon v-if="!voiceTaskRefineIsRecording"><Microphone /></el-icon>
                           <el-icon v-else><VideoPause /></el-icon>
                         </template>
                         {{ voiceTaskRefineIsRecording ? 'Dừng ghi âm bổ sung' : 'Nói để bổ sung/chỉnh sửa thông tin' }}
                      </el-button>

                      <div v-if="voiceTaskRefineRecordedUrl" class="w-full bg-background p-3 rounded-md border border-border flex items-center gap-4">
                         <audio :src="voiceTaskRefineRecordedUrl" controls class="flex-1"></audio>
                      </div>

                      <el-divider>Hoặc chọn file</el-divider>

                      <div class="flex items-center gap-3">
                         <input type="file" id="voice-task-refine-upload" @change="handleVoiceTaskRefineFileChange" accept="audio/*" style="display:none" />
                         <label for="voice-task-refine-upload" class="flex-1">
                            <el-button tag="span" style="width: 100%" size="large" plain>
                               <template #icon><Folder /></template>
                               {{ voiceTaskRefineAudioFile ? voiceTaskRefineAudioFile.name : 'Chọn file ghi âm bổ sung' }}
                            </el-button>
                         </label>
                         <el-button @click="submitVoiceTaskRefine" type="primary" size="large" :loading="isVoiceTaskProcessing" :disabled="!voiceTaskRefineAudioFile" class="flex-1">
                            <template #icon><Position /></template>
                            Gửi yêu cầu chỉnh sửa
                         </el-button>
                      </div>
                   </div>
                </div>
            </el-card>

            <!-- PARSED TASK CARD (PREVIEW & EDIT) -->
            <el-card v-if="parsedVoiceTask" shadow="never" style="margin-top: 1rem; border-color: var(--el-color-primary-light-7);">
                <template #header>
                   <h3 class="text-primary text-lg font-medium m-0 flex items-center gap-2">
                     <el-icon><EditPen /></el-icon>
                      Xem trước và hiệu chỉnh Task tạo từ AI
                   </h3>
                   <p class="text-sm text-muted-foreground m-0 mt-1">Các thông tin được trích xuất tự động qua OpenAI. Vui lòng xác nhận trước khi lưu.</p>
                </template>
                
                <div class="flex flex-col gap-6">
                   <!-- Transcript Text -->
                   <div class="flex flex-col gap-1.5 p-3 bg-muted/20 rounded-md border border-border">
                     <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Văn bản chuyển đổi từ giọng nói (STT):</span>
                     <p class="text-sm font-medium leading-relaxed font-sans">"{{ voiceTaskTranscript }}"</p>
                   </div>

                   <!-- Form Fields Table -->
                   <el-table :data="[parsedVoiceTask]" style="width: 100%" border size="small" :cell-style="{ verticalAlign: 'top', padding: '6px' }">
                      <el-table-column :label="t('col_name')" min-width="200" header-align="center">
                        <template #default="{ row }">
                          <div :class="{ 'missing-field': !row.title }">
                            <el-input v-model="row.title" placeholder="⚠️ Chưa có tên task" />
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column :label="t('col_assignee')" min-width="180" header-align="center">
                        <template #default="{ row }">
                          <div :class="{ 'missing-field': voiceTaskMissingFields.includes('assignee') }">
                            <el-select v-model="row.assignee_display" filterable placeholder="⚠️ Chưa có người thực hiện" style="width: 100%">
                              <el-option v-for="emp in employeeOptions" :key="emp.value" :label="emp.label" :value="emp.value" />
                            </el-select>
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column :label="t('col_project')" min-width="150" header-align="center">
                        <template #default="{ row }">
                          <div :class="{ 'missing-field': voiceTaskMissingFields.includes('project') }">
                            <el-select v-model="row.project" style="width: 100%" placeholder="⚠️ Chưa có dự án">
                              <el-option label="[Không có]" value="" />
                              <el-option v-for="p in voiceTaskProjects" :key="p.name" :label="p.project_name ? p.project_name : p.name" :value="p.name" />
                            </el-select>
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column header-align="center" :label="t('col_start')" width="130">
                        <template #default="{ row }">
                          <el-date-picker v-model="row.start_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" />
                        </template>
                      </el-table-column>
                      <el-table-column header-align="center" :label="t('col_due')" width="130">
                        <template #default="{ row }">
                          <div :class="{ 'missing-field': voiceTaskMissingFields.includes('end_date') }">
                            <el-date-picker v-model="row.due_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" placeholder="⚠️ Chưa có hạn chót" />
                          </div>
                        </template>
                      </el-table-column>
                      <el-table-column header-align="center" :label="t('col_desc')" min-width="250">
                        <template #default="{ row }">
                          <el-input v-model="row.description" type="textarea" :rows="3" resize="none" />
                        </template>
                      </el-table-column>
                   </el-table>
                </div>

                <template #footer>
                   <div class="flex justify-between items-center w-full">
                     <span class="text-sm font-semibold font-mono" :class="voiceTaskSyncStatus.includes('✅') ? 'text-primary' : 'text-danger'">{{ voiceTaskSyncStatus }}</span>
                     <el-button @click="syncVoiceTaskToERP" type="primary" size="large" :loading="isVoiceTaskSyncing">
                        {{ isVoiceTaskSyncing ? '⏳ Đang đồng bộ...' : 'Tạo & Đồng bộ Task lên ERPNext' }}
                     </el-button>
                   </div>
                </template>
            </el-card>
         </div>
      </template>

      <template v-if="activeTab === 'view_meeting'">
         <div class="w-full flex flex-col gap-8 pb-10 mt-2">
            <el-card shadow="never" class="glow-effect">
                <template #header>
                  <h3 class="text-lg font-medium m-0">{{ currentMeeting?.title }}</h3>
                  <p class="text-sm text-muted-foreground m-0 mt-1">{{ currentMeeting?.date }} &middot; Trạng thái: {{ currentMeeting?.status }}</p>
                </template>
                
                <div class="flex flex-col gap-6">
                  <!-- Actions -->
                  <div class="flex flex-wrap items-center gap-4 p-4 bg-muted/30 rounded-lg border border-border">
                     <el-button v-if="currentMeeting?.audio_file" tag="a" :href="currentMeeting.audio_file" target="_blank" plain>
                       <template #icon><VideoPlay /></template>
                       Nghe lại Audio
                     </el-button>
                     
                     <el-button v-if="currentMeeting?.minute_docx" @click="downloadViaBackend(currentMeeting.name, 'docx')" type="primary" plain>
                       <template #icon><Document /></template>
                       Tải Biên bản (Word)
                     </el-button>
                     
                     <el-button v-if="currentMeeting?.task_xlsx" @click="downloadViaBackend(currentMeeting.name, 'xlsx')" type="success" plain>
                       <template #icon><Download /></template>
                       Tải Tasks (Excel)
                     </el-button>
                  </div>

                  <!-- Parsed JSON Transcript (raw_results) -->
                  <div class="mt-4" v-if="currentMeeting?.raw_results">
                    <h4 class="text-sm font-bold uppercase tracking-wider text-muted-foreground mb-4">Nội dung hội thoại</h4>
                    <div class="bg-muted/10 border border-border rounded-lg max-h-[550px] overflow-y-auto">
                      <div class="p-6 space-y-4">
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
                    <div class="bg-muted/10 border border-border rounded-lg p-6 max-h-[500px] overflow-y-auto flex flex-col gap-6">
                       <div v-for="(msg, idx) in parseTranscript(currentMeeting.transcript)" :key="idx" class="flex gap-3">
                          <div class="flex flex-col gap-1.5 flex-1">
                            <div class="flex items-center gap-2">
                              <span class="text-sm font-bold text-foreground">{{ msg.speaker }}</span>
                              <span class="text-xs text-muted-foreground">{{ msg.time }}</span>
                            </div>
                            <div class="text-sm text-foreground bg-white dark:bg-muted/20 border border-border rounded-2xl rounded-tl-none p-3.5 leading-relaxed shadow-sm w-fit max-w-[90%] whitespace-pre-wrap break-words font-sans">
                               {{ msg.text }}
                            </div>
                          </div>
                       </div>
                    </div>
                  </div>
                </div>
            </el-card>
         </div>
      </template>

    </main>
    </div>
    </div>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body {
  overflow-x: hidden;
  max-width: 100vw;
}


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
.log-text { font-size: 0.875rem; line-height: 1.5; margin: 0; color: hsl(var(--foreground)); word-break: break-word; white-space: pre-wrap; }

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

/* Missing field highlight in voice-to-task table */
.missing-field { border-radius: 6px; outline: 2px solid var(--el-color-danger); outline-offset: 1px; }
.missing-field .el-input__wrapper,
.missing-field .el-select .el-input__wrapper,
.missing-field .el-date-editor { box-shadow: none !important; }

/* Task table: allow row height to grow with content */
.task-table .el-table__cell { height: auto !important; overflow: visible !important; }
.task-table .el-table__row td { vertical-align: top; }
.task-table .el-input__wrapper,
.task-table .el-select .el-input__wrapper { min-height: 32px; height: auto; }
.task-table .el-textarea__inner { min-height: 56px !important; resize: vertical; }
</style>
