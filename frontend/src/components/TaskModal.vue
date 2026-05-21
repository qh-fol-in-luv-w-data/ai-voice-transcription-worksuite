<script setup>
import { defineProps, defineEmits } from 'vue'

const props = defineProps({
  isOpen: Boolean,
  tasks: Array,
  dbEmployees: Array,
  hrProjectsMap: Object,
  docxUrl: String,
  excelUrl: String,
  currentLocalDate: Function,
  t: Function,
  selectedAttendees: Array,
  voiceDbSpeakers: Array,
  isReanalyzing: Boolean
})

const emit = defineEmits([
  'close', 'remove-task', 'add-task', 'sync-erp', 
  'toggle-attendee', 'remove-attendee', 'reanalyze'
])

const getProjectsForHR = (displayStr) => {
  if (!displayStr) return []
  const match = displayStr.match(/\((HR[-_]EMP[-_][^)]+)\)/i)
  let hrCode = ''
  if (match) hrCode = match[1]
  else if (displayStr.startsWith('HR_EMP_') || displayStr.startsWith('HR-EMP-')) hrCode = displayStr.trim()
  return props.hrProjectsMap[hrCode] || []
}

// Hàm tải file trực tiếp để tránh lỗi
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
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
    <div class="bg-background border border-border rounded-xl shadow-2xl w-[95%] max-w-7xl max-h-[90vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
      
      <!-- HEADER -->
      <div class="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/10 shrink-0">
        <h2 class="text-xl font-bold text-foreground">Kết quả trích xuất Task</h2>
        <button @click="emit('close')" class="btn-ghost-icon hover:bg-muted/30">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
        </button>
      </div>

      <!-- BODY -->
      <div class="flex-1 overflow-y-auto p-6 space-y-6">
        
        <!-- ATTENDEES -->
        <div class="shadcn-card border-primary/30">
            <div class="card-header border-b border-border bg-primary/5">
              <div class="flex justify-between items-center w-full">
                <div>
                  <h3 class="card-title flex items-center gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                    {{ t('attendees_title') }}
                  </h3>
                  <p class="card-description">{{ t('attendees_desc') }}</p>
                </div>
                <button
                  v-if="selectedAttendees.length > 0"
                  @click="emit('reanalyze')"
                  :disabled="isReanalyzing"
                  class="shadcn-btn shadcn-btn-primary"
                >
                  <svg v-if="!isReanalyzing" xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><polyline points="23 4 23 10 17 10"></polyline><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"></path></svg>
                  <svg v-else xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2 animate-spin"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg>
                  {{ isReanalyzing ? t('reanalyzing') : t('btn_reanalyze') }}
                </button>
              </div>
            </div>
            <div class="card-content p-4">
              <div class="flex flex-wrap items-center gap-2">
                <!-- Tags -->
                <span v-for="name in selectedAttendees" :key="name" class="attendee-chip attendee-chip--active">
                  <span class="attendee-avatar">{{ name.charAt(0).toUpperCase() }}</span>
                  <span>{{ name }}</span>
                  <button @click="emit('remove-attendee', name)" class="attendee-remove" title="Xóa">
                    <svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                  </button>
                </span>

                <!-- Dropdown -->
                <input
                  list="voice_db_speakers_list_modal"
                  @change="(e) => { 
                    const val = e.target.value.trim();
                    if(val) { 
                      const valid = voiceDbSpeakers.find(s => s.speaker_name === val);
                      if (valid) emit('toggle-attendee', val);
                      e.target.value = '';
                    }
                  }"
                  :disabled="voiceDbSpeakers.length === 0"
                  class="attendee-add-input cursor-text"
                  :placeholder="voiceDbSpeakers.length > 0 ? '+ Tìm & thêm người...' : 'Trống'"
                />
                <datalist id="voice_db_speakers_list_modal">
                  <option v-for="spk in voiceDbSpeakers" :key="spk.speaker_name" :value="spk.speaker_name">
                    {{ spk.email ? spk.email : '' }}
                  </option>
                </datalist>
              </div>
            </div>
        </div>

        <!-- TASK LIST -->
        <div class="shadcn-card">
             <div class="card-header border-b border-border flex justify-between items-center bg-muted/10">
                <div>
                  <h3 class="card-title">{{ t('task_list') }}</h3>
                  <p class="card-description">{{ t('task_desc') }}</p>
                </div>
                <div class="flex gap-2">
                  <button v-if="excelUrl" @click="downloadFile(excelUrl, 'Task ngày ' + currentLocalDate() + '.xlsx')" class="shadcn-btn shadcn-btn-ghost">
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                     {{ t('export_xlsx') }}
                  </button>
                  <button v-if="docxUrl" @click="downloadFile(docxUrl, 'Biên bản họp ngày ' + currentLocalDate() + '.docx')" class="shadcn-btn shadcn-btn-ghost">
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                     {{ t('export_docx') }}
                  </button>
                  <button @click="emit('add-task')" class="shadcn-btn shadcn-btn-outline">
                     <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                     {{ t('add_task') }}
                  </button>
                </div>
             </div>
             <div class="card-content p-0 bg-background overflow-x-auto">
                <table class="shadcn-table w-full text-sm min-w-max">
                   <thead class="bg-muted/20 border-b border-border">
                      <tr>
                         <th class="p-4 text-left font-medium text-muted-foreground w-12">#</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-64">{{ t('col_name') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-48">{{ t('col_assignee') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-48">{{ t('col_project') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-32">{{ t('col_start') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-32">{{ t('col_due') }}</th>
                         <th class="p-4 text-left font-medium text-muted-foreground w-72">{{ t('col_desc') }}</th>
                         <th class="p-4 text-center font-medium text-muted-foreground w-16">{{ t('col_del') }}</th>
                      </tr>
                   </thead>
                   <tbody>
                      <tr v-for="(task, idx) in tasks" :key="idx" class="border-b border-border hover:bg-muted/10 transition-colors">
                         <td class="p-4 font-mono text-xs text-muted-foreground">{{ idx + 1 }}</td>
                         <td class="p-3"><input v-model="task.title" class="shadcn-table-input" /></td>
                         <td class="p-3">
                           <input
                             v-model="task.assignee_display"
                             list="erp_employee_list_modal"
                             class="shadcn-table-input"
                             placeholder="Tìm người..."
                           />
                         </td>
                         <td class="p-3">
                            <select v-model="task.project" class="shadcn-table-select text-xs p-1 h-8">
                              <option value="">Trống</option>
                              <option v-for="p in getProjectsForHR(task.assignee_display)" :key="p[1]" :value="p[1]">
                                {{ p[0] }}
                              </option>
                            </select>
                         </td>
                         <td class="p-3"><input v-model="task.start_date" type="date" class="shadcn-table-input px-1 text-xs" /></td>
                         <td class="p-3"><input v-model="task.due_date" type="date" class="shadcn-table-input px-1 text-xs" /></td>
                         <td class="p-3"><textarea v-model="task.description" class="shadcn-table-input resize-y min-h-[60px] p-2 text-xs"></textarea></td>
                         <td class="p-4 text-center">
                            <button @click="emit('remove-task', idx)" class="btn-ghost-icon text-destructive hover:bg-destructive/10">
                               <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"></path><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path></svg>
                            </button>
                         </td>
                      </tr>
                   </tbody>
                </table>
                <datalist id="erp_employee_list_modal">
                  <option v-for="emp in dbEmployees" :key="emp.name" :value="emp.employee_name + ' (' + emp.name + ')'">{{ emp.user_id ? emp.user_id : '' }}</option>
                </datalist>
             </div>
        </div>

      </div>

      <!-- FOOTER -->
      <div class="p-4 border-t border-border bg-muted/20 flex justify-end gap-3 shrink-0">
        <button @click="emit('close')" class="shadcn-btn shadcn-btn-ghost px-6">Đóng</button>
        <button @click="emit('sync-erp')" class="shadcn-btn shadcn-btn-primary px-8">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="mr-2"><path d="M21 2v6h-6"></path><path d="M3 12a9 9 0 0 1 15-6.7L21 8"></path><path d="M3 22v-6h6"></path><path d="M21 12a9 9 0 0 1-15 6.7L3 16"></path></svg>
          {{ t('btn_sync') }}
        </button>
      </div>
      
    </div>
  </div>
</template>
