<script setup>
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { voiceToTask, syncTasksToERP } from '../api'
import { useSession } from '../utils/session'
import { dict, uiLang, dbEmployees } from '../composables/useVoiceApp'
import { Microphone, VideoPause, Folder, Position, Warning, EditPen, Delete } from '@element-plus/icons-vue'

const { currentUser } = useSession()
const t = (key) => dict[uiLang.value][key] || key

const voiceTaskAudioFile = ref(null)
const voiceTaskRecordedUrl = ref('')
const voiceTaskIsRecording = ref(false)
const voiceTaskMediaRecorder = ref(null)
const voiceTaskChunks = ref([])

const isVoiceTaskProcessing = ref(false)
const voiceTaskStatus = ref('')
const parsedVoiceTask = ref(null)
const voiceTaskTranscript = ref('')
const isVoiceTaskSyncing = ref(false)
const voiceTaskSyncStatus = ref('')
const voiceTaskClarification = ref('')
const voiceTaskMissingFields = ref([])
const voiceTaskProjects = ref([])
const voiceTaskEmployees = ref([])

const voiceTaskRefineAudioFile = ref(null)
const voiceTaskRefineRecordedUrl = ref('')
const voiceTaskRefineIsRecording = ref(false)
const voiceTaskRefineMediaRecorder = ref(null)
const voiceTaskRefineChunks = ref([])

const employeeOptions = computed(() => {
  return voiceTaskEmployees.value.map(emp => ({
    value: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - '),
    label: [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ')
  }))
})

const handleVoiceTaskFileChange = (e) => {
  if (e.target.files.length > 0) {
    voiceTaskAudioFile.value = e.target.files[0]
    voiceTaskRecordedUrl.value = ''
  }
}

const toggleVoiceTaskRecording = async () => {
  if (voiceTaskIsRecording.value) {
    voiceTaskMediaRecorder.value.stop()
    voiceTaskIsRecording.value = false
    return
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    voiceTaskMediaRecorder.value = new MediaRecorder(stream)
    voiceTaskChunks.value = []
    
    voiceTaskMediaRecorder.value.ondataavailable = e => {
      if (e.data.size > 0) voiceTaskChunks.value.push(e.data)
    }
    
    voiceTaskMediaRecorder.value.onstop = () => {
      const blob = new Blob(voiceTaskChunks.value, { type: 'audio/wav' })
      voiceTaskAudioFile.value = blob
      voiceTaskAudioFile.value.name = 'voice_task_command.wav'
      voiceTaskRecordedUrl.value = URL.createObjectURL(blob)
      stream.getTracks().forEach(t => t.stop())
    }
    
    voiceTaskMediaRecorder.value.start()
    voiceTaskIsRecording.value = true
  } catch(e) {
    ElMessage.error("Lỗi truy cập Micro: " + e)
  }
}

const applyVoiceTaskResult = (res) => {
  voiceTaskStatus.value = t('voice_task_success')
  voiceTaskTranscript.value = res.transcript || voiceTaskTranscript.value

  let assignee = res.task.assignee_display || '';
  if (!assignee && currentUser.value && res.employees) {
    const emp = res.employees.find(e => e.user_id === currentUser.value);
    if (emp) assignee = [emp.employee_name, emp.user_id, emp.designation].filter(Boolean).join(' - ');
  }

  parsedVoiceTask.value = {
    title: res.task.task_name || '',
    assignee_display: assignee,
    assignee_hr_code: '',
    assignee_email: '',
    project: res.task.project_id || '',
    start_date: res.task.start_date || '',
    due_date: res.task.end_date || '',
    task_type: res.task.task_type || "task",
    description: res.task.description || ''
  }

  voiceTaskProjects.value = res.projects || []
  voiceTaskEmployees.value = res.employees || []
  voiceTaskClarification.value = res.task.clarification_question || ''
  voiceTaskMissingFields.value = res.task.missing_fields || []
}

const submitVoiceTask = async () => {
  if (!voiceTaskAudioFile.value) {
    ElMessage.warning(t('alert_no_file'))
    return
  }
  isVoiceTaskProcessing.value = true
  voiceTaskStatus.value = t('voice_task_transcribing')
  voiceTaskTranscript.value = ''
  parsedVoiceTask.value = null
  voiceTaskSyncStatus.value = ''
  voiceTaskClarification.value = ''
  voiceTaskMissingFields.value = []

  try {
    const res = await voiceToTask(voiceTaskAudioFile.value)
    if (res.status === 'success') {
      applyVoiceTaskResult(res)
    } else {
      voiceTaskStatus.value = '❌ Lỗi: ' + (res.message || 'Không rõ lỗi')
    }
  } catch(e) {
    voiceTaskStatus.value = '❌ Lỗi: ' + t('error_connect')
  } finally {
    isVoiceTaskProcessing.value = false
  }
}

const handleVoiceTaskRefineFileChange = (e) => {
  if (e.target.files.length > 0) {
    voiceTaskRefineAudioFile.value = e.target.files[0]
    voiceTaskRefineRecordedUrl.value = ''
  }
}

const toggleVoiceTaskRefineRecording = async () => {
  if (voiceTaskRefineIsRecording.value) {
    voiceTaskRefineMediaRecorder.value.stop()
    voiceTaskRefineIsRecording.value = false
    return
  }
  
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    voiceTaskRefineMediaRecorder.value = new MediaRecorder(stream)
    voiceTaskRefineChunks.value = []
    
    voiceTaskRefineMediaRecorder.value.ondataavailable = e => {
      if (e.data.size > 0) voiceTaskRefineChunks.value.push(e.data)
    }
    
    voiceTaskRefineMediaRecorder.value.onstop = () => {
      const blob = new Blob(voiceTaskRefineChunks.value, { type: 'audio/wav' })
      voiceTaskRefineAudioFile.value = blob
      voiceTaskRefineAudioFile.value.name = 'voice_task_refine.wav'
      voiceTaskRefineRecordedUrl.value = URL.createObjectURL(blob)
      stream.getTracks().forEach(t => t.stop())
    }
    
    voiceTaskRefineMediaRecorder.value.start()
    voiceTaskRefineIsRecording.value = true
  } catch(e) {
    ElMessage.error("Lỗi truy cập Micro: " + e)
  }
}

const submitVoiceTaskRefine = async () => {
  if (!voiceTaskRefineAudioFile.value) {
    ElMessage.warning(t('alert_no_file'))
    return
  }
  isVoiceTaskProcessing.value = true
  voiceTaskStatus.value = t('voice_task_parsing')

  try {
    const res = await voiceToTask(voiceTaskRefineAudioFile.value, parsedVoiceTask.value)
    if (res.status === 'success') {
      voiceTaskTranscript.value += (res.transcript ? ` -> ${res.transcript}` : '')
      applyVoiceTaskResult(res)
      voiceTaskRefineAudioFile.value = null
      voiceTaskRefineRecordedUrl.value = ''
    } else {
      voiceTaskStatus.value = '❌ Lỗi: ' + (res.message || 'Không rõ lỗi')
    }
  } catch(e) {
    voiceTaskStatus.value = '❌ Lỗi: ' + t('error_connect')
  } finally {
    isVoiceTaskProcessing.value = false
  }
}

const syncVoiceTaskToERP = async () => {
  if (!parsedVoiceTask.value) return
  isVoiceTaskSyncing.value = true
  voiceTaskSyncStatus.value = t('status_sync_wait')
  
  try {
    const displayStr = parsedVoiceTask.value.assignee_display
    if (displayStr) {
      const match = displayStr.match(/\((HR[-_]EMP[-_][^)]+)\)/i)
      if (match) parsedVoiceTask.value.assignee_hr_code = match[1]
      
      const matchedEmp = voiceTaskEmployees.value.find(e => [e.employee_name, e.user_id, e.designation].filter(Boolean).join(' - ') === displayStr)
      if (matchedEmp) {
        parsedVoiceTask.value.assignee_email = matchedEmp.user_id
        parsedVoiceTask.value.assignee_hr_code = matchedEmp.name
      }
    }

    const res = await syncTasksToERP([parsedVoiceTask.value])
    if (res.status === 'success') {
      const created = res.report.created_tasks ? res.report.created_tasks.length : 0
      if (created > 0) {
        voiceTaskSyncStatus.value = t('voice_task_sync_success')
      } else {
        voiceTaskSyncStatus.value = t('voice_task_sync_error') + (res.report.errors ? res.report.errors.join(', ') : '')
      }
    } else {
      voiceTaskSyncStatus.value = t('voice_task_sync_error') + res.message
    }
  } catch (e) {
    voiceTaskSyncStatus.value = t('error_connect')
  } finally {
    isVoiceTaskSyncing.value = false
  }
}
</script>

<template>
<div class="w-full flex flex-col gap-8 pb-10 mt-2 fade-in">
    <!-- Content Container Card -->
    <div class="bg-white dark:bg-surface-container-low border border-gray-200 dark:border-outline-variant rounded-lg p-lg shadow-sm flex flex-col min-h-[600px]">
      <!-- Header -->
      <div class="mb-xl">
        <h1 class="font-headline-lg text-headline-lg text-gray-900 dark:text-on-surface mb-xs">{{ t('voice_task_title') }}</h1>
        <p class="text-gray-600 dark:text-on-surface-variant text-body-md">{{ t('voice_task_desc') }}</p>
      </div>
      
      <!-- Suggestion Box -->
      <div class="bg-primary/5 border border-primary/20 rounded-md p-md mb-xl">
        <div class="font-medium text-primary mb-xs text-body-md">Gợi ý câu lệnh mẫu:</div>
        <div class="text-gray-700 dark:text-on-surface-variant text-body-sm italic">
          "{{ t('voice_task_placeholder') }}"
        </div>
      </div>
      
      <!-- Interaction Area -->
      <div class="flex-1 flex flex-col justify-center items-center gap-lg border border-gray-200 dark:border-outline-variant border-dashed rounded-lg p-xl bg-gray-50 dark:bg-surface-container-lowest/50 relative group transition-colors hover:bg-gray-100 dark:hover:bg-surface-container-lowest/80">
        <!-- Record Button -->
        <button @click="toggleVoiceTaskRecording" :class="['flex items-center justify-center gap-sm px-xl py-md border border-gray-300 dark:border-outline-variant rounded-full transition-all duration-300 shadow-sm w-full max-w-sm relative overflow-hidden', voiceTaskIsRecording ? 'bg-error/20 text-error border-error animate-pulse' : 'bg-white dark:bg-surface text-gray-900 dark:text-on-surface hover:text-primary hover:border-primary hover:shadow-[0_0_15px_rgba(192,193,255,0.15)]']">
          <div class="absolute inset-0 bg-primary/0 hover:bg-primary/5 transition-colors duration-300"></div>
          <span class="material-symbols-outlined transition-colors z-10" :class="voiceTaskIsRecording ? 'text-error' : 'text-gray-400 dark:text-outline group-hover:text-primary'">{{ voiceTaskIsRecording ? 'stop_circle' : 'mic' }}</span>
          <span class="font-medium z-10">{{ voiceTaskIsRecording ? t('btn_stop') : 'Bắt đầu thu âm' }}</span>
        </button>
        
        <!-- Divider -->
        <div class="w-full max-w-md flex items-center gap-md">
          <div class="h-px bg-gray-300 dark:bg-outline-variant flex-1"></div>
          <span class="text-gray-600 dark:text-on-surface-variant text-body-sm font-medium bg-gray-100 dark:bg-surface-container-highest px-md py-xs rounded-full border border-gray-300 dark:border-outline-variant/50 shadow-sm">Hoặc</span>
          <div class="h-px bg-gray-300 dark:bg-outline-variant flex-1"></div>
        </div>
        
        <!-- Drag & Drop Zone -->
        <div class="flex flex-col items-center text-center w-full max-w-md p-lg rounded-lg border-2 border-transparent border-dashed hover:border-primary/30 transition-colors cursor-pointer relative group-hover:border-gray-300 dark:group-hover:border-outline-variant">
          <input accept=".mp3,.wav,audio/*" class="absolute inset-0 w-full h-full opacity-0 cursor-pointer z-20" type="file" @change="handleVoiceTaskFileChange" />
          <div class="w-16 h-16 bg-gray-100 dark:bg-surface-container-highest rounded-full flex items-center justify-center mb-md group-hover:bg-primary-container group-hover:text-white dark:group-hover:text-on-primary-container transition-colors shadow-sm">
            <span class="material-symbols-outlined text-3xl text-gray-500 dark:text-on-surface-variant group-hover:text-white dark:group-hover:text-on-primary-container transition-colors">cloud_upload</span>
          </div>
          <h3 class="text-gray-900 dark:text-on-surface font-medium text-body-md mb-xs">Kéo thả file vào đây hoặc bấm để chọn</h3>
          <p class="text-primary/80 text-body-sm">{{ (voiceTaskAudioFile && !voiceTaskRecordedUrl) ? voiceTaskAudioFile.name : 'Hỗ trợ: .mp3, .wav' }}</p>
        </div>
      </div>
      
      <!-- Primary Action -->
      <div class="mt-xl">
        <button @click="submitVoiceTask" :disabled="!voiceTaskAudioFile || isVoiceTaskProcessing" class="w-full bg-gray-100 dark:bg-surface-variant text-gray-900 dark:text-on-surface hover:bg-primary hover:text-white font-medium py-md rounded-md transition-all duration-300 shadow-sm hover:shadow-md border border-gray-300 dark:border-outline-variant hover:border-primary flex items-center justify-center gap-sm disabled:opacity-50 disabled:cursor-not-allowed">
          <span v-if="isVoiceTaskProcessing" class="material-symbols-outlined animate-spin text-[18px]">autorenew</span>
          {{ isVoiceTaskProcessing ? t('voice_task_parsing') : 'Bắt đầu xử lý lệnh giọng nói' }}
        </button>
        <div v-if="voiceTaskStatus" class="text-center text-sm font-medium mt-2" :class="voiceTaskStatus.includes('✅') ? 'text-primary' : 'text-error'">
          {{ voiceTaskStatus }}
        </div>
      </div>
    </div>



    <!-- AI ASSISTANT CHAT BUBBLE (LUÔN HIỆN KHI CÓ TASK ĐỂ CHỈNH SỬA) -->
    <el-card v-if="parsedVoiceTask" shadow="hover" style="background: hsla(var(--primary)/0.03); margin-top: 1rem; border-color: var(--el-color-primary-light-7);">
        <template #header>
           <div class="flex items-center gap-3">
             <el-avatar :size="36" style="background: linear-gradient(135deg, #a855f7, #6366f1); font-size: 18px;">🤖</el-avatar>
             <div>
                <h3 class="text-primary font-medium m-0 flex items-center gap-2">Trợ lý AI</h3>
                <p v-if="voiceTaskMissingFields && voiceTaskMissingFields.length > 0" class="text-sm text-danger m-0 font-medium">Phát hiện thông tin tạo Task chưa đầy đủ</p>
                <p v-else class="text-sm m-0" style="color: #10b981; font-weight: 500;">Thông tin đã đầy đủ, bạn có thể lưu hoặc tiếp tục tinh chỉnh</p>
             </div>
           </div>
        </template>
        <div class="flex flex-col gap-4">
           <!-- Missing Fields Badges -->
           <div v-if="voiceTaskMissingFields && voiceTaskMissingFields.length > 0" class="flex flex-wrap gap-2 items-center">
              <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Thông tin còn thiếu:</span>
              <el-tag v-if="voiceTaskMissingFields.includes('project')" type="danger" effect="light" round>
                 <el-icon><Warning /></el-icon> Thiếu Dự án
              </el-tag>
              <el-tag v-if="voiceTaskMissingFields.includes('assignee')" type="danger" effect="light" round>
                 <el-icon><Warning /></el-icon> Thiếu Người phụ trách
              </el-tag>
              <el-tag v-if="voiceTaskMissingFields.includes('end_date')" type="danger" effect="light" round>
                 <el-icon><Warning /></el-icon> Thiếu Hạn chót
              </el-tag>
           </div>

           <!-- AI Clarification Question -->
           <div class="p-4 bg-background border border-border rounded-lg leading-relaxed text-base font-medium font-sans">
              "{{ (voiceTaskMissingFields && voiceTaskMissingFields.length > 0) ? voiceTaskClarification : 'Tất cả thông tin cốt lõi đã sẵn sàng! Bạn muốn bổ sung hay thay đổi gì nữa không?' }}"
           </div>

           <el-divider style="margin: 4px 0" />

           <!-- Voice Refinement input -->
           <div class="flex flex-col gap-3">
              <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Nói hoặc tải lên câu lệnh để chỉnh sửa:</span>
              
              <el-button @click="toggleVoiceTaskRefineRecording" :type="voiceTaskRefineIsRecording ? 'danger' : 'default'" :plain="!voiceTaskRefineIsRecording" size="large" class="w-full font-bold h-11 transition-all">
                 <template #icon>
                   <el-icon v-if="!voiceTaskRefineIsRecording"><Microphone /></el-icon>
                   <el-icon v-else><VideoPause /></el-icon>
                 </template>
                 {{ voiceTaskRefineIsRecording ? 'Dừng ghi âm bổ sung' : 'Nói để bổ sung/chỉnh sửa thông tin' }}
              </el-button>

              <div v-if="voiceTaskRefineRecordedUrl" class="w-full bg-background p-3 rounded-md border border-border flex items-center gap-4">
                 <audio :src="voiceTaskRefineRecordedUrl" controls class="flex-1"></audio>
              </div>

              <el-divider>Hoặc chọn file</el-divider>

              <div class="flex items-center gap-3">
                 <input type="file" id="voice-task-refine-upload" @change="handleVoiceTaskRefineFileChange" accept="audio/*" style="display:none" />
                 <label for="voice-task-refine-upload" class="flex-1">
                    <el-button tag="span" style="width: 100%" size="large" plain>
                       <template #icon><Folder /></template>
                       {{ voiceTaskRefineAudioFile ? voiceTaskRefineAudioFile.name : 'Chọn file ghi âm bổ sung' }}
                    </el-button>
                 </label>
                 <el-button @click="submitVoiceTaskRefine" type="primary" size="large" :loading="isVoiceTaskProcessing" :disabled="!voiceTaskRefineAudioFile" class="flex-1">
                    <template #icon><Position /></template>
                    Gửi yêu cầu chỉnh sửa
                 </el-button>
              </div>
           </div>
        </div>
    </el-card>

    <!-- PARSED TASK CARD (PREVIEW & EDIT) -->
    <el-card v-if="parsedVoiceTask" shadow="never" style="margin-top: 1rem; border-color: var(--el-color-primary-light-7);">
        <template #header>
           <h3 class="text-primary text-lg font-medium m-0 flex items-center gap-2">
             <el-icon><EditPen /></el-icon>
              Xem trước và hiệu chỉnh Task tạo từ AI
           </h3>
           <p class="text-sm text-muted-foreground m-0 mt-1">Các thông tin được trích xuất tự động qua OpenAI. Vui lòng xác nhận trước khi lưu.</p>
        </template>
        
        <div class="flex flex-col gap-6">
           <!-- Transcript Text -->
           <div class="flex flex-col gap-1.5 p-3 bg-muted/20 rounded-md border border-border">
             <span class="text-xs font-bold text-muted-foreground uppercase tracking-wider">Văn bản chuyển đổi từ giọng nói (STT):</span>
             <p class="text-sm font-medium leading-relaxed font-sans">"{{ voiceTaskTranscript }}"</p>
           </div>

           <!-- Form Fields Table -->
           <el-table :data="[parsedVoiceTask]" style="width: 100%" border size="small" :cell-style="{ verticalAlign: 'top', padding: '6px' }">
              <el-table-column :label="t('col_name')" min-width="250" header-align="center">
                <template #default="{ row }">
                  <div :class="{ 'missing-field': !row.title }">
                    <el-input v-model="row.title" type="textarea" :rows="2" resize="vertical" placeholder="⚠️ Chưa có tên task" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column header-align="center" label="Phân loại" min-width="130">
                <template #default="{ row }">
                  <el-select v-model="row.task_type" placeholder="Phân loại">
                    <el-option label="Task" value="task" />
                    <el-option label="Thông báo" value="noti" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column :label="t('col_assignee')" min-width="180" header-align="center">
                <template #default="{ row }">
                  <div :class="{ 'missing-field': voiceTaskMissingFields.includes('assignee') }">
                    <el-select v-model="row.assignee_display" filterable placeholder="⚠️ Chưa có người thực hiện" style="width: 100%">
                      <el-option v-for="emp in employeeOptions" :key="emp.value" :label="emp.label" :value="emp.value" />
                    </el-select>
                  </div>
                </template>
              </el-table-column>
              <el-table-column :label="t('col_project')" min-width="150" header-align="center">
                <template #default="{ row }">
                  <div :class="{ 'missing-field': voiceTaskMissingFields.includes('project') }">
                    <el-select v-model="row.project" style="width: 100%" placeholder="⚠️ Chưa có dự án">
                      <el-option label="[Không có]" value="" />
                      <el-option v-for="p in voiceTaskProjects" :key="p.name" :label="p.project_name ? p.project_name : p.name" :value="p.name" />
                    </el-select>
                  </div>
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_start')" width="130">
                <template #default="{ row }">
                  <el-date-picker v-model="row.start_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" />
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_due')" width="130">
                <template #default="{ row }">
                  <div :class="{ 'missing-field': voiceTaskMissingFields.includes('end_date') }">
                    <el-date-picker v-model="row.due_date" type="date" style="width: 100%" value-format="YYYY-MM-DD" placeholder="⚠️ Chưa có hạn chót" />
                  </div>
                </template>
              </el-table-column>
              <el-table-column header-align="center" :label="t('col_desc')" min-width="250">
                <template #default="{ row }">
                  <el-input v-model="row.description" type="textarea" :rows="3" resize="none" />
                </template>
              </el-table-column>
           </el-table>
        </div>

        <template #footer>
           <div class="flex justify-between items-center w-full">
             <span class="text-sm font-semibold font-mono" :class="voiceTaskSyncStatus.includes('✅') ? 'text-primary' : 'text-danger'">{{ voiceTaskSyncStatus }}</span>
             <el-button @click="syncVoiceTaskToERP" type="primary" size="large" :loading="isVoiceTaskSyncing">
                {{ isVoiceTaskSyncing ? '⏳ Đang đồng bộ...' : 'Tạo & Đồng bộ Task lên ERPNext' }}
             </el-button>
           </div>
        </template>
    </el-card>
 </div>
</template>
