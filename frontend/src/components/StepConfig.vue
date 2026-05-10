<template>
  <div class="step-config">
    <div class="config-card">
      <div class="config-header">
        <h2>配置项目与维度</h2>
        <p>选择 DataWorks 项目并输入要添加的维度信息</p>
      </div>

      <el-form :model="form" :rules="rules" ref="formRef" label-width="140px" class="config-form">
        <el-form-item label="项目空间" prop="projectId">
          <el-select
            v-model="form.projectId"
            placeholder="输入关键词搜索项目空间"
            filterable
            clearable
            :filter-method="filterProjects"
            :loading="loading"
            class="form-select"
          >
            <el-option
              v-for="p in filteredProjects"
              :key="p.id"
              :label="p.id"
              :value="p.id"
            />
          </el-select>
          <el-button type="primary" text @click="loadProjects" :loading="loading" style="margin-left: 8px;">
            <el-icon><Refresh /></el-icon>
          </el-button>
        </el-form-item>

        <el-form-item label="目标表名" prop="tableName">
          <el-input v-model="form.tableName" placeholder="如: dwr_spock_test2_1d" class="form-input" />
        </el-form-item>

        <el-form-item label="新增维度" prop="dimensionName">
          <el-input v-model="form.dimensionName" placeholder="英文列名，如: exp_sts" class="form-input" />
        </el-form-item>

        <el-form-item label="维度中文名" prop="dimensionChineseName">
          <el-input v-model="form.dimensionChineseName" placeholder="如: 实验状态" class="form-input" />
        </el-form-item>
      </el-form>

      <div class="config-actions">
        <el-button type="primary" size="large" @click="submit" :loading="loading" class="submit-btn">
          开始分析
          <el-icon class="btn-icon"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, ArrowRight } from '@element-plus/icons-vue'
import api from '../api/index.js'

const emit = defineEmits(['next'])
const formRef = ref(null)
const loading = ref(false)
const projects = ref([])
const searchKeyword = ref('')

const form = reactive({
  projectId: '',
  tableName: '',
  dimensionName: '',
  dimensionChineseName: '',
})

const rules = {
  projectId: [{ required: true, message: '请选择项目空间', trigger: 'change' }],
  tableName: [{ required: true, message: '请输入目标表名', trigger: 'blur' }],
  dimensionName: [{ required: true, message: '请输入新增维度', trigger: 'blur' }],
}

const filteredProjects = computed(() => {
  if (!searchKeyword.value) return projects.value
  const kw = searchKeyword.value.toLowerCase()
  return projects.value.filter(p => p.id.toLowerCase().includes(kw))
})

function filterProjects(keyword) {
  searchKeyword.value = keyword
}

async function loadProjects() {
  loading.value = true
  try {
    projects.value = await api.getProjects()
    ElMessage.success(`已加载 ${projects.value.length} 个项目空间`)
  } catch (e) {
    ElMessage.error('获取项目列表失败: ' + e.message)
  } finally {
    loading.value = false
  }
}

function submit() {
  formRef.value.validate((valid) => {
    if (!valid) return
    emit('next', { ...form })
  })
}

onMounted(loadProjects)
</script>

<style scoped>
.step-config {
  max-width: 700px;
  margin: 0 auto;
}

.config-card {
  background: #fff;
  border-radius: 16px;
  padding: 40px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}

.config-header {
  text-align: center;
  margin-bottom: 32px;
}

.config-header h2 {
  margin: 0 0 8px 0;
  font-size: 24px;
  font-weight: 600;
  color: #1a1a1a;
}

.config-header p {
  margin: 0;
  color: #909399;
  font-size: 14px;
}

.config-form {
  margin-top: 24px;
}

.form-select,
.form-input {
  width: 100%;
}

.form-select :deep(.el-input__wrapper),
.form-input :deep(.el-input__wrapper) {
  border-radius: 10px;
  padding: 4px 12px;
  height: 44px;
}

.config-actions {
  text-align: center;
  margin-top: 40px;
}

.submit-btn {
  width: 200px;
  height: 48px;
  font-size: 16px;
  border-radius: 12px;
}

.btn-icon {
  margin-left: 8px;
}
</style>
