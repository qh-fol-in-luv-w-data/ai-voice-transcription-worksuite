import re

with open('frontend/src/App.vue', 'r') as f:
    content = f.read()

# 1. Update aside style
aside_old = """      <aside class="transition-all duration-300 ease-in-out bg-muted/10 flex flex-col h-full shrink-0 overflow-hidden border-border" :style="{ width: isSidebarOpen ? '260px' : '0px', borderRightWidth: isSidebarOpen ? '1px' : '0px' }">"""
aside_new = """      <aside class="transition-all duration-300 ease-in-out bg-muted/10 flex flex-col h-full shrink-0 overflow-hidden border-border" :style="{ width: isSidebarOpen ? '260px' : '0px', minWidth: isSidebarOpen ? '260px' : '0px', maxWidth: isSidebarOpen ? '260px' : '0px', opacity: isSidebarOpen ? 1 : 0, borderRightWidth: isSidebarOpen ? '1px' : '0px' }">"""
content = content.replace(aside_old, aside_new)

# 2. Add insertSegmentAfter function
func_code = """const removeTask = (idx) => {
  tasks.value.splice(idx, 1)
}

const insertSegmentAfter = (idx) => {
  let time = 0;
  if (transcriptResults.value.length > 0 && transcriptResults.value[idx]) {
     time = transcriptResults.value[idx][1] || transcriptResults.value[idx][0] || 0;
  }
  transcriptResults.value.splice(idx + 1, 0, [time, time, "Tên người nói", "Nhập nội dung..."]);
  isTranscriptModified.value = true;
}"""
content = content.replace("const removeTask = (idx) => {\n  tasks.value.splice(idx, 1)\n}", func_code)

# 3. Update transcriptResults rendering (Block 1 - transcribe tab)
block1_old = """                 <div v-if="seg[3] && seg[3].trim()" class="log-entry">
                   <div class="log-meta">
                     <span class="log-speaker" :style="{ color: stringToColor(seg[2]) }">{{ seg[2] }}</span>
                     <span class="log-time">[{{ seg[0].toFixed(2) }}s]</span>
                   </div>
                   <el-input v-model="seg[3]" type="textarea" :autosize="{ minRows: 1 }" class="transparent-input log-text" @input="isTranscriptModified = true" />
                 </div>"""

block1_new = """                 <div class="log-entry relative group pb-4">
                   <div class="log-meta flex justify-between items-center bg-muted/20 px-2 py-1 rounded-t-md">
                     <div class="flex items-center gap-2">
                       <el-input v-model="seg[2]" size="small" class="w-[150px] !bg-transparent border-none font-bold" :style="{ color: stringToColor(seg[2]) }" @input="isTranscriptModified = true" />
                       <span class="log-time text-xs text-muted-foreground">[{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s]</span>
                     </div>
                     <el-button size="small" type="primary" circle plain @click="insertSegmentAfter(idx)" title="Thêm hội thoại bên dưới" class="opacity-0 group-hover:opacity-100 transition-opacity"><el-icon><Plus /></el-icon></el-button>
                   </div>
                   <el-input v-model="seg[3]" type="textarea" :autosize="{ minRows: 1 }" class="transparent-input log-text mt-1" @input="isTranscriptModified = true" />
                 </div>"""
content = content.replace(block1_old, block1_new)

# 4. Update transcriptResults rendering (Block 2 - view_meeting tab)
block2_old = """                          <div v-if="seg[3] && seg[3].trim()" class="log-entry">
                            <div class="log-meta">
                              <span class="log-speaker" :style="{ color: stringToColor(seg[2]) }">{{ seg[2] }}</span>
                              <span class="log-time">[{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s]</span>
                            </div>
                            <el-input v-model="seg[3]" type="textarea" :autosize="{ minRows: 1 }" class="transparent-input log-text" @input="isTranscriptModified = true" />
                          </div>"""

block2_new = """                          <div class="log-entry relative group pb-4">
                            <div class="log-meta flex justify-between items-center bg-muted/20 px-2 py-1 rounded-t-md">
                              <div class="flex items-center gap-2">
                                <el-input v-model="seg[2]" size="small" class="w-[150px] !bg-transparent border-none font-bold" :style="{ color: stringToColor(seg[2]) }" @input="isTranscriptModified = true" />
                                <span class="log-time text-xs text-muted-foreground">[{{ seg[0]?.toFixed ? seg[0].toFixed(2) : seg[0] }}s]</span>
                              </div>
                              <el-button size="small" type="primary" circle plain @click="insertSegmentAfter(idx)" title="Thêm hội thoại bên dưới" class="opacity-0 group-hover:opacity-100 transition-opacity"><el-icon><Plus /></el-icon></el-button>
                            </div>
                            <el-input v-model="seg[3]" type="textarea" :autosize="{ minRows: 1 }" class="transparent-input log-text mt-1" @input="isTranscriptModified = true" />
                          </div>"""
content = content.replace(block2_old, block2_new)

with open('frontend/src/App.vue', 'w') as f:
    f.write(content)
