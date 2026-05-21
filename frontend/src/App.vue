<script setup>
import { onMounted } from 'vue'
import { initSession, useSession } from './utils/session'
import { getEnrolledSpeakers } from './api'
import {
  activeTab, meetingHistory, currentMeeting, isTaskModalOpen,
  tasks, dbEmployees, hrProjectsMap, docxUrl, excelUrl,
  selectedAttendees, voiceDbSpeakers, isReanalyzing, dict, uiLang,
  loadHistory, currentLocalDate, toggleLang, toggleDark
} from './composables/useVoiceApp'
import { extractTasks, syncTasksToERP } from './api'

import CTSplashScreen from './components/CTSplashScreen.vue'
import CTAccessDenied from './components/CTAccessDenied.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'
import VoiceTranscribe from './views/VoiceTranscribe.vue'
import VoiceEnroll from './views/VoiceEnroll.vue'
import MeetingHistory from './views/MeetingHistory.vue'
import TaskModal from './components/TaskModal.vue'

const { authState } = useSession()
const t = (key) => dict[uiLang.value][key] || key

onMounted(async () => {
  await initSession('/api/method/voice_app.api.get_context')
  if (authState.value !== 'authorized') return

  try {
    const res = await getEnrolledSpeakers()
    if (res && res.speakers) voiceDbSpeakers.value = res.speakers
  } catch(e) { console.warn('Could not load enrolled speakers', e) }
  
  loadHistory()
})

const handleTaskModalClose = () => {
  isTaskModalOpen.value = false
}

const handleRemoveTask = (idx) => {
  tasks.value.splice(idx, 1)
}

const handleAddTask = () => {
  tasks.value.push({
    title: '', assignee_display: '', project: '',
    start_date: '', due_date: '', description: ''
  })
}

const handleSyncERP = async () => {
  if (tasks.value.length === 0) return
  try {
    const res = await syncTasksToERP(tasks.value)
    if (res.status === 'success') {
      alert("Đồng bộ thành công!")
    } else {
      alert("Lỗi đồng bộ: " + res.message)
    }
  } catch(e) {
    alert("Lỗi kết nối khi đồng bộ")
  }
}

const handleToggleAttendee = (name) => {
  if (selectedAttendees.value.includes(name)) {
    selectedAttendees.value = selectedAttendees.value.filter(n => n !== name)
  } else {
    selectedAttendees.value.push(name)
  }
}

const handleRemoveAttendee = (name) => {
  selectedAttendees.value = selectedAttendees.value.filter(n => n !== name)
}

// Chức năng reanalyze có thể được định nghĩa lại ở đây hoặc trigger sự kiện
const handleReanalyze = () => {
  // Call reanalyze api
  alert("Tính năng phân tích lại đang được cập nhật!")
}

</script>

<template>
  <CTSplashScreen v-if="authState === 'loading'" />
  <CTAccessDenied v-else-if="authState === 'denied'" />
  
  <div v-else-if="authState === 'authorized'" class="flex h-screen w-full bg-background overflow-hidden text-foreground">
    
    <AppSidebar />

    <!-- MAIN CONTENT -->
    <div class="flex-1 flex flex-col h-full overflow-hidden relative">
      <AppHeader />

      <!-- Scrollable content area -->
      <main class="flex-1 overflow-y-auto px-8 py-6 relative">
        <div class="absolute inset-0 pointer-events-none overflow-hidden -z-10">
          <div class="absolute top-[-20%] left-[-10%] w-[50%] h-[50%] bg-primary/5 rounded-full blur-3xl"></div>
          <div class="absolute bottom-[-20%] right-[-10%] w-[60%] h-[60%] bg-secondary/5 rounded-full blur-3xl"></div>
        </div>

        <template v-if="activeTab === 'transcribe'">
          <VoiceTranscribe />
        </template>
        
        <template v-else-if="activeTab === 'enroll'">
          <VoiceEnroll />
        </template>
        
        <template v-else-if="activeTab === 'view_meeting'">
          <MeetingHistory :meeting="currentMeeting" :t="t" />
        </template>
        
      </main>
    </div>

    <!-- Modals -->
    <TaskModal 
      :isOpen="isTaskModalOpen"
      :tasks="tasks"
      :dbEmployees="dbEmployees"
      :hrProjectsMap="hrProjectsMap"
      :docxUrl="docxUrl"
      :excelUrl="excelUrl"
      :currentLocalDate="currentLocalDate"
      :t="t"
      :selectedAttendees="selectedAttendees"
      :voiceDbSpeakers="voiceDbSpeakers"
      :isReanalyzing="isReanalyzing"
      @close="handleTaskModalClose"
      @remove-task="handleRemoveTask"
      @add-task="handleAddTask"
      @sync-erp="handleSyncERP"
      @toggle-attendee="handleToggleAttendee"
      @remove-attendee="handleRemoveAttendee"
      @reanalyze="handleReanalyze"
    />

  </div>
</template>

<style>
/* CSS styles có thể được di chuyển ra file style.css sau */
@import './style.css';
</style>
