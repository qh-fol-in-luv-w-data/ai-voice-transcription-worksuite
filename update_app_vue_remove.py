import re

with open('frontend/src/App.vue', 'r') as f:
    content = f.read()

# 1. Add removeSegment function
func_old = """const insertSegmentAfter = (idx) => {"""
func_new = """const removeSegment = (idx) => {
  transcriptResults.value.splice(idx, 1);
  isTranscriptModified.value = true;
}

const insertSegmentAfter = (idx) => {"""
content = content.replace(func_old, func_new)

# 2. Add Delete button to Block 1
block1_old = """                     <el-button size="small" type="primary" circle plain @click="insertSegmentAfter(idx)" title="Thêm hội thoại bên dưới" class="opacity-0 group-hover:opacity-100 transition-opacity"><el-icon><Plus /></el-icon></el-button>"""
block1_new = """                     <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                       <el-button size="small" type="primary" circle plain @click="insertSegmentAfter(idx)" title="Thêm hội thoại bên dưới"><el-icon><Plus /></el-icon></el-button>
                       <el-button size="small" type="danger" circle plain @click="removeSegment(idx)" title="Xóa hội thoại này"><el-icon><Delete /></el-icon></el-button>
                     </div>"""
content = content.replace(block1_old, block1_new)

with open('frontend/src/App.vue', 'w') as f:
    f.write(content)
