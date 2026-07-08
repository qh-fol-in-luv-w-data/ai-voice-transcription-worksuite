<script setup>
import { defineProps, defineEmits, computed } from 'vue'

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

const employeeOptions = computed(() => {
  return props.dbEmployees.map(emp => ({
    value: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - '),
    label: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ')
  }))
})

const onAttendeeSelect = (val) => {
  if(val) { 
    emit('toggle-attendee', val);
  }
}
</script>

<template>
  <el-dialog
    :model-value="isOpen"
    @update:model-value="(val) => { if(!val) emit('close') }"
    title="Kết quả trích xuất Task"
    width="95%"
    top="5vh"
    destroy-on-close
    class="task-modal"
  >
    <div class="flex-col space-y-6">
      
      <!-- ATTENDEES -->
      <div class="bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant rounded-2xl shadow-sm">
        <div class="p-4 border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low rounded-t-2xl">
          <div class="flex justify-between items-center w-full">
            <div>
              <h3 class="text-lg font-medium m-0 flex items-center gap-2">
                <el-icon><User /></el-icon>
                {{ t('attendees_title') }}
              </h3>
              <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('attendees_desc') }}</p>
            </div>
            <el-button
              v-if="selectedAttendees.length > 0"
              type="primary"
              :loading="isReanalyzing"
              @click="emit('reanalyze')"
            >
              <template #icon v-if="!isReanalyzing">
                <el-icon><RefreshRight /></el-icon>
              </template>
              {{ isReanalyzing ? t('reanalyzing') : t('btn_reanalyze') }}
            </el-button>
          </div>
        </div>
        
        <div class="p-5 flex flex-wrap items-center gap-3">
          <el-tag
            v-for="name in selectedAttendees"
            :key="name"
            closable
            size="large"
            @close="emit('remove-attendee', name)"
            type="primary"
            effect="light"
            round
          >
            {{ name }}
          </el-tag>

          <el-select
            filterable
            placeholder="+ Tìm & thêm người..."
            style="width: 250px"
            :disabled="voiceDbSpeakers.length === 0"
            @change="onAttendeeSelect"
            clearable
          >
            <el-option
              v-for="spk in voiceDbSpeakers"
              :key="spk.speaker_name"
              :label="spk.speaker_name + (spk.email ? ' - ' + spk.email : '')"
              :value="spk.speaker_name"
            />
          </el-select>
        </div>
      </div>

      <!-- TASK LIST -->
      <div class="bg-white dark:bg-surface border border-gray-200 dark:border-outline-variant rounded-2xl shadow-sm">
        <div class="p-4 border-b border-gray-200 dark:border-outline-variant bg-gray-50 dark:bg-surface-container-low rounded-t-2xl">
          <div class="flex justify-between items-center">
            <div>
              <h3 class="text-lg font-medium m-0">{{ t('task_list') }}</h3>
              <p class="text-sm text-muted-foreground m-0 mt-1">{{ t('task_desc') }}</p>
            </div>
            <div class="flex gap-2">
              <el-button v-if="excelUrl" plain @click="downloadFile(excelUrl, 'Task ngày ' + currentLocalDate() + '.xlsx')">
                <el-icon class="mr-1"><Download /></el-icon>
                {{ t('export_xlsx') }}
              </el-button>
              <el-button v-if="docxUrl" plain @click="downloadFile(docxUrl, 'Biên bản họp ngày ' + currentLocalDate() + '.docx')">
                <el-icon class="mr-1"><Document /></el-icon>
                {{ t('export_docx') }}
              </el-button>
              <el-button type="primary" plain @click="emit('add-task')">
                <el-icon class="mr-1"><Plus /></el-icon>
                {{ t('add_task') }}
              </el-button>
            </div>
          </div>
          </div>
        </div>

        <div class="p-5">
        <el-table :data="tasks" style="width: 100%" border stripe size="large" class="custom-el-table">
          <el-table-column type="index" label="#" width="50" align="center" />
          
          <el-table-column :label="t('col_name')" min-width="250">
            <template #default="{ row }">
              <el-input v-model="row.title" type="textarea" :rows="2" resize="vertical" placeholder="Tên nhiệm vụ" />
            </template>
          </el-table-column>
          
          <el-table-column label="Phân loại" min-width="130">
            <template #default="{ row }">
              <el-select v-model="row.task_type" placeholder="Phân loại">
                <el-option label="Task" value="task" />
                <el-option label="Thông báo" value="noti" />
              </el-select>
            </template>
          </el-table-column>
          
          <el-table-column :label="t('col_assignee')" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.assignee_display" filterable placeholder="Tìm người...">
                <el-option
                  v-for="item in employeeOptions"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column :label="t('col_project')" min-width="220">
            <template #default="{ row }">
              <el-select v-model="row.project" filterable placeholder="Trống" clearable>
                <el-option
                  v-for="p in getProjectsForHR(row.assignee_display)"
                  :key="p[1]"
                  :label="p[0]"
                  :value="p[1]"
                />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column :label="t('col_start')" width="160">
            <template #default="{ row }">
              <el-date-picker
                v-model="row.start_date"
                type="date"
                placeholder="Bắt đầu"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </template>
          </el-table-column>

          <el-table-column :label="t('col_due')" width="160">
            <template #default="{ row }">
              <el-date-picker
                v-model="row.due_date"
                type="date"
                placeholder="Hạn chót"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </template>
          </el-table-column>



          <el-table-column :label="t('col_desc')" min-width="250">
            <template #default="{ row }">
              <el-input v-model="row.description" type="textarea" :rows="2" resize="vertical" placeholder="Mô tả chi tiết" />
            </template>
          </el-table-column>

          <el-table-column :label="t('col_del')" width="70" align="center" fixed="right">
            <template #default="{ $index }">
              <el-button type="danger" circle @click="emit('remove-task', $index)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        </div>
      </div>

    <template #footer>
      <div class="dialog-footer pt-4 mt-2 border-t border-gray-200 dark:border-outline-variant flex justify-end gap-3">
        <button @click="emit('close')" class="px-5 py-2 rounded-lg font-medium border border-gray-300 dark:border-outline-variant hover:bg-gray-100 dark:hover:bg-surface-variant transition-colors text-gray-700 dark:text-on-surface">Đóng</button>
        <button @click="emit('sync-erp')" class="px-5 py-2 rounded-lg font-medium bg-primary text-white hover:bg-primary/90 transition-colors flex items-center gap-2 shadow-sm">
          <el-icon><UploadFilled /></el-icon>
          {{ t('btn_sync') }}
        </button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.task-modal :deep(.el-dialog__body) {
  padding-top: 10px;
  padding-bottom: 10px;
}

:deep(.el-dialog) {
  border-radius: 16px !important;
  overflow: hidden;
}

html.dark :deep(.el-dialog) {
  background-color: #1e1e2d !important;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

html.dark :deep(.el-dialog__title) {
  color: white !important;
}

html.dark :deep(.el-table),
html.dark :deep(.el-table__expanded-cell) {
  background-color: transparent !important;
  color: #fff !important;
}

html.dark :deep(.el-table th), html.dark :deep(.el-table tr) {
  background-color: transparent !important;
  color: #e2e8f0 !important;
}

html.dark :deep(.el-table td), html.dark :deep(.el-table th.is-leaf) {
  border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
}

html.dark :deep(.el-table--border) {
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

html.dark :deep(.el-input__wrapper), html.dark :deep(.el-textarea__inner) {
  background-color: rgba(255, 255, 255, 0.05) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
  color: white !important;
}

html.dark :deep(.el-input__inner) {
  color: white !important;
}

html.dark :deep(.el-select-dropdown) {
  background-color: #1e1e2d !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
}

html.dark :deep(.el-select-dropdown__item) {
  color: #e2e8f0 !important;
}

html.dark :deep(.el-select-dropdown__item.hover), html.dark :deep(.el-select-dropdown__item:hover) {
  background-color: rgba(255, 255, 255, 0.1) !important;
}

.space-y-6 > * + * {
  margin-top: 1.5rem;
}
.m-0 {
  margin: 0;
}
.mt-1 {
  margin-top: 0.25rem;
}
</style>
