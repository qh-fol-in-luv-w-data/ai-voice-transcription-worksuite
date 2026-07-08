<script setup>
import { isDark, toggleDark, uiLang, toggleLang, dict } from '../composables/useVoiceApp'
import { useSession } from '../utils/session'

const { currentUser, currentFullName } = useSession()
</script>

<template>
<header class="bg-background/90 dark:bg-background/90 backdrop-blur-md flex justify-between items-center h-16 px-gutter w-full border-b border-outline-variant shrink-0 z-10 sticky top-0">
<div class="flex items-center gap-md">
<button class="md:hidden text-on-surface-variant p-sm hover:bg-surface-variant rounded-full transition-colors">
<span class="material-symbols-outlined">menu</span>
</button>
<div class="font-headline-md text-headline-md font-bold text-on-surface hidden md:block">
                    2AS Worksuite
                </div>
</div>
<div class="flex items-center gap-lg">
<div class="flex items-center gap-sm">
<button @click="toggleDark" class="text-on-surface-variant p-sm hover:bg-surface-variant rounded-full transition-colors" title="Toggle Theme">
<span class="material-symbols-outlined">dark_mode</span>
</button>
<button @click="toggleLang" class="text-on-surface-variant p-sm hover:bg-surface-variant rounded-full transition-colors" title="Translate">
<span class="material-symbols-outlined">translate</span>
</button>
</div>
<div class="h-8 w-px bg-outline-variant mx-xs"></div>
<div class="flex items-center gap-sm cursor-pointer hover:opacity-80 transition-opacity">
<div class="w-8 h-8 rounded-full bg-primary-container flex items-center justify-center text-on-primary-container font-bold text-sm shrink-0 uppercase">
                        {{ currentFullName ? currentFullName.charAt(0) : (currentUser ? currentUser.charAt(0) : 'U') }}
                    </div>
<span class="font-body-md text-body-md text-on-surface hidden sm:block">{{ currentFullName || currentUser || 'User' }}</span>
</div>
</div>
</header>
</template>
