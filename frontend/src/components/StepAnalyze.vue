<template>
  <div class="step-analyze">
    <!-- Loading State -->
    <div v-if="!analysis" class="loading-container">
      <div class="loading-spinner">
        <el-icon :size="48" class="loading-icon"><Loading /></el-icon>
      </div>
      <p class="loading-text">正在分析上下游...</p>
      <p class="loading-subtext">请稍候，正在获取表结构信息和血缘关系</p>
    </div>

    <template v-else>
      <!-- KPI Cards -->
      <div class="kpi-row">
        <div class="kpi-card">
          <div class="kpi-label">上游表数</div>
          <div class="kpi-value">{{ analysis.upstream_tables?.length || 0 }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">下游节点数</div>
          <div class="kpi-value">{{ analysis.downstream_nodes?.length || 0 }}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">维度展开方式</div>
          <div class="kpi-value kpi-small">{{ expansionTypeLabel }}</div>
        </div>
        <div class="kpi-card" :class="hasIssues ? 'kpi-warning' : 'kpi-success'">
          <div class="kpi-label">分析状态</div>
          <div class="kpi-value kpi-small">{{ hasIssues ? '有问题' : '通过' }}</div>
        </div>
      </div>

      <!-- Issues Alert -->
      <el-card v-if="hasIssues" class="section-card warning-card">
        <template #header>
          <span><el-icon><Warning /></el-icon> 检测到上游问题</span>
        </template>
        <div v-for="issue in analysis.issues" :key="issue" class="issue-item">
          <el-icon><WarningFilled /></el-icon> {{ issue }}
        </div>
        <el-radio-group v-model="issueResolution" class="issue-actions">
          <el-radio label="source">从推荐来源表补充</el-radio>
          <el-radio label="stop">停止，手动处理上游</el-radio>
        </el-radio-group>
      </el-card>

      <!-- Upstream Tables -->
      <el-card class="section-card">
        <template #header>
          <span>上游表字段存在性</span>
        </template>
        <el-table :data="analysis.upstream_tables" border stripe>
          <el-table-column prop="table_name" label="表名" min-width="180" />
          <el-table-column prop="alias" label="别名" width="100" />
          <el-table-column label="字段存在" width="120">
            <template #default="scope">
              <el-tag :type="scope.row.field_exists ? 'success' : 'danger'" size="small">
                {{ scope.row.field_exists ? '✅ 存在' : '❌ 缺失' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="来源方式" width="150">
            <template #default="scope">
              <el-tag v-if="scope.row.via_select_star && scope.row.ddl_verified && scope.row.field_exists" type="success" size="small">SELECT * (DDL确认)</el-tag>
              <el-tag v-else-if="scope.row.via_select_star && scope.row.ddl_verified && !scope.row.field_exists" type="danger" size="small">SELECT * (DDL缺失)</el-tag>
              <el-tag v-else-if="scope.row.via_select_star && !scope.row.ddl_verified" type="warning" size="small">SELECT * (待验证)</el-tag>
              <el-tag v-else-if="scope.row.field_exists && !scope.row.via_select_star" type="success" size="small">显式引用</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="推荐来源" width="120">
            <template #default="scope">
              <el-tag v-if="scope.row.suggested_source" type="warning" size="small">推荐</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- Downstream Nodes -->
      <el-card class="section-card">
        <template #header>
          <span>下游节点</span>
        </template>
        <el-table :data="analysis.downstream_nodes" border stripe v-if="analysis.downstream_nodes?.length > 0">
          <el-table-column prop="node_id" label="节点ID" width="120" />
          <el-table-column prop="node_name" label="节点名" />
          <el-table-column prop="project_env" label="环境" width="100" />
        </el-table>
        <el-empty v-else description="未找到下游节点" />
      </el-card>

      <!-- Actions -->
      <div class="step-actions">
        <el-button @click="$emit('prev')">上一步</el-button>
        <el-button type="primary" @click="next" :disabled="hasIssues && issueResolution === 'stop'">
          确认并继续
          <el-icon class="btn-icon"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Warning, WarningFilled, ArrowRight, Loading } from '@element-plus/icons-vue'

const props = defineProps(['config', 'analysis'])
const emit = defineEmits(['prev', 'next'])

const hasIssues = computed(() => props.analysis?.issues?.length > 0)
const issueResolution = ref('source')

const expansionTypeLabel = computed(() => {
  const map = { cube: 'GROUP BY CUBE', lateral_view: 'LATERAL VIEW EXPLODE', group_by: '普通 GROUP BY' }
  return map[props.analysis?.expansion_type] || props.analysis?.expansion_type
})

function next() {
  emit('next', {
    selectedUpstream: issueResolution.value === 'source' ? 'recommended' : null,
    issueResolution: issueResolution.value,
  })
}
</script>

<style scoped>
.step-analyze {
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

/* KPI Cards */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.kpi-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px 24px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  text-align: center;
}

.kpi-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.kpi-value {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a1a;
}

.kpi-small {
  font-size: 18px;
}

.kpi-success .kpi-value {
  color: #67c23a;
}

.kpi-warning .kpi-value {
  color: #e6a23c;
}

.section-card {
  margin-bottom: 20px;
  border-radius: 12px;
}

.section-card :deep(.el-card__header) {
  font-weight: 600;
  font-size: 15px;
}

.warning-card {
  border-left: 4px solid #e6a23c;
}

.issue-item {
  padding: 8px 0;
  color: #e6a23c;
  font-size: 14px;
}

.issue-actions {
  margin-top: 16px;
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
