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
  localEnrollStatus.value = "⏳ " + (t('status_enrolling') === 'status_enrolling' ? 'Đang đăng ký...' : t('status_enrolling'))
  
  try {
    const msg = await enrollVoice(localEnrollAudioFile.value)
    if (msg && msg.message) {
      localEnrollStatus.value = "✅ " + msg.message
    } else {
      localEnrollStatus.value = "✅ " + msg
    }
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
  <div class="w-full max-w-[1200px] px-4 md:px-8 mx-auto flex flex-col gap-md py-4 fade-in flex-1 min-h-0 h-full">
    <header class="mb-2 shrink-0">
      <h2 class="font-headline-lg text-headline-lg text-gray-900 dark:text-on-surface mb-1">{{ t('enroll_title') }}</h2>
      <p class="font-body-md text-body-md text-gray-500 dark:text-on-surface-variant max-w-2xl">{{ t('enroll_desc') }}</p>
    </header>
    
    <div class="grid grid-cols-1 gap-lg">
      <!-- Sample Text Card -->
      <div class="flex flex-col gap-md">
        <h3 class="font-label-caps text-label-caps text-gray-400 dark:text-on-surface-variant uppercase tracking-wider">Đoạn văn mẫu</h3>
        <div class="bg-gray-50 dark:bg-surface-container/50 p-lg rounded-xl h-full border border-gray-200 dark:border-outline-variant">
          <p class="font-body-lg text-body-lg leading-relaxed text-gray-900 dark:text-on-surface italic">
            "Chào hệ thống, tôi đang thực hiện ghi âm để cung cấp mẫu dữ liệu giọng nói cho trợ lý AI. Việc cung cấp một đoạn âm thanh rõ ràng và tự nhiên sẽ giúp AI dễ dàng nhận diện và phân biệt được giọng nói của tôi trong các cuộc họp trực tuyến hoặc khi thảo luận công việc với đồng nghiệp. Tôi hy vọng đoạn ghi âm này đủ độ dài và chi tiết để hệ thống học được các đặc trưng riêng biệt trong chất giọng của tôi."
          </p>
        </div>
      </div>
      
      <!-- Action Area -->
      <div class="flex flex-col gap-md flex-1">
        <h3 class="font-label-caps text-label-caps text-gray-400 dark:text-on-surface-variant uppercase tracking-wider">Cung cấp mẫu giọng nói</h3>
        <div class="bg-white dark:bg-[#0a0f1c]/90 border border-gray-200 dark:border-white/5 rounded-3xl p-6 lg:p-8 flex flex-col items-center justify-center shadow-2xl relative overflow-hidden min-h-[400px]">
          <div class="w-full max-w-md flex flex-col items-center gap-md relative z-10">
            
            <!-- Record Button -->
            <button @click="localToggleRecording" :class="['flex items-center justify-center gap-sm font-headline-md text-lg px-lg py-3 rounded-full transition-all active:scale-95 w-full max-w-[280px]', localIsRecording ? 'bg-error text-on-error shadow-[0_0_25px_rgba(255,180,171,0.5)] animate-pulse' : 'bg-primary text-on-primary shadow-[0_0_15px_rgba(192,193,255,0.3)] hover:shadow-[0_0_25px_rgba(192,193,255,0.5)]']">
              <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">{{ localIsRecording ? 'stop_circle' : 'mic' }}</span>
              {{ localIsRecording ? t('btn_stop') : 'Bắt đầu thu âm' }}
            </button>
            
            <audio v-if="localRecordedAudioUrl" :src="localRecordedAudioUrl" controls class="w-full max-w-md h-12 rounded-full shadow-sm mt-xs"></audio>
            
            <div class="w-full flex items-center gap-md">
              <div class="h-px bg-gray-200 dark:bg-outline-variant flex-1"></div>
              <span class="font-label-caps text-label-caps text-gray-400 dark:text-on-surface-variant">HOẶC</span>
              <div class="h-px bg-gray-200 dark:bg-outline-variant flex-1"></div>
            </div>
            
            <!-- Drag and Drop Zone -->
            <div class="flex flex-col items-center gap-sm cursor-pointer opacity-70 hover:opacity-100 transition-opacity relative w-full p-4 rounded-lg hover:bg-gray-50 dark:hover:bg-surface-variant/30">
              <input type="file" accept="audio/*" @change="localHandleEnrollFileChange" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20" />
              <div class="w-16 h-16 rounded-full bg-gray-100 dark:bg-surface-variant flex items-center justify-center mb-sm">
                <span class="material-symbols-outlined text-3xl text-gray-500 dark:text-on-surface-variant">cloud_upload</span>
              </div>
              <p class="font-body-md text-body-md text-gray-900 dark:text-on-surface text-center">Kéo thả file vào đây hoặc bấm để chọn</p>
              <p class="font-body-sm text-body-sm text-primary font-medium" v-if="localEnrollAudioFile">{{ localEnrollAudioFile.name }}</p>
              <p class="font-body-sm text-body-sm text-gray-500 dark:text-on-surface-variant" v-else>Hỗ trợ: .mp3, .wav</p>
            </div>
            
          </div>
        </div>
      </div>
    </div>
    
    <!-- Final Action -->
    <div class="mt-4 flex flex-col items-center pt-4 border-t border-gray-200 dark:border-outline-variant justify-center gap-md shrink-0">
      <button @click="localSubmitEnrollment" :disabled="localIsEnrolling || !localEnrollAudioFile" :class="['font-headline-md text-lg px-xl py-sm rounded-lg transition-colors min-w-[200px] flex items-center justify-center gap-2', (localIsEnrolling || !localEnrollAudioFile) ? 'bg-gray-100 text-gray-400 dark:bg-surface-variant dark:text-on-surface-variant opacity-50 cursor-not-allowed' : 'bg-primary-container text-white hover:bg-primary active:scale-95']">
        <span v-if="localIsEnrolling" class="material-symbols-outlined animate-spin text-[20px]">autorenew</span>
        {{ localIsEnrolling ? t('status_enrolling') : 'Đăng ký Hệ thống' }}
      </button>
      
      <div v-if="localEnrollStatus" class="font-body-md font-medium text-center px-4 py-2 rounded-md" :class="localEnrollStatus.includes('❌') ? 'bg-error/10 text-error' : (localEnrollStatus.includes('⏳') ? 'bg-surface-variant text-on-surface' : 'bg-primary/10 text-primary')">
        {{ localEnrollStatus }}
      </div>
    </div>
  </div>
</template>
