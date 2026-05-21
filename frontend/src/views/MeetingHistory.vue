<script setup>
import { defineProps } from 'vue'

const props = defineProps({
  meeting: Object,
  t: Function
})

const getSegments = (rawResults) => {
  if (!rawResults) return [];
  try {
    return JSON.parse(rawResults);
  } catch(e) {
    return [];
  }
}

const downloadFile = (url, defaultName) => {
  if (!url) return;
  const link = document.createElement('a');
  link.href = url;
  link.download = defaultName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}
</script>

<template>
  <div v-if="meeting" class="w-full flex flex-col gap-8 pb-10 mt-2 fade-in">
    <!-- Meeting Info Card -->
    <div class="shadcn-card glow-effect">
      <div class="card-header border-b border-border bg-muted/10">
        <h3 class="card-title text-xl">{{ meeting.title }}</h3>
        <p class="card-description">Ngày: {{ meeting.date }} &middot; Trạng thái: {{ meeting.status }}</p>
      </div>
      
      <div class="card-content flex items-center gap-4 mt-4">
          <button v-if="meeting.audio_file" @click="downloadFile(meeting.audio_file, meeting.title + '.wav')" class="shadcn-btn shadcn-btn-outline h-10">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M9 18V5l12-2v13"></path><circle cx="6" cy="18" r="3"></circle><circle cx="18" cy="16" r="3"></circle></svg>
             Tải Âm thanh
          </button>
          
          <button v-if="meeting.minute_docx" @click="downloadFile(meeting.minute_docx, meeting.title + '.docx')" class="shadcn-btn shadcn-btn-outline h-10">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
             Biên bản Word
          </button>
          
          <button v-if="meeting.task_xlsx" @click="downloadFile(meeting.task_xlsx, meeting.title + '.xlsx')" class="shadcn-btn shadcn-btn-outline h-10">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
             Danh sách Task
          </button>
      </div>
    </div>
    
    <!-- TRANSCRIPT -->
    <div v-if="meeting.raw_results" class="shadcn-card">
      <div class="card-header border-b border-border bg-muted/10">
        <h3 class="card-title">Nội dung hội thoại</h3>
        <p class="card-description">Đã phân tích và phân rã người nói</p>
      </div>
      <div class="card-content p-0">
         <div class="log-view p-6 space-y-6 max-h-[500px] overflow-auto">
            <div v-for="(seg, idx) in getSegments(meeting.raw_results)" :key="idx" class="log-entry">
               <div class="log-meta">
                  <span class="log-speaker">{{ seg[2] }}</span>
                  <span class="log-time">[{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s]</span>
               </div>
               <p class="log-text">{{ seg[3] }}</p>
            </div>
         </div>
      </div>
    </div>
    <div v-else-if="meeting.transcript" class="shadcn-card">
       <div class="card-header border-b border-border bg-muted/10">
         <h3 class="card-title">Nội dung văn bản gốc</h3>
       </div>
       <div class="card-content p-6">
          <pre class="whitespace-pre-wrap font-sans text-sm">{{ meeting.transcript }}</pre>
       </div>
    </div>
  </div>
  <div v-else class="flex h-full items-center justify-center text-muted-foreground">
     Vui lòng chọn một cuộc họp từ Sidebar để xem chi tiết.
  </div>
</template>
