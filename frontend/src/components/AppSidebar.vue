<script setup>
import { useSession } from '../utils/session'
import { activeTab, meetingHistory, loadPastMeeting, t, currentMeeting } from '../composables/useVoiceApp'

const { currentUser, currentFullName } = useSession()

const setTab = (tab) => {
  activeTab.value = tab
}
</script>

<template>
<aside class="bg-[#0a0f1c]/95 backdrop-blur-xl flex flex-col py-6 docked fixed left-0 h-full w-[280px] border-r border-white/5 z-20 hidden md:flex shadow-2xl">
<!-- Header Logo -->
<div class="px-6 mb-10 flex items-center gap-3">
<div class="w-10 h-10 rounded-xl bg-gradient-to-br from-secondary to-primary flex items-center justify-center shrink-0 shadow-[0_0_15px_rgba(192,193,255,0.3)]">
<span class="font-bold text-white text-[15px] tracking-tight">2AS</span>
</div>
<div>
<h1 class="text-[17px] font-bold text-white tracking-wide">2AS Worksuite</h1>
</div>
</div>
<!-- Navigation Links -->
<nav class="flex-1 px-4 flex flex-col gap-2 overflow-y-auto custom-scrollbar">
<!-- Active Tab -->
<a @click.prevent="setTab('transcribe')" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'transcribe' ? 'text-white font-bold bg-white/10 shadow-sm border border-white/5' : 'text-on-surface-variant hover:text-white hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">chat_bubble</span>
<span class="font-body-md text-[14.5px] truncate">Phân tích Hội thoại</span>
</a>
<a @click.prevent="setTab('voice_task')" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'voice_task' ? 'text-white font-bold bg-white/10 shadow-sm border border-white/5' : 'text-on-surface-variant hover:text-white hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">edit_square</span>
<span class="font-body-md text-[14.5px] truncate">Tự tạo Task qua Voice</span>
</a>
<a @click.prevent="setTab('enroll')" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'enroll' ? 'text-white font-bold bg-white/10 shadow-sm border border-white/5' : 'text-on-surface-variant hover:text-white hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">mic</span>
<span class="font-body-md text-[14.5px] truncate">Đăng ký Giọng nói</span>
</a>

<div class="px-4 mt-6 mb-2">
  <span class="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">Lịch sử Cuộc họp</span>
</div>

<a v-for="meeting in meetingHistory" :key="meeting.name" @click.prevent="loadPastMeeting(meeting)" :class="['flex items-center gap-4 px-4 py-3.5 rounded-xl font-medium transition-all group cursor-pointer', activeTab === 'view_meeting' && currentMeeting?.name === meeting.name ? 'text-white font-bold bg-white/10 shadow-sm border border-white/5' : 'text-on-surface-variant hover:text-white hover:bg-white/5']">
<span class="material-symbols-outlined text-[22px] group-hover:scale-110 transition-transform font-light">history</span>
<span class="font-body-md text-[14.5px] truncate">{{ meeting.title }}</span>
</a>

<div v-if="meetingHistory.length === 0" class="px-4 py-2 text-[13px] text-on-surface-variant/50 italic">
  Chưa có lịch sử
</div>
</nav>
</aside>
</template>
