<script setup>
import { onMounted, watch } from 'vue'
import { initSession, useSession } from './utils/session'
import { getEmployees, getEnrolledSpeakers } from './api'
import { dbEmployees, voiceDbSpeakers, loadHistory } from './composables/useVoiceApp'
import CTSplashScreen from './components/CTSplashScreen.vue'
import CTAccessDenied from './components/CTAccessDenied.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'

// Import all views
import VoiceTranscribe from './views/VoiceTranscribe.vue'
import VoiceEnroll from './views/VoiceEnroll.vue'
import VoiceTask from './views/VoiceTask.vue'
import MeetingHistory from './views/MeetingHistory.vue'

import { activeTab, uiLang, isDark } from './composables/useVoiceApp'
import { getElevenLabsInfo } from './api' // Wait, I will just use standard imports if needed

// Session
const { authState } = useSession()

onMounted(async () => {
  await initSession('/api/method/voice_app.api.get_context')
  if (authState.value !== 'authorized') return

  // Load essential data
  try {
    const res = await getElevenLabsInfo()
  } catch (e) { console.warn(e) }
  
  try {
    const res = await getEnrolledSpeakers()
    if (res && res.speakers) voiceDbSpeakers.value = res.speakers
  } catch(e) { console.warn('Could not load enrolled speakers', e) }
  
  try {
    const res = await getEmployees()
    if (res && res.employees) dbEmployees.value = res.employees
  } catch(e) { console.warn('Could not load employees', e) }
  
  loadHistory()
})

watch(isDark, (val) => {
  if (val) {
    document.documentElement.classList.add('dark')
  } else {
    document.documentElement.classList.remove('dark')
  }
}, { immediate: true })
</script>

<template>
  <CTSplashScreen v-if="authState === 'loading'" />
  <CTAccessDenied v-else-if="authState === 'denied'" />
  <div v-else class="h-screen w-full flex overflow-hidden bg-background dark:bg-background text-on-background">
    <!-- Sidebar -->
    <AppSidebar class="z-20 shrink-0" />
    
    <!-- Main Area -->
    <div class="flex-1 flex flex-col h-screen min-w-0 bg-background overflow-hidden relative md:ml-[280px]">
      <AppHeader />
      
      <!-- Scrollable content area -->
      <main class="flex-1 overflow-y-auto p-4 md:p-6 bg-surface-container-lowest relative text-on-background">
        <VoiceTranscribe v-if="activeTab === 'transcribe'" />
        <VoiceEnroll v-if="activeTab === 'enroll'" />
        <VoiceTask v-if="activeTab === 'voice_task'" />
        <MeetingHistory v-if="activeTab === 'view_meeting'" />
      </main>
    </div>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
body {
  overflow-x: hidden;
  max-width: 100vw;
}
</style>
