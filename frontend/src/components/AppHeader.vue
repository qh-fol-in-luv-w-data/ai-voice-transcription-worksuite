<script setup>
import { isDark, toggleDark, uiLang, toggleLang, dict } from '../composables/useVoiceApp'
</script>

<template>
  <header class="h-16 border-b border-border bg-background/90 backdrop-blur-md flex items-center justify-between px-8 sticky top-0 z-10 shrink-0">
    <div>
      <h1 class="text-xl font-bold tracking-tight text-foreground">
        2AS Voice Suite
      </h1>
      <p class="text-xs text-muted-foreground font-medium uppercase tracking-wider mt-0.5">{{ dict[uiLang].title }}</p>
    </div>
    <div class="flex items-center gap-4">
      <button @click="toggleLang" class="shadcn-btn shadcn-btn-ghost w-10 h-10 p-0 rounded-full font-bold hover:bg-muted transition-colors">
        {{ uiLang === 'vi' ? 'VN' : 'EN' }}
      </button>
      <button @click="toggleDark" class="shadcn-btn shadcn-btn-ghost w-10 h-10 p-0 rounded-full hover:bg-muted transition-colors">
        <svg v-if="isDark" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></svg>
        <svg v-else xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></svg>
      </button>
    </div>
  </header>
</template>
