<script setup>
import { onMounted, watch } from 'vue'
import { initSession, useSession } from './utils/session'
import { getEmployees, getEnrolledSpeakers } from './api'
import CTSplashScreen from './components/CTSplashScreen.vue'
import CTAccessDenied from './components/CTAccessDenied.vue'
import AppSidebar from './components/AppSidebar.vue'
import AppHeader from './components/AppHeader.vue'

// Import all views
import VoiceTranscribe from './views/VoiceTranscribe.vue'
import VoiceEnroll from './views/VoiceEnroll.vue'
import VoiceTask from './views/VoiceTask.vue'
import MeetingHistory from './views/MeetingHistory.vue'
import TaskModal from './components/TaskModal.vue'

import { 
  dbEmployees, voiceDbSpeakers, loadHistory,
  activeTab, uiLang, isDark, currentMeeting, dict,
  isTaskModalOpen, tasks, hrProjectsMap,
  docxUrl, excelUrl, selectedAttendees, isReanalyzing 
} from './composables/useVoiceApp'
import { getElevenLabsInfo, syncTasksToERP } from './api'
import { ElMessage } from 'element-plus'

const handleSyncERP = async () => {
  if (tasks.value.length === 0) {
    ElMessage.warning("Không có nhiệm vụ nào để đồng bộ!")
    return
  }
  try {
    const res = await syncTasksToERP(tasks.value)
    if (res.status === 'success') {
      ElMessage.success(`✅ Đã đồng bộ thành công!`)
      isTaskModalOpen.value = false
    } else {
      ElMessage.error("❌ Lỗi đồng bộ: " + res.message)
    }
  } catch(e) {
    ElMessage.error("❌ Lỗi kết nối khi đồng bộ")
  }
}

const t = (key) => {
  if (dict[uiLang.value] && dict[uiLang.value][key]) {
    return dict[uiLang.value][key]
  }
  return key
}

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
  <div v-else class="h-screen w-full flex overflow-hidden bg-background text-on-background">
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
        <MeetingHistory v-if="activeTab === 'view_meeting'" :meeting="currentMeeting" :t="t" />
      </main>
      
      <!-- Global Task Modal -->
      <TaskModal 
        :is-open="isTaskModalOpen"
        :tasks="tasks"
        :db-employees="dbEmployees"
        :hr-projects-map="hrProjectsMap"
        :docx-url="docxUrl"
        :excel-url="excelUrl"
        :current-local-date="() => new Date().toLocaleString('vi-VN', { hour12: false })"
        :t="t"
        :selected-attendees="selectedAttendees"
        :voice-db-speakers="voiceDbSpeakers"
        :is-reanalyzing="isReanalyzing"
        @close="isTaskModalOpen = false"
        @remove-task="(idx) => tasks.splice(idx, 1)"
        @add-task="tasks.push({ title: '', assignee_display: '', project: '', start_date: new Date().toLocaleString('vi-VN', { hour12: false }), end_date: '', description: '' })"
        @sync-erp="handleSyncERP"
        @toggle-attendee="(val) => { const i = selectedAttendees.indexOf(val); if(i > -1) selectedAttendees.splice(i,1); else selectedAttendees.push(val); }"
        @remove-attendee="(name) => { const i = selectedAttendees.indexOf(name); if(i > -1) selectedAttendees.splice(i,1); }"
      />
    </div>
  </div>
</template>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');


body {
  overflow-x: hidden;
  max-width: 100vw;
}

/* Global Dark Theme Overrides for Element Plus Poppers */
.dark .el-popper.is-light {
  background-color: #111827 !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5) !important;
}

.dark .el-popper.is-light .el-popper__arrow::before {
  background-color: #111827 !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

.dark .el-select-dropdown__item {
  color: rgba(255, 255, 255, 0.8) !important;
}

.dark .el-select-dropdown__item.hover, 
.dark .el-select-dropdown__item:hover {
  background-color: rgba(255, 255, 255, 0.05) !important;
}

.dark .el-select-dropdown__item.is-selected {
  color: #a8c7fa !important;
  background-color: rgba(168, 199, 250, 0.1) !important;
}

.dark .el-picker-panel {
  background-color: #111827 !important;
  border-color: rgba(255, 255, 255, 0.1) !important;
  color: #fff !important;
}

.dark .el-picker-panel__icon-btn,
.dark .el-date-picker__header-label,
.dark .el-date-table th,
.dark .el-date-table td {
  color: rgba(255, 255, 255, 0.8) !important;
}

.dark .el-date-table td.available:hover {
  color: #a8c7fa !important;
}
.dark .el-date-table td.current:not(.disabled) .el-date-table-cell__text {
  background-color: #a8c7fa !important;
  color: #000 !important;
}

/* Override Tailwind Forms plugin's hardcoded white background */
[type='text'], [type='email'], [type='url'], [type='password'], [type='number'], [type='date'], [type='datetime-local'], [type='month'], [type='search'], [type='tel'], [type='time'], [type='week'], [multiple], textarea, select {
  background-color: transparent !important;
}
</style>
