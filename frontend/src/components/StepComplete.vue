<template>
  <div class="step-complete">
    <div class="result-card">
      <el-result icon="success" title="操作完成" sub-title="DataWorks 加维度流程已执行完毕">
        <template #icon>
          <div class="success-icon">
            <el-icon :size="64" color="#67c23a"><CircleCheck /></el-icon>
          </div>
        </template>
      </el-result>

      <div class="result-grid" v-if="executionResult">
        <div class="result-item" :class="executionResult.saveDraft ? 'success' : 'pending'">
          <el-icon :size="28"><component :is="executionResult.saveDraft ? Check : Close" /></el-icon>
          <div class="result-label">保存草稿</div>
          <div class="result-status">{{ executionResult.saveDraft ? '✅ 已保存' : '⏭️ 未执行' }}</div>
        </div>
        <div class="result-item" :class="executionResult.alterTable ? 'success' : 'pending'">
          <el-icon :size="28"><component :is="executionResult.alterTable ? Check : Close" /></el-icon>
          <div class="result-label">ALTER TABLE</div>
          <div class="result-status">{{ executionResult.alterTable ? '✅ 已执行' : '⏭️ 未执行' }}</div>
        </div>
        <div class="result-item" :class="executionResult.backfill ? 'success' : 'pending'">
          <el-icon :size="28"><component :is="executionResult.backfill ? Check : Close" /></el-icon>
          <div class="result-label">历史回刷</div>
          <div class="result-status">{{ executionResult.backfill ? '✅ 已执行' : '⏭️ 未执行' }}</div>
        </div>
        <div class="result-item" :class="executionResult.syncBI ? 'success' : 'pending'">
          <el-icon :size="28"><component :is="executionResult.syncBI ? Check : Close" /></el-icon>
          <div class="result-label">BI 同步</div>
          <div class="result-status">{{ executionResult.syncBI ? '✅ 已同步' : '⏭️ 未执行' }}</div>
        </div>
      </div>

      <div v-if="executionResult?.errors?.length" class="error-section">
        <el-alert type="error" title="执行中出现错误" show-icon :closable="false">
          <div v-for="err in executionResult.errors" :key="err">• {{ err }}</div>
        </el-alert>
      </div>

      <div class="complete-actions">
        <el-button @click="$emit('prev')" size="large">
          <el-icon class="btn-icon"><ArrowLeft /></el-icon>
          上一步
        </el-button>
        <el-button type="primary" size="large" @click="restart">
          <el-icon class="btn-icon"><RefreshLeft /></el-icon>
          重新开始
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { CircleCheck, Check, Close, RefreshLeft, ArrowLeft } from '@element-plus/icons-vue'

const props = defineProps(['config', 'executionResult'])
const emit = defineEmits(['prev'])

function restart() {
  window.location.reload()
}
</script>

<style scoped>
.step-complete {
  max-width: 800px;
  margin: 0 auto;
  text-align: center;
}

.result-card {
  background: #fff;
  border-radius: 16px;
  padding: 48px 32px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.06);
}

.success-icon {
  margin-bottom: 16px;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin: 32px 0;
  text-align: left;
}

.result-item {
  background: #f5f7fa;
  border-radius: 12px;
  padding: 20px 16px;
  text-align: center;
  transition: all 0.3s;
}

.result-item.success {
  background: #f0f9ff;
}

.result-item.success .el-icon {
  color: #67c23a;
}

.result-item.pending .el-icon {
  color: #c0c4cc;
}

.result-label {
  font-size: 13px;
  color: #909399;
  margin-top: 8px;
  margin-bottom: 4px;
}

.result-status {
  font-size: 14px;
  font-weight: 600;
  color: #1a1a1a;
}

.error-section {
  margin-top: 24px;
  text-align: left;
}

.complete-actions {
  margin-top: 40px;
  display: flex;
  justify-content: center;
  gap: 16px;
}

.btn-icon {
  margin-right: 8px;
}
</style>
