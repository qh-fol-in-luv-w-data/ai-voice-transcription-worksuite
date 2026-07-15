<script setup>
import { defineProps, defineEmits, computed, watch, ref } from 'vue'
import { meetingSummary, meetingConclusion, currentMeetingName, tasks } from '../composables/useVoiceApp'
import { saveMeetingDraft, exportDynamicDocx } from '../api'
import { ElMessage } from 'element-plus'

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

const attendeeQuery = ref('')
const filterAttendee = (query) => {
  attendeeQuery.value = query
}
const filteredAttendeeOptions = computed(() => {
  const query = attendeeQuery.value
  if (!query) return employeeOptions.value
  const q = query.toLowerCase()
  return employeeOptions.value.filter(opt => opt.label.toLowerCase().includes(q))
})
const onAttendeeVisibleChange = (visible) => {
  if (!visible) attendeeQuery.value = ''
}

const assigneeQueries = ref({})
const filterAssignee = (idx, query) => {
  assigneeQueries.value[idx] = query
}
const getFilteredAssigneeOptions = (idx) => {
  const query = assigneeQueries.value[idx]
  if (!query) return employeeOptions.value
  const q = query.toLowerCase()
  return employeeOptions.value.filter(opt => opt.label.toLowerCase().includes(q))
}
const onAssigneeVisibleChange = (idx, visible) => {
  if (!visible) assigneeQueries.value[idx] = ''
}


const onAttendeeSelect = (val) => {
  if(val) { 
    emit('toggle-attendee', val);
  }
}

// Auto-save logic
let saveTimeout = null
watch([meetingSummary, meetingConclusion, tasks], () => {
  if (saveTimeout) clearTimeout(saveTimeout)
  saveTimeout = setTimeout(async () => {
    if (!currentMeetingName.value) return
    try {
      await saveMeetingDraft(
        currentMeetingName.value,
        meetingSummary.value,
        meetingConclusion.value,
        JSON.stringify(tasks.value)
      )
    } catch(e) {
      console.error("Auto-save failed", e)
    }
  }, 1500)
}, { deep: true })

const downloadDynamicDocx = async () => {
  if (!currentMeetingName.value) return
  ElMessage.info("Đang tạo file DOCX...")
  try {
    // Force save the current state before exporting
    await saveMeetingDraft(
      currentMeetingName.value,
      meetingSummary.value,
      meetingConclusion.value,
      JSON.stringify(tasks.value)
    )
    const res = await exportDynamicDocx(currentMeetingName.value)
    if (res.status === 'success' && res.file_url) {
      downloadFile(res.file_url, 'Biên bản họp ngày ' + props.currentLocalDate() + '.docx')
    } else {
      ElMessage.error(res.message || "Không thể xuất DOCX")
    }
  } catch(e) {
    ElMessage.error("Lỗi xuất DOCX: " + e.toString())
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
            allow-create
            default-first-option
            placeholder="+ Tìm & thêm người..."
            style="width: 250px"
            :disabled="employeeOptions.length === 0"
            @change="onAttendeeSelect"
            clearable
            :filter-method="filterAttendee"
            @visible-change="onAttendeeVisibleChange"
          >
            <el-option
              v-for="emp in filteredAttendeeOptions"
              :key="emp.value"
              :label="emp.label"
              :value="emp.value"
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
              <el-button plain @click="downloadDynamicDocx">
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

        <div class="p-5 flex-col space-y-4">
          <!-- Summary & Conclusion section -->
          <div class="flex flex-col space-y-4 mb-4">
            <div>
              <h4 class="text-md font-medium mb-2">Tóm tắt nội dung chính</h4>
              <el-input
                v-model="meetingSummary"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 10 }"
                resize="none"
                placeholder="Nhập tóm tắt cuộc họp..."
              />
            </div>
            <div>
              <h4 class="text-md font-medium mb-2">Kết luận cuộc họp</h4>
              <el-input
                v-model="meetingConclusion"
                type="textarea"
                :autosize="{ minRows: 3, maxRows: 10 }"
                resize="none"
                placeholder="Nhập kết luận cuộc họp..."
              />
            </div>
          </div>

        <el-table :data="tasks" style="width: 100%" size="large" stripe class="custom-task-table" v-if="tasks && tasks.length > 0">
          <el-table-column type="index" label="#" width="50" align="center" />
          
          <el-table-column :label="t('col_name')" min-width="250">
            <template #default="{ row }">
              <el-input v-model="row.title" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" resize="none" placeholder="Tên nhiệm vụ" />
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
            <template #default="{ row, $index }">
              <el-select v-model="row.assignee_display" filterable placeholder="Tìm người..."
                :filter-method="(q) => filterAssignee($index, q)"
                @visible-change="(v) => onAssigneeVisibleChange($index, v)">
                <el-option
                  v-for="item in getFilteredAssigneeOptions($index)"
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
              <el-input v-model="row.description" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" resize="none" placeholder="Mô tả chi tiết" />
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
  border-radius: 20px !important;
  overflow: hidden;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5) !important;
}

html.dark :deep(.el-dialog) {
  background-color: #0f1423 !important; /* Match inner body color or slightly lighter */
  border: 1px solid rgba(255, 255, 255, 0.08);
}

html.dark :deep(.el-dialog__title) {
  color: white !important;
  font-weight: 600;
  font-size: 1.125rem;
}

/* Custom Table Styles - Modern & Soft */
html.dark :deep(.custom-task-table),
html.dark :deep(.el-table),
html.dark :deep(.el-table__expanded-cell) {
  background-color: transparent !important;
  --el-table-border-color: rgba(255, 255, 255, 0.05);
  --el-table-row-hover-bg-color: rgba(255, 255, 255, 0.02);
}

/* Header Cells */
html.dark :deep(.el-table th.el-table__cell) {
  background-color: transparent !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-right: none !important;
  color: #94a3b8 !important; /* Tailwind slate-400 */
  font-weight: 600;
  font-size: 12px;
  letter-spacing: 0.03em;
  padding: 12px 0;
}

/* Body Rows */
html.dark :deep(.el-table tr) {
  background-color: transparent !important;
}

html.dark :deep(.el-table .el-table__row--striped td.el-table__cell) {
  background-color: rgba(255, 255, 255, 0.02) !important;
}

/* Body Cells */
html.dark :deep(.el-table td.el-table__cell) {
  border-bottom: 1px dashed rgba(255, 255, 255, 0.1) !important;
  border-right: none !important;
  padding: 16px 0;
}

html.dark :deep(.el-table--border::after), 
html.dark :deep(.el-table--group::after), 
html.dark :deep(.el-table::before) {
  display: none;
}

/* Inputs, Selects, and Textareas */
html.dark :deep(.el-input__wrapper), 
html.dark :deep(.el-textarea__inner) {
  background-color: rgba(255, 255, 255, 0.03) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.1) inset !important;
  border-radius: 8px !important;
  color: #f1f5f9 !important; /* slate-100 */
  transition: all 0.2s ease;
  padding: 8px 12px;
}

html.dark :deep(.el-input__wrapper:hover), 
html.dark :deep(.el-textarea__inner:hover) {
  background-color: rgba(255, 255, 255, 0.06) !important;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.2) inset !important;
}

html.dark :deep(.el-input__wrapper.is-focus), 
html.dark :deep(.el-textarea__inner:focus) {
  box-shadow: 0 0 0 1px #4f46e5 inset !important; /* Indigo 600 */
  background-color: rgba(79, 70, 229, 0.05) !important;
}

html.dark :deep(.el-input__inner) {
  color: #f1f5f9 !important;
}

/* Select Dropdown Menu */
html.dark :deep(.el-select-dropdown) {
  background-color: #1e1e2d !important;
  border: 1px solid rgba(255, 255, 255, 0.1) !important;
  border-radius: 12px !important;
  box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5) !important;
}

html.dark :deep(.el-select-dropdown__item) {
  color: #cbd5e1 !important; /* slate-300 */
  border-radius: 6px;
  margin: 2px 4px;
}

html.dark :deep(.el-select-dropdown__item.hover), 
html.dark :deep(.el-select-dropdown__item:hover) {
  background-color: rgba(255, 255, 255, 0.08) !important;
  color: white !important;
}

/* Date Picker adjustments */
html.dark :deep(.el-date-editor) {
  --el-date-editor-width: 100%;
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
