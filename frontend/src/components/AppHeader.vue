<script setup>
import { isDark, toggleDark, uiLang, toggleLang, dict } from '../composables/useVoiceApp'
import { useSession } from '../utils/session'

const { currentUser, currentFullName } = useSession()
</script>

<template>
<header class="bg-transparent flex justify-end items-center h-20 px-8 w-full shrink-0 z-10 sticky top-0">
<div class="flex items-center gap-6">
<div class="flex items-center gap-1 mr-4">
    <button v-show="false" @click="toggleDark" class="text-gray-500 dark:text-on-surface-variant hover:text-gray-900 dark:hover:text-on-surface hover:bg-gray-100 dark:hover:bg-surface-variant/30 p-2 rounded-full transition-colors group" title="Toggle Theme">
    <span class="material-symbols-outlined text-[20px] group-hover:scale-110 transition-transform font-light">{{ isDark ? 'dark_mode' : 'light_mode' }}</span>
    </button>
    <button v-show="false" @click="toggleLang" class="text-gray-500 dark:text-on-surface-variant hover:text-gray-900 dark:hover:text-on-surface hover:bg-gray-100 dark:hover:bg-surface-variant/30 p-2 rounded-full transition-colors group" title="Translate">
    <span class="material-symbols-outlined text-[20px] group-hover:scale-110 transition-transform font-light">translate</span>
    </button>
</div>

<button class="relative text-gray-500 dark:text-on-surface-variant hover:text-gray-900 dark:hover:text-on-surface p-2 rounded-full transition-colors group">
<span class="material-symbols-outlined text-[24px] group-hover:scale-110 transition-transform font-light">notifications</span>
<div class="absolute top-2 right-2 w-2 h-2 bg-error rounded-full border border-white dark:border-background"></div>
</button>

<div class="h-6 w-px bg-gray-200 dark:bg-outline-variant/30"></div>

<!-- User Profile -->
<div class="flex items-center gap-3 cursor-pointer group">
<span class="font-body-md text-[14px] text-gray-900 dark:text-on-surface hidden sm:block font-medium group-hover:text-primary transition-colors">{{ currentFullName || currentUser || 'User' }}</span>
<div class="w-10 h-10 rounded-full bg-gray-100 dark:bg-surface-container overflow-hidden border border-gray-200 dark:border-outline-variant/50 group-hover:border-primary/50 transition-colors flex items-center justify-center">
    <img v-if="false" src="" alt="Avatar" class="w-full h-full object-cover">
    <div v-else class="w-full h-full bg-gradient-to-br from-primary to-secondary flex items-center justify-center text-white font-bold text-sm uppercase">
        {{ currentFullName ? currentFullName.charAt(0) : (currentUser ? currentUser.charAt(0) : 'U') }}
    </div>
</div>
</div>
</div>
</header>
</template>
