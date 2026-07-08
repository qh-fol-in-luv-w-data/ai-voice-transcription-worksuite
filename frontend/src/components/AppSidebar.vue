<script setup>
import { ref } from 'vue'
import { useSession } from '../utils/session'
import { activeTab, meetingHistory, loadPastMeeting, t, currentMeeting, loadHistory } from '../composables/useVoiceApp'
import { renameMeeting } from '../api'

const { currentUser, currentFullName } = useSession()

const setTab = (tab) => {
  activeTab.value = tab
}

const isHistoryModalOpen = ref(false)
const editingMeeting = ref(null)
const editTitleInput = ref('')

const startEdit = (meeting) => {
  editingMeeting.value = meeting.name
  editTitleInput.value = meeting.title
}

const saveEdit = async (meeting) => {
  if (!editTitleInput.value.trim()) return
  try {
    await renameMeeting(meeting.name, editTitleInput.value)
    // Update local state immediately
    meeting.title = editTitleInput.value
    if (currentMeeting.value?.name === meeting.name) {
      currentMeeting.value.title = editTitleInput.value
    }
  } catch (e) {
    alert("Không thể đổi tên cuộc họp: " + e.message)
  }
  editingMeeting.value = null
}

const cancelEdit = () => {
  editingMeeting.value = null
}

const selectMeetingFromModal = (meeting) => {
  loadPastMeeting(meeting)
  isHistoryModalOpen.value = false
}
</script>

<template>
<aside class="bg-white dark:bg-[#0a0f1c]/95 backdrop-blur-xl flex flex-col py-6 docked fixed left-0 h-full w-[280px] border-r border-outline-variant/30 dark:border-white/5 z-20 hidden md:flex shadow-2xl">
<!-- Header Logo -->
<div class="px-6 mb-10 flex items-center gap-3">
<div class="w-10 h-10 rounded-xl bg-gradient-to-br from-secondary to-primary flex items-center justify-center shrink-0 shadow-[0_0_15px_rgba(192,193,255,0.3)]">
<span class="font-bold text-white text-[15px] tracking-tight">2AS</span>
</div>
<div>
<h1 class="text-[17px] font-bold text-on-surface dark:text-white tracking-wide">2AS Worksuite</h1>
</div>
</div>
<!-- Navigation Links -->
<nav class="flex-1 px-4 flex flex-col gap-2 overflow-y-auto custom-scrollbar">
<!-- Active Tab -->
<a @click.prevent="setTab('transcribe')" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'transcribe' ? 'text-primary dark:text-white font-bold bg-primary/10 dark:bg-white/10 shadow-sm border border-primary/20 dark:border-white/5' : 'text-on-surface-variant hover:text-on-surface dark:hover:text-white hover:bg-surface-variant/30 dark:hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">chat_bubble</span>
<span class="font-body-md text-[14.5px] truncate">Phân tích Hội thoại</span>
</a>
<a @click.prevent="setTab('voice_task')" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'voice_task' ? 'text-primary dark:text-white font-bold bg-primary/10 dark:bg-white/10 shadow-sm border border-primary/20 dark:border-white/5' : 'text-on-surface-variant hover:text-on-surface dark:hover:text-white hover:bg-surface-variant/30 dark:hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">edit_square</span>
<span class="font-body-md text-[14.5px] truncate">Tự tạo Task qua Voice</span>
</a>
<a @click.prevent="setTab('enroll')" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'enroll' ? 'text-primary dark:text-white font-bold bg-primary/10 dark:bg-white/10 shadow-sm border border-primary/20 dark:border-white/5' : 'text-on-surface-variant hover:text-on-surface dark:hover:text-white hover:bg-surface-variant/30 dark:hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">mic</span>
<span class="font-body-md text-[14.5px] truncate">Đăng ký Giọng nói</span>
</a>

<div class="px-4 mt-6 mb-2">
  <span class="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">Lịch sử Cuộc họp</span>
</div>

<a @click.prevent="isHistoryModalOpen = true" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', isHistoryModalOpen ? 'text-primary dark:text-white font-bold bg-primary/10 dark:bg-white/10 shadow-sm border border-primary/20 dark:border-white/5' : 'text-on-surface-variant hover:text-on-surface dark:hover:text-white hover:bg-surface-variant/30 dark:hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">format_list_bulleted</span>
<span class="font-body-md text-[14.5px] truncate">Quản lý Lịch sử Cuộc họp</span>
</a>
</nav>

<!-- History Modal -->
<Teleport to="body">
<div v-if="isHistoryModalOpen" class="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm">
  <div class="bg-white dark:bg-surface-container border border-outline-variant/30 rounded-3xl p-6 w-full max-w-2xl max-h-[80vh] flex flex-col shadow-2xl">
    <div class="flex justify-between items-center mb-6">
      <h2 class="text-xl font-bold text-on-surface dark:text-white tracking-wide">Lịch sử Cuộc họp</h2>
      <button @click="isHistoryModalOpen = false" class="w-8 h-8 rounded-full hover:bg-surface-variant/50 dark:hover:bg-white/10 flex items-center justify-center text-on-surface-variant hover:text-error transition-colors">
        <span class="material-symbols-outlined">close</span>
      </button>
    </div>
    
    <div class="flex-1 overflow-y-auto custom-scrollbar pr-2 space-y-2">
      <div v-if="meetingHistory.length === 0" class="text-center py-8 text-on-surface-variant/50 italic">
        Chưa có lịch sử cuộc họp nào.
      </div>
      
      <div v-for="meeting in meetingHistory" :key="meeting.name" class="flex items-center gap-3 p-3 rounded-xl hover:bg-surface-variant/30 dark:hover:bg-white/5 border border-transparent hover:border-outline-variant/30 dark:hover:border-white/5 transition-all group">
        <span class="material-symbols-outlined text-primary text-[20px] opacity-80">graphic_eq</span>
        
        <div class="flex-1 min-w-0">
          <template v-if="editingMeeting === meeting.name">
            <input v-model="editTitleInput" @keyup.enter="saveEdit(meeting)" @keyup.esc="cancelEdit" class="w-full bg-surface-container-highest border border-primary/50 rounded-lg px-3 py-1.5 text-sm text-on-surface dark:text-white focus:outline-none" autoFocus />
          </template>
          <template v-else>
            <div @click="selectMeetingFromModal(meeting)" class="font-medium text-[14.5px] text-on-surface dark:text-white truncate cursor-pointer hover:text-primary transition-colors">
              {{ meeting.title }}
            </div>
          </template>
        </div>
        
        <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <template v-if="editingMeeting === meeting.name">
            <button @click="saveEdit(meeting)" class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-primary/20 text-primary transition-colors" title="Lưu">
              <span class="material-symbols-outlined text-[18px]">check</span>
            </button>
            <button @click="cancelEdit" class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-error/20 text-error transition-colors" title="Hủy">
              <span class="material-symbols-outlined text-[18px]">close</span>
            </button>
          </template>
          <template v-else>
            <button @click="startEdit(meeting)" class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-surface-variant/50 dark:hover:bg-white/10 text-on-surface-variant hover:text-on-surface dark:hover:text-white transition-colors" title="Đổi tên">
              <span class="material-symbols-outlined text-[18px]">edit</span>
            </button>
            <button @click="selectMeetingFromModal(meeting)" class="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-primary/20 text-primary transition-colors" title="Mở">
              <span class="material-symbols-outlined text-[18px]">open_in_new</span>
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>
</div>
</Teleport>
</aside>
</template>
