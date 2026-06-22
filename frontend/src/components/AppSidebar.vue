<script setup>
import { useSession } from '../utils/session'
import { activeTab, meetingHistory, loadPastMeeting, t, currentMeeting } from '../composables/useVoiceApp'

const { currentUser, currentFullName } = useSession()

const setTab = (tab) => {
  activeTab.value = tab
}
</script>

<template>
  <aside class="w-72 border-r border-border bg-background shrink-0 flex flex-col transition-all duration-300">
    <div class="h-16 flex items-center px-6 border-b border-border">
      <div class="flex items-center gap-3 w-full">
        <div class="w-8 h-8 rounded bg-foreground flex items-center justify-center text-background font-bold shadow-sm">
          A
        </div>
        <span class="font-bold text-lg tracking-tight text-foreground truncate">Agent Hub</span>
      </div>
    </div>
    
    <nav class="flex-1 overflow-y-auto p-4 space-y-6 sidebar-scroll">
      <div>
        <h3 class="mb-2 px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">{{ t('menu_main') === 'menu_main' ? 'Menu' : t('menu_main') }}</h3>
        <ul class="space-y-1">
          <li>
            <button
              @click="setTab('transcribe')"
              :class="['w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200',
                       activeTab === 'transcribe' ? 'bg-muted text-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground']"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="activeTab === 'transcribe' ? 'text-foreground' : 'text-muted-foreground'"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>
              {{ t('tab_transcribe') }}
            </button>
          </li>
          <li>
            <button
              @click="setTab('enroll')"
              :class="['w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200',
                       activeTab === 'enroll' ? 'bg-muted text-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground']"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="activeTab === 'enroll' ? 'text-foreground' : 'text-muted-foreground'"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg>
              {{ t('tab_enroll') }}
            </button>
          </li>
          <li>
            <button
              @click="setTab('voice_task')"
              :class="['w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm font-medium transition-all duration-200',
                       activeTab === 'voice_task' ? 'bg-muted text-foreground shadow-sm' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground']"
            >
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" :class="activeTab === 'voice_task' ? 'text-foreground' : 'text-muted-foreground'"><path d="M12 2c-1.7 0-3 1.2-3 2.6v6.8c0 1.4 1.3 2.6 3 2.6s3-1.2 3-2.6V4.6C15 3.2 13.7 2 12 2z"/><path d="M19 10v1a7 7 0 0 1-14 0v-1"/><path d="m9 17 3 3 5-5"/></svg>
              {{ t('tab_voice_task') || 'Tạo Task qua Voice' }}
            </button>
          </li>
        </ul>
      </div>

      <div>
        <h3 class="mb-2 px-2 text-xs font-semibold text-muted-foreground uppercase tracking-wider">{{ t('meeting_history') === 'meeting_history' ? 'History' : t('meeting_history') }}</h3>
        <ul v-if="meetingHistory.length > 0" class="space-y-1">
          <li v-for="meeting in meetingHistory" :key="meeting.name">
            <button
              @click="loadPastMeeting(meeting)"
              :class="['w-full text-left px-3 py-2 rounded-md text-sm font-medium transition-colors truncate',
                       activeTab === 'view_meeting' && currentMeeting?.name === meeting.name ? 'bg-muted text-foreground font-semibold' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground']"
            >
              {{ meeting.title }}
            </button>
          </li>
        </ul>
        <div v-else class="px-3 py-2 text-sm text-muted-foreground/60 italic">
          {{ t('no_history') === 'no_history' ? 'No history' : t('no_history') }}
        </div>
      </div>
    </nav>
    
    <!-- User Profile Footer -->
    <div class="p-4 border-t border-border bg-muted/20">
      <div class="flex items-center gap-3 p-2 rounded-lg hover:bg-muted/50 transition-colors cursor-pointer">
        <div class="w-9 h-9 rounded-full bg-foreground flex items-center justify-center text-background font-bold shadow-inner">
          {{ currentFullName?.charAt(0) || 'U' }}
        </div>
        <div class="flex-1 min-w-0">
          <p class="text-sm font-medium text-foreground truncate">{{ currentFullName }}</p>
          <p class="text-xs text-muted-foreground truncate">{{ currentUser }}</p>
        </div>
      </div>
    </div>
  </aside>
</template>
