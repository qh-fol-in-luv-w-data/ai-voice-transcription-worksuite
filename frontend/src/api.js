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

export async function transcribeAudio(file, language, filterSpeakers = null) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('language', language)
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

export async function extractTasks(results, modelType, meetingName) {
  const res = await api.post('/api/method/voice_app.api.extract_tasks', {
    results: results,
    model_type: modelType,
    meeting_name: meetingName
  })
  return res.data.message
}

export async function getMeetingHistory() {
  const res = await api.get('/api/method/voice_app.api.get_meeting_history')
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

export async function cleanTranscript(results, modelType, meetingName) {
  const res = await api.post('/api/method/voice_app.api.clean_transcript', {
    results: results,
    model_type: modelType,
    meeting_name: meetingName
  })
  return res.data.message
}

export default api
