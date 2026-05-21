<script setup>
import { enrollAudioFile, recordedAudioUrl, isRecording, enrollStatus, isEnrolling, dict, uiLang } from '../composables/useVoiceApp'

const t = (key) => dict[uiLang.value][key] || key

// Note: handleEnrollFileChange, toggleRecording, submitEnrollment need to be exported from useVoiceApp 
// or defined here. I will define them here so it's simpler.

import { ref } from 'vue'
import { enrollVoice } from '../api'

const localEnrollAudioFile = enrollAudioFile
const localRecordedAudioUrl = recordedAudioUrl
const localIsRecording = isRecording
const localEnrollStatus = enrollStatus
const localIsEnrolling = isEnrolling
const mediaRecorder = ref(null)
const audioChunks = ref([])

const localHandleEnrollFileChange = (e) => {
  if (e.target.files.length > 0) {
    localEnrollAudioFile.value = e.target.files[0]
    localRecordedAudioUrl.value = ''
  }
}

const localToggleRecording = async () => {
  if (localIsRecording.value) {
    mediaRecorder.value.stop()
    localIsRecording.value = false
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
      localEnrollAudioFile.value = blob
      localEnrollAudioFile.value.name = 'recorded_audio.wav'
      localRecordedAudioUrl.value = URL.createObjectURL(blob)
      stream.getTracks().forEach(t => t.stop())
    }
    
    mediaRecorder.value.start()
    localIsRecording.value = true
  } catch(e) {
    alert("Lỗi truy cập Micro: " + e.message)
  }
}

const localSubmitEnrollment = async () => {
  if (!localEnrollAudioFile.value) {
    alert(t('alert_no_file'))
    return
  }
  localIsEnrolling.value = true
  localEnrollStatus.value = "⏳ Đang đăng ký..."
  
  try {
    const msg = await enrollVoice(localEnrollAudioFile.value)
    localEnrollStatus.value = "✅ " + msg
  } catch(e) {
    if (e.response?.data?.message) {
      localEnrollStatus.value = "❌ " + e.response.data.message
    } else {
      localEnrollStatus.value = "❌ " + t('error_connect')
    }
  } finally {
    localIsEnrolling.value = false
  }
}

</script>

<template>
  <div class="max-w-2xl mx-auto w-full flex flex-col gap-8 pb-10 mt-10 fade-in">
    <div class="shadcn-card glow-effect">
      <div class="card-header border-b border-border bg-muted/10">
        <h3 class="card-title text-xl">{{ t('enroll_title') }}</h3>
        <p class="card-description">{{ t('enroll_desc') }}</p>
      </div>
      <div class="card-content flex flex-col gap-6 mt-6">
        
        <div class="flex items-center gap-4 p-6 border-2 border-dashed border-border rounded-xl bg-muted/5 hover:bg-muted/10 transition-colors">
            <input type="file" accept="audio/*" @change="localHandleEnrollFileChange" class="hidden" id="enroll-upload" />
            <label for="enroll-upload" class="shadcn-btn shadcn-btn-outline cursor-pointer shrink-0">
               <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
               Chọn file Audio
            </label>
            <span class="text-sm text-muted-foreground truncate flex-1">
              {{ localEnrollAudioFile ? localEnrollAudioFile.name : 'Chưa có file nào được chọn' }}
            </span>
        </div>

        <div class="flex items-center gap-4">
            <div class="h-px bg-border flex-1"></div>
            <span class="text-xs text-muted-foreground uppercase tracking-widest font-semibold">HOẶC</span>
            <div class="h-px bg-border flex-1"></div>
        </div>

        <div class="flex flex-col items-center gap-4 py-4">
            <button 
              @click="localToggleRecording" 
              :class="['w-20 h-20 rounded-full flex items-center justify-center transition-all duration-300 shadow-lg', localIsRecording ? 'bg-destructive animate-pulse scale-105 shadow-destructive/40' : 'bg-primary hover:scale-105 shadow-primary/40']"
            >
              <svg v-if="localIsRecording" xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><rect x="6" y="6" width="12" height="12"></rect></svg>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>
            </button>
            <span class="text-sm font-medium" :class="localIsRecording ? 'text-destructive' : 'text-muted-foreground'">
               {{ localIsRecording ? t('btn_stop') : t('btn_record') }}
            </span>
            <audio v-if="localRecordedAudioUrl" :src="localRecordedAudioUrl" controls class="mt-4 w-full max-w-md h-10 rounded-full bg-muted/30"></audio>
        </div>

        <div class="pt-6 border-t border-border mt-2">
            <button 
              @click="localSubmitEnrollment" 
              :disabled="localIsEnrolling || !localEnrollAudioFile" 
              class="shadcn-btn shadcn-btn-primary w-full h-12 text-lg shadow-lg shadow-primary/20"
            >
               <svg v-if="!localIsEnrolling" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>
               <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
               {{ t('btn_enroll') }}
            </button>
            
            <div v-if="localEnrollStatus" 
                 class="mt-4 p-4 rounded-lg text-sm border font-medium flex items-center justify-center animate-in fade-in slide-in-from-bottom-2"
                 :class="localEnrollStatus.includes('❌') ? 'bg-destructive/10 text-destructive border-destructive/20' : (localEnrollStatus.includes('⏳') ? 'bg-muted text-foreground border-border' : 'bg-primary/10 text-primary border-primary/20')">
               {{ localEnrollStatus }}
            </div>
        </div>

      </div>
    </div>
  </div>
</template>
