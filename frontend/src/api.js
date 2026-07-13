import axios from 'axios'

const api = axios.create({
  baseURL: '/',
  withCredentials: true
})

import { getCsrfToken, getSessionId } from './utils/session'

api.interceptors.request.use(config => {
  const csrf = getCsrfToken()
  if (csrf) config.headers['X-Frappe-CSRF-Token'] = csrf

  const sid = getSessionId()
  if (sid) config.headers['X-App-Session-Id'] = sid
  
  return config;
})

export async function transcribeAudio(file, filterSpeakers = null, sttMode = 'google') {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('stt_mode', sttMode)
  if (filterSpeakers && filterSpeakers.length > 0) {
    formData.append('filter_speakers', JSON.stringify(filterSpeakers))
  }

  const res = await api.post('/api/method/voice_app.api.transcribe_audio', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return res.data.message
}

export async function extractTasks(results, modelType, meetingName, startTime = null, endTime = null, location = null, chairperson = null) {
  const res = await api.post('/api/method/voice_app.api.extract_tasks', {
    results: results,
    model_type: modelType,
    meeting_name: meetingName,
    start_time: startTime,
    end_time: endTime,
    location: location,
    chairperson: chairperson
  })
  return res.data.message
}

export async function getMeetingHistory() {
  const res = await api.get('/api/method/voice_app.api.get_meeting_history')
  return res.data.message
}

export async function renameMeeting(meetingName, newTitle) {
  const res = await api.post('/api/method/voice_app.meeting_api.rename_meeting', {
    meeting_name: meetingName,
    new_title: newTitle
  })
  return res.data
}

export async function getEmployees() {
  const res = await api.get('/api/method/voice_app.api.get_employees')
  return res.data.message
}

export async function syncTasksToERP(tasks) {
  const res = await api.post('/api/method/voice_app.api.sync_tasks_to_erp', {
    tasks: tasks
  })
  return res.data.message
}

export async function getElevenLabsInfo() {
  const res = await api.get('/api/method/voice_app.api.get_elevenlabs_info')
  return res.data.message
}

export async function enrollVoice(audioBlob) {
  const formData = new FormData()
  formData.append('file', audioBlob, 'voice_record.wav')

  const res = await api.post('/api/method/voice_app.api.enroll_voice', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return res.data.message
}



export async function getEnrolledSpeakers() {
  const res = await api.get('/api/method/voice_app.api.get_enrolled_speakers')
  return res.data.message
}

export async function cleanTranscript(results, modelType, meetingName, customVocabulary = '') {
  const res = await api.post('/api/method/voice_app.api.clean_transcript', {
    results: results,
    model_type: modelType,
    meeting_name: meetingName,
    custom_vocabulary: customVocabulary
  })
  return res.data.message
}

export async function updateMeetingResults(meetingName, results) {
  const res = await api.post('/api/method/voice_app.api.update_meeting_results', {
    meeting_name: meetingName,
    results: results
  })
  return res.data.message
}

export async function updateTranscriptText(meetingName, results) {
  const res = await api.post('/api/method/voice_app.api.update_transcript_text', {
    meeting_name: meetingName,
    results: results
  })
  return res.data.message
}

export async function enrollMappedSpeakers(meetingName, mappings) {
  const res = await api.post('/api/method/voice_app.api.map_and_enroll_speakers', {
    meeting_name: meetingName,
    mappings: mappings
  })
  return res.data.message
}

export async function voiceToTask(file, existingTask = null) {
  const formData = new FormData()
  formData.append('file', file)
  if (existingTask) {
    formData.append('existing_task', JSON.stringify(existingTask))
  }

  const res = await api.post('/api/method/voice_app.api.voice_to_task', formData, {
    headers: {
      'Content-Type': 'multipart/form-data'
    }
  })
  return res.data.message
}

export async function checkMeetingStatus(meetingName) {
  const res = await api.get('/api/method/voice_app.api.check_meeting_status', {
    params: { meeting_name: meetingName }
  })
  return res.data.message
}

export async function checkExtractStatus(meetingName) {
  const res = await api.get('/api/method/voice_app.api.check_extract_status', {
    params: { meeting_name: meetingName }
  })
  return res.data.message
}

export async function checkCleanStatus(meetingName) {
  const res = await api.get('/api/method/voice_app.api.check_clean_status', {
    params: { meeting_name: meetingName }
  })
  return res.data.message
}


export async function resumeTranscription(meetingName) {
  const res = await api.post('/api/method/voice_app.api.resume_transcription', {
    meeting_name: meetingName
  })
  return res.data.message
}

export async function undoMapping(meetingName) {
  const res = await api.post('/api/method/voice_app.api.undo_mapping', {
    meeting_name: meetingName
  })
  return res.data.message
}

export async function getGlobalVocabulary() {
  const res = await api.get('/api/method/voice_app.api.get_global_vocabulary')
  // Frappe whitelist with a dict returns { message: { status: "success", message: "..." } }
  if (res.data.message && typeof res.data.message === 'object') {
    return res.data.message.message
  }
  return res.data.message
}

export async function saveGlobalVocabulary(vocabulary) {
  const res = await api.post('/api/method/voice_app.api.save_global_vocabulary', {
    vocabulary: vocabulary
  })
  return res.data.message
}

export default api
