<script setup>
import { useSession } from '../utils/session'
import { activeTab, meetingHistory, loadPastMeeting } from '../composables/useVoiceApp'

const { currentUser, currentFullName } = useSession()

const setTab = (tab) => {
  activeTab.value = tab
}
</script>

<template>
  <aside class="w-72 border-r border-border bg-sidebar shrink-0 flex flex-col transition-all duration-300">
    <div class="h-16 flex items-center px-6 border-b border-border bg-sidebar-accent/30">
      <div class="flex items-center gap-3 w-full">
        <div class="w-8 h-8 rounded bg-primary/20 flex items-center justify-center text-primary font-bold shadow-sm">
          A
        </div>
        <span class="font-bold text-lg tracking-tight text-sidebar-foreground truncate">Agent Hub</span>
      </div>
    </div>
    
    <nav class="flex-1 overflow-y-auto p-4 space-y-6 sidebar-scroll">
      <div>
        <h3 class="mb-2 px-2 text-xs font-semibold text-sidebar-foreground/50 uppercase tracking-wider">Menu Chính</h3>
        <ul class="space-y-1">
          <li>
            <button
              @click="setTab('transcribe')"
              :class="['w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200',
                       activeTab === 'transcribe' ? 'bg-primary/10 text-primary shadow-sm' : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground']"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="activeTab === 'transcribe' ? 'text-primary' : 'text-sidebar-foreground/50'"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>
              Phân tích Hội thoại
            </button>
          </li>
          <li>
            <button
              @click="setTab('enroll')"
              :class="['w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200',
                       activeTab === 'enroll' ? 'bg-primary/10 text-primary shadow-sm' : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground']"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="activeTab === 'enroll' ? 'text-primary' : 'text-sidebar-foreground/50'"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              Đăng ký Giọng nói
            </button>
          </li>
        </ul>
      </div>

      <div>
        <h3 class="mb-2 px-2 text-xs font-semibold text-sidebar-foreground/50 uppercase tracking-wider">Lịch sử Cuộc họp</h3>
        <ul v-if="meetingHistory.length > 0" class="space-y-1">
          <li v-for="meeting in meetingHistory" :key="meeting.name">
            <button
              @click="loadPastMeeting(meeting)"
              :class="['w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors truncate',
                       activeTab === 'view_meeting' && currentMeeting?.name === meeting.name ? 'bg-sidebar-accent text-sidebar-foreground font-semibold' : 'text-sidebar-foreground/60 hover:bg-sidebar-accent hover:text-sidebar-foreground']"
            >
              {{ meeting.title }}
            </button>
          </li>
        </ul>
        <div v-else class="px-3 py-2 text-sm text-sidebar-foreground/40 italic">
          Chưa có lịch sử
        </div>
      </div>
    </nav>
    
    <!-- User Profile Footer -->
    <div class="p-4 border-t border-border bg-sidebar-accent/10">
      <div class="flex items-center gap-3 p-2 rounded-lg hover:bg-sidebar-accent transition-colors cursor-pointer">
        <div class="w-9 h-9 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold shadow-inner">
          {{ currentFullName?.charAt(0) || 'U' }}
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-sidebar-foreground truncate">{{ currentFullName }}</p>
          <p class="text-xs text-sidebar-foreground/50 truncate">{{ currentUser }}</p>
        </div>
      </div>
    </div>
  </aside>
</template>
