<template>
  <div class="step-modify">
    <!-- Loading -->
    <div v-if="!modifyResult" class="loading-container">
      <div class="loading-spinner">
        <el-icon :size="48" class="loading-icon"><Loading /></el-icon>
      </div>
      <p class="loading-text">正在修改 SQL...</p>
      <p class="loading-subtext">请稍候，LLM 正在分析和改写 SQL 代码</p>
    </div>

    <template v-else>
      <!-- Status Cards -->
      <div class="status-row">
        <div class="status-card" :class="modifyResult.saved_to_dataworks ? 'status-success' : 'status-pending'">
          <el-icon :size="32"><Check v-if="modifyResult.saved_to_dataworks" /><Document v-else /></el-icon>
          <div class="status-label">保存状态</div>
          <div class="status-value">{{ modifyResult.saved_to_dataworks ? '已保存' : '待保存' }}</div>
        </div>
        <div class="status-card">
          <el-icon :size="32"><Timer /></el-icon>
          <div class="status-label">修改行数</div>
          <div class="status-value">{{ diffCount }} 行</div>
        </div>
      </div>

      <!-- Diff View -->
      <el-card class="diff-card">
        <template #header>
          <span>SQL 修改预览</span>
          <el-tag :type="modifyResult.error ? 'danger' : 'success'" size="small" style="margin-left: 12px;">
            {{ modifyResult.error ? '有错误' : '检查通过' }}
          </el-tag>
        </template>
        <div class="diff-view">
          <div v-for="(line, idx) in diffLines" :key="idx" :class="['diff-line', line.type]">
            <span class="line-num">{{ line.orig_line_num || line.mod_line_num || '' }}</span>
            <span class="line-content">{{ line.content }}</span>
          </div>
        </div>
      </el-card>

      <!-- Actions -->
      <div class="step-actions">
        <el-button @click="$emit('prev')">上一步</el-button>
        <el-button type="primary" @click="$emit('next')">
          确认并继续
          <el-icon class="btn-icon"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { Check, Document, Timer, ArrowRight, Loading } from '@element-plus/icons-vue'

const props = defineProps(['config', 'analysis', 'modifyResult'])
const emit = defineEmits(['prev', 'next'])

const diffLines = computed(() => props.modifyResult?.diff_lines || [])
const diffCount = computed(() => diffLines.value.length)
</script>

<style scoped>
.step-modify {
  max-width: 1200px;
  margin: 0 auto;
}

/* Loading */
.loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 20px;
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}

.loading-spinner {
  margin-bottom: 24px;
}

.loading-icon {
  color: #409eff;
  animation: spin 1.5s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.loading-text {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 8px 0;
}

.loading-subtext {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.status-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.status-card {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  text-align: center;
}

.status-card .el-icon {
  color: #409eff;
  margin-bottom: 8px;
}

.status-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 4px;
}

.status-value {
  font-size: 20px;
  font-weight: 700;
  color: #1a1a1a;
}

.status-success .status-value {
  color: #67c23a;
}

.status-pending .status-value {
  color: #909399;
}

.diff-card {
  border-radius: 12px;
}

.diff-view {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  max-height: 500px;
  overflow-y: auto;
}

.diff-line {
  display: flex;
  line-height: 1.8;
  padding: 2px 8px;
  border-radius: 4px;
}

.diff-line.added {
  background: rgba(103, 194, 58, 0.15);
}

.diff-line.removed {
  background: rgba(245, 108, 108, 0.15);
}

.diff-line .line-num {
  width: 40px;
  color: #606266;
  text-align: right;
  margin-right: 12px;
  flex-shrink: 0;
}

.diff-line .line-content {
  color: #d4d4d4;
  word-break: break-all;
}

.step-actions {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 32px;
  padding-bottom: 40px;
}

.btn-icon {
  margin-left: 4px;
}
</style>
