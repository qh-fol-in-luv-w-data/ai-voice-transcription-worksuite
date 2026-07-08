<script setup>
import { useSession } from '../utils/session'
import { activeTab, meetingHistory, loadPastMeeting, t, currentMeeting } from '../composables/useVoiceApp'

const { currentUser, currentFullName } = useSession()

const setTab = (tab) => {
  activeTab.value = tab
}
</script>

<template>
<aside class="bg-surface-container-low dark:bg-surface-container-low flex flex-col py-lg docked fixed left-0 h-full w-[280px] border-r border-outline-variant z-20 hidden md:flex">
<!-- Header -->
<div class="px-lg mb-xl flex items-center gap-md">
<div class="w-10 h-10 rounded-lg bg-surface-container-high flex items-center justify-center shrink-0 border border-outline-variant">
<span class="material-symbols-outlined text-primary">graphic_eq</span>
</div>
<div>
<h1 class="font-headline-md text-headline-md text-primary truncate leading-tight" title="AUDIO INTELLIGENCE">AUDIO INTELLIGENCE</h1>
<p class="font-label-caps text-label-caps text-on-surface-variant uppercase mt-1">Worksuite</p>
</div>
</div>
<!-- Navigation Links -->
<nav class="flex-1 px-md flex flex-col gap-sm overflow-y-auto">
<!-- Active Tab -->
<a @click.prevent="setTab('transcribe')" :class="['flex items-center gap-md px-md py-sm rounded-md font-medium hover:bg-surface-variant/50 transition-all group cursor-pointer', activeTab === 'transcribe' ? 'text-primary font-bold bg-surface-variant/30 border-r-2 border-primary' : 'text-on-surface-variant']">
<span class="material-symbols-outlined group-hover:scale-110 transition-transform">mic</span>
<span class="font-body-md text-body-md truncate">Phân tích Hội thoại</span>
</a>
<a @click.prevent="setTab('voice_task')" :class="['flex items-center gap-md px-md py-sm rounded-md font-medium hover:bg-surface-variant/50 transition-all group cursor-pointer', activeTab === 'voice_task' ? 'text-primary font-bold bg-surface-variant/30 border-r-2 border-primary' : 'text-on-surface-variant']">
<span class="material-symbols-outlined group-hover:scale-110 transition-transform">keyboard_voice</span>
<span class="font-body-md text-body-md truncate">Tự tạo Task qua Voice</span>
</a>
<a @click.prevent="setTab('enroll')" :class="['flex items-center gap-md px-md py-sm rounded-md font-medium hover:bg-surface-variant/50 transition-all group cursor-pointer', activeTab === 'enroll' ? 'text-primary font-bold bg-surface-variant/30 border-r-2 border-primary' : 'text-on-surface-variant']">
<span class="material-symbols-outlined group-hover:scale-110 transition-transform">person_add</span>
<span class="font-body-md text-body-md truncate">Đăng ký Giọng nói</span>
</a>

<div class="px-md mt-4 mb-2">
  <span class="font-label-caps text-label-caps text-on-surface-variant uppercase tracking-wider">Lịch sử Cuộc họp</span>
</div>

<a v-for="meeting in meetingHistory" :key="meeting.name" @click.prevent="loadPastMeeting(meeting)" :class="['flex items-center gap-md px-md py-sm rounded-md font-medium hover:bg-surface-variant/50 transition-all group cursor-pointer', activeTab === 'view_meeting' && currentMeeting?.name === meeting.name ? 'text-primary font-bold bg-surface-variant/30 border-r-2 border-primary' : 'text-on-surface-variant']">
<span class="material-symbols-outlined group-hover:scale-110 transition-transform">history</span>
<span class="font-body-md text-body-md truncate">{{ meeting.title }}</span>
</a>

<div v-if="meetingHistory.length === 0" class="px-md py-2 text-sm text-on-surface-variant opacity-60 italic">
  Chưa có lịch sử
</div>
</nav>
<!-- Footer Links -->
<div class="px-md mt-auto pt-lg border-t border-outline-variant flex flex-col gap-sm">
<a class="flex items-center gap-md px-md py-sm rounded-md text-on-surface-variant font-medium hover:bg-surface-variant/50 transition-all cursor-pointer">
<span class="material-symbols-outlined">settings</span>
<span class="font-body-md text-body-md truncate">Settings</span>
</a>
<a class="flex items-center gap-md px-md py-sm rounded-md text-on-surface-variant font-medium hover:bg-surface-variant/50 transition-all cursor-pointer">
<span class="material-symbols-outlined">help</span>
<span class="font-body-md text-body-md truncate">Help</span>
</a>
</div>
</aside>
</template>
