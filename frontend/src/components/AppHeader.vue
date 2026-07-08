<script setup>
import { isDark, toggleDark, uiLang, toggleLang, dict } from '../composables/useVoiceApp'
import { useSession } from '../utils/session'

const { currentUser, currentFullName } = useSession()
</script>

<template>
<header class="bg-transparent flex justify-end items-center h-20 px-8 w-full shrink-0 z-10 sticky top-0">
<div class="flex items-center gap-6">
<!-- Notifications -->
<div class="flex items-center gap-1 mr-4">
    <button @click="toggleDark" class="text-on-surface-variant hover:text-white hover:bg-white/5 p-2 rounded-full transition-colors group" title="Toggle Theme">
    <span class="material-symbols-outlined text-[20px] group-hover:scale-110 transition-transform font-light">dark_mode</span>
    </button>
    <button @click="toggleLang" class="text-on-surface-variant hover:text-white hover:bg-white/5 p-2 rounded-full transition-colors group" title="Translate">
    <span class="material-symbols-outlined text-[20px] group-hover:scale-110 transition-transform font-light">translate</span>
    </button>
</div>

<button class="relative text-on-surface-variant hover:text-white p-2 rounded-full transition-colors group">
<span class="material-symbols-outlined text-[24px] group-hover:scale-110 transition-transform font-light">notifications</span>
<div class="absolute top-2 right-2 w-2 h-2 bg-error rounded-full border border-background"></div>
</button>

<div class="h-6 w-px bg-outline-variant/30"></div>

<!-- User Profile -->
<div class="flex items-center gap-3 cursor-pointer group">
<span class="font-body-md text-[14px] text-white hidden sm:block font-medium group-hover:text-primary transition-colors">{{ currentFullName || currentUser || 'User' }}</span>
<div class="w-10 h-10 rounded-full bg-surface-container overflow-hidden border border-white/10 group-hover:border-primary/50 transition-colors flex items-center justify-center">
    <img v-if="false" src="" alt="Avatar" class="w-full h-full object-cover">
    <div v-else class="w-full h-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white font-bold text-sm uppercase">
        {{ currentFullName ? currentFullName.charAt(0) : (currentUser ? currentUser.charAt(0) : 'U') }}
    </div>
</div>
</div>
</div>
</header>
</template>
