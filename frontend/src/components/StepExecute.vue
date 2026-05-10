<template>
  <div class="step-execute">
    <!-- Summary Cards -->
    <div class="summary-row">
      <div class="summary-card" v-for="(item, idx) in summaryItems" :key="idx" :class="item.status">
        <el-icon :size="28"><component :is="item.icon" /></el-icon>
        <div class="summary-label">{{ item.label }}</div>
        <div class="summary-value">{{ item.value }}</div>
      </div>
    </div>

    <!-- Execution Options -->
    <el-card class="option-card">
      <template #header>
        <span>执行选项</span>
      </template>

      <div class="option-list">
        <!-- Save Draft -->
        <div class="option-item">
          <el-checkbox v-model="checklist.saveDraft" />
          <div class="option-info">
            <div class="option-title">保存到 DataWorks 草稿</div>
            <div class="option-desc">将修改后的 SQL 保存到 DataWorks</div>
          </div>
        </div>

        <!-- Submit Code -->
        <div class="option-item">
          <el-checkbox v-model="checklist.submitCode" />
          <div class="option-info">
            <div class="option-title">提交代码到仓库</div>
            <div class="option-desc">将修改后的代码提交到 DataWorks 代码仓库（推荐）</div>
          </div>
        </div>

        <!-- ALTER TABLE -->
        <div class="option-item">
          <el-checkbox v-model="checklist.alterTable" />
          <div class="option-info">
            <div class="option-title">执行 ALTER TABLE</div>
            <div class="option-desc">添加新列到目标表</div>
          </div>
        </div>
        <div v-if="checklist.alterTable" class="sql-preview">
          <pre class="sql-block">{{ alterTableSql }}</pre>
        </div>

        <!-- Backfill -->
        <div class="option-item" @click="checklist.backfill = !checklist.backfill">
          <el-checkbox v-model="checklist.backfill" @click.stop />
          <div class="option-info">
            <div class="option-title">历史数据回刷</div>
            <div class="option-desc">回填历史分区的数据</div>
          </div>
        </div>
        <div v-if="checklist.backfill" class="backfill-detail" @click.stop>
          <div class="backfill-controls">
            <el-date-picker
              v-model="backfillRange"
              type="daterange"
              range-separator="至"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              value-format="YYYY-MM-DD"
              size="large"
              style="width: 380px;"
            />
            <el-button type="primary" @click.stop="previewBackfill" :loading="backfillLoading" style="margin-left: 12px;">
              预览 SQL
            </el-button>
          </div>
          <div v-if="backfillSql" class="backfill-preview">
            <pre class="sql-block">{{ backfillSql }}</pre>
            <el-alert type="info" :closable="false" style="margin-top: 8px;">
              预计影响 {{ backfillPartitions }} 个分区
            </el-alert>
          </div>
        </div>

        <!-- Sync BI -->
        <div class="option-item">
          <el-checkbox v-model="checklist.syncBI" />
          <div class="option-info">
            <div class="option-title">同步 BI 平台</div>
            <div class="option-desc">同步维度到 BI 筛选器</div>
          </div>
        </div>

        <!-- Downstream Filter (only for cube/lateral_view) -->
        <div v-if="showDownstream" class="option-item downstream-option">
          <el-checkbox v-model="checklist.downstreamFilter" />
          <div class="option-info">
            <div class="option-title">处理下游节点过滤</div>
            <div class="option-desc">
              本表使用 {{ expansionTypeLabel }} 展开，下游节点需要补充过滤条件
            </div>
          </div>
        </div>
        <!-- Downstream nodes table -->
        <div v-if="checklist.downstreamFilter && downstreamNodes.length > 0" class="downstream-detail">
          <el-alert type="warning" :closable="false" style="margin-bottom: 12px;">
            <template #title>下游节点需要处理</template>
            <div>由于本表新增了 {{ props.config.dimensionName }} 列并生成了 'ALL' 汇总行，下游节点查询时需要过滤 ALL 行。</div>
          </el-alert>
          <el-table :data="downstreamNodes" size="small" border>
            <el-table-column prop="node_name" label="节点名" min-width="200" />
            <el-table-column prop="project_env" label="环境" width="80" />
            <el-table-column label="操作" width="120">
              <template #default="scope">
                <el-button
                  type="primary"
                  size="small"
                  :loading="downstreamProcessing === scope.row.node_id"
                  @click="addDownstreamFilter(scope.row)">
                  <span v-if="downstreamProcessing === scope.row.node_id">处理中...</span>
                  <span v-else>补过滤</span>
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </div>
    </el-card>

    <!-- Actions -->
    <div class="step-actions">
      <el-button @click="$emit('prev')">上一步</el-button>
      <el-button type="primary" @click="execute" :loading="executing">
        确认执行
        <el-icon class="btn-icon"><ArrowRight /></el-icon>
      </el-button>
    </div>

    <!-- Downstream Filter Diff Dialog -->
    <el-dialog
      v-model="downstreamDiffVisible"
      title="下游节点过滤条件修改"
      width="900px"
      :close-on-click-modal="false"
    >
      <div v-if="downstreamDiffData.nodeName">
        <el-alert type="info" :closable="false" style="margin-bottom: 12px;">
          <template #title>节点: {{ downstreamDiffData.nodeName }}</template>
          已向该节点 SQL 添加过滤条件：{{ props.config.dimensionName }} <> 'ALL'
        </el-alert>
        
        <div class="diff-title">修改对比</div>
        <div class="diff-container">
          <div v-for="(line, idx) in downstreamDiffData.diffLines" :key="idx" 
               :class="['diff-line', line.type]">
            <span class="diff-line-num">{{ line.line_num }}</span>
            <span class="diff-line-content">{{ line.content }}</span>
          </div>
        </div>

        <el-divider />
        
        <div class="diff-sections">
          <div class="diff-section">
            <div class="diff-section-title">修改前</div>
            <pre class="diff-section-code">{{ downstreamDiffData.originalSql }}</pre>
          </div>
          <div class="diff-section">
            <div class="diff-section-title">修改后</div>
            <pre class="diff-section-code">{{ downstreamDiffData.modifiedSql }}</pre>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Document, Grid, Calendar, TrendCharts, ArrowRight } from '@element-plus/icons-vue'
import api from '../api/index.js'

const props = defineProps(['config', 'analysis', 'modifyResult'])
const emit = defineEmits(['prev', 'next'])

const checklist = reactive({
  sqlConfirmed: true,
  saveDraft: true,
  submitCode: true,
  alterTable: false,
  backfill: false,
  syncBI: false,
  downstreamFilter: false,
})

const backfillRange = ref([])
const backfillSql = ref('')
const backfillPartitions = ref(0)
const backfillLoading = ref(false)
const executing = ref(false)
const downstreamProcessing = ref(null)
const downstreamDiffVisible = ref(false)
const downstreamDiffData = ref({
  nodeName: '',
  originalSql: '',
  modifiedSql: '',
  diffLines: [],
})

const expansionTypeLabel = computed(() => {
  const map = { cube: 'GROUP BY CUBE', lateral_view: 'LATERAL VIEW EXPLODE', group_by: '普通 GROUP BY' }
  return map[props.analysis?.expansion_type] || props.analysis?.expansion_type
})

const downstreamNodes = computed(() => props.analysis?.downstream_nodes || [])

const showDownstream = computed(() => {
  const expansion = props.analysis?.expansion_type
  return downstreamNodes.value.length > 0 && ['cube', 'lateral_view'].includes(expansion)
})

const summaryItems = computed(() => [
  { label: '项目', value: props.config.projectId, icon: Grid, status: 'info' },
  { label: '目标表', value: props.config.tableName, icon: Document, status: 'info' },
  { label: '新增维度', value: props.config.dimensionName, icon: TrendCharts, status: 'primary' },
  { label: '维度展开', value: props.analysis?.expansion_type || 'unknown', icon: Calendar, status: 'info' },
])

const alterTableSql = computed(() => {
  const dim = props.config.dimensionName
  const cn = props.config.dimensionChineseName
  const comment = cn ? ` COMMENT '${cn}'` : ''
  return `ALTER TABLE ${props.config.tableName} ADD COLUMNS (${dim} STRING${comment});`
})

async function previewBackfill() {
  if (!backfillRange.value || backfillRange.value.length < 2) {
    ElMessage.warning('请选择回刷日期范围')
    return
  }
  backfillLoading.value = true
  try {
    const res = await api.generateBackfill({
      project_id: props.config.projectId,
      table_name: props.config.tableName,
      dimension_name: props.config.dimensionName,
      start_dt: backfillRange.value[0],
      end_dt: backfillRange.value[1],
    })
    backfillSql.value = res.sql
    backfillPartitions.value = res.estimated_partitions
  } catch (e) {
    ElMessage.error('生成回刷 SQL 失败: ' + e.message)
  } finally {
    backfillLoading.value = false
  }
}

async function addDownstreamFilter(node) {
  console.log('addDownstreamFilter called', node)
  if (downstreamProcessing.value === node.node_id) {
    console.log('Already processing this node')
    return
  }
  downstreamProcessing.value = node.node_id
  try {
    const res = await api.modifyDownstreamFilter({
      project_id: props.config.projectId,
      node_id: node.node_id,
      dimension_name: props.config.dimensionName,
    })
    if (res.success) {
      downstreamDiffData.value = {
        nodeName: node.node_name,
        originalSql: res.original_sql || '',
        modifiedSql: res.modified_sql || '',
        diffLines: res.diff_lines || [],
      }
      downstreamDiffVisible.value = true
      ElMessage.success(`已向 ${node.node_name} 添加过滤条件`)
    } else {
      ElMessage.error('添加过滤条件失败: ' + res.message)
    }
  } catch (e) {
    ElMessage.error('添加过滤条件失败: ' + e.message)
  } finally {
    downstreamProcessing.value = null
  }
}

async function execute() {
  executing.value = true
  const results = {
    saveDraft: false,
    submitCode: false,
    alterTable: false,
    backfill: false,
    syncBI: false,
    downstreamFilter: false,
    errors: []
  }

  try {
    // 1. Save Draft
    if (checklist.saveDraft) {
      try {
        const res = await api.saveDraft({
          project_id: props.config.projectId,
          file_id: props.modifyResult?.file_id,
          node_id: props.modifyResult?.node_id,
          sql_content: props.modifyResult?.modified_sql || '',
        })
        if (res.success) {
          results.saveDraft = true
          ElMessage.success('保存草稿成功')
        } else {
          results.errors.push('保存草稿失败: ' + res.message)
          ElMessage.error('保存草稿失败: ' + res.message)
        }
      } catch (e) {
        results.errors.push('保存草稿异常: ' + e.message)
        ElMessage.error('保存草稿异常: ' + e.message)
      }
    }

    // 2. Submit Code to DataWorks repository
    if (checklist.submitCode) {
      try {
        const res = await api.submitFile({
          project_id: props.config.projectId,
          file_id: props.modifyResult?.file_id,
          comment: `加维度: ${props.config.dimensionName} (${props.config.dimensionChineseName})`,
        })
        if (res.success) {
          results.submitCode = true
          ElMessage.success('代码提交成功')
        } else {
          results.errors.push('代码提交失败: ' + res.message)
          ElMessage.error('代码提交失败: ' + res.message)
        }
      } catch (e) {
        results.errors.push('代码提交异常: ' + e.message)
        ElMessage.error('代码提交异常: ' + e.message)
      }
    }

    // 3. ALTER TABLE
    if (checklist.alterTable) {
      try {
        const res = await api.alterTable({
          project_id: props.config.projectId,
          table_name: props.config.tableName,
          dimension_name: props.config.dimensionName,
          dimension_chinese_name: props.config.dimensionChineseName,
        })
        if (res.success) {
          results.alterTable = true
          ElMessage.success('ALTER TABLE 执行成功')
        } else {
          results.errors.push('ALTER TABLE 失败: ' + res.message)
          ElMessage.error('ALTER TABLE 失败: ' + res.message)
        }
      } catch (e) {
        results.errors.push('ALTER TABLE 异常: ' + e.message)
        ElMessage.error('ALTER TABLE 异常: ' + e.message)
      }
    }

    // 3. Backfill
    if (checklist.backfill) {
      // Auto-generate backfill SQL if not yet previewed
      if (!backfillSql.value && backfillRange.value && backfillRange.value.length >= 2) {
        try {
          const genRes = await api.generateBackfill({
            project_id: props.config.projectId,
            table_name: props.config.tableName,
            dimension_name: props.config.dimensionName,
            start_dt: backfillRange.value[0],
            end_dt: backfillRange.value[1],
          })
          backfillSql.value = genRes.sql
          backfillPartitions.value = genRes.estimated_partitions
        } catch (e) {
          results.errors.push('生成回刷 SQL 失败: ' + e.message)
          ElMessage.error('生成回刷 SQL 失败: ' + e.message)
        }
      }
      
      if (!backfillSql.value) {
        results.errors.push('回刷 SQL 为空，请先生成预览')
        ElMessage.warning('回刷 SQL 为空，请先生成预览')
      } else {
        try {
          const res = await api.executeBackfill({
            project_id: props.config.projectId,
            table_name: props.config.tableName,
            dimension_name: props.config.dimensionName,
            sql: backfillSql.value,
          })
          if (res.success) {
            results.backfill = true
            ElMessage.success('回刷执行成功')
          } else {
            results.errors.push('回刷失败: ' + res.message)
            ElMessage.error('回刷失败: ' + res.message)
          }
        } catch (e) {
          results.errors.push('回刷异常: ' + e.message)
          ElMessage.error('回刷异常: ' + e.message)
        }
      }
    }

    // 4. Sync BI
    if (checklist.syncBI) {
      try {
        const res = await api.syncBI({
          table_name: props.config.tableName,
          dimension_name: props.config.dimensionName,
          dimension_chinese_name: props.config.dimensionChineseName,
          expansion_type: props.analysis?.expansion_type,
        })
        if (res.success) {
          results.syncBI = true
          ElMessage.success('BI 同步成功')
        } else {
          results.errors.push('BI 同步失败: ' + res.message)
          ElMessage.error('BI 同步失败: ' + res.message)
        }
      } catch (e) {
        results.errors.push('BI 同步异常: ' + e.message)
        ElMessage.error('BI 同步异常: ' + e.message)
      }
    }

    emit('next', results)
  } finally {
    executing.value = false
  }
}
</script>

<style scoped>
.step-execute {
  max-width: 900px;
  margin: 0 auto;
}

.summary-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
}

.summary-card {
  background: #fff;
  border-radius: 12px;
  padding: 20px 16px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
  text-align: center;
}

.summary-card .el-icon {
  color: #409eff;
  margin-bottom: 8px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.summary-value {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
}

.option-card {
  border-radius: 12px;
  margin-bottom: 20px;
}

.option-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.option-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  border-radius: 10px;
  background: #f5f7fa;
  cursor: pointer;
  transition: background 0.2s;
}

.option-item:hover {
  background: #e6f0ff;
}

.option-info {
  flex: 1;
  min-width: 0;
}

.option-title {
  font-size: 15px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 4px;
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
}

.option-desc {
  font-size: 13px;
  color: #909399;
  line-height: 1.4;
  white-space: normal;
  word-break: break-word;
}

/* Downstream option highlight */
.downstream-option {
  border-left: 4px solid #e6a23c;
  background: #fff8f0;
}

.downstream-option:hover {
  background: #fff0e0;
}

/* Downstream detail */
.downstream-detail {
  margin: -8px 0 8px 36px;
  padding: 16px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e4e7ed;
}

/* ALTER TABLE SQL Preview */
.sql-preview {
  margin: -8px 0 8px 36px;
  padding: 12px 16px;
  background: #1e1e1e;
  border-radius: 8px;
}

.sql-preview .sql-block {
  margin: 0;
  padding: 0;
  color: #d4d4d4;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
}

/* Backfill Detail */
.backfill-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: -8px 0 8px 36px;
  padding: 16px;
  background: #fff;
  border-radius: 10px;
  border: 1px solid #e4e7ed;
}

.backfill-controls {
  display: flex;
  align-items: center;
}

.backfill-preview {
  margin-top: 8px;
}

.backfill-preview .sql-block {
  background: #1e1e1e;
  color: #d4d4d4;
  padding: 12px 16px;
  border-radius: 8px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
  margin: 0;
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

/* Downstream Diff Dialog */
.diff-title {
  font-size: 16px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 12px;
}

.diff-container {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 12px 16px;
  font-family: 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.6;
  max-height: 300px;
  overflow-y: auto;
  margin-bottom: 20px;
}

.diff-line {
  display: flex;
  white-space: pre-wrap;
  word-break: break-all;
}

.diff-line .diff-line-num {
  width: 40px;
  flex-shrink: 0;
  color: #6e7681;
  text-align: right;
  padding-right: 12px;
  user-select: none;
}

.diff-line .diff-line-content {
  flex: 1;
}

.diff-line.added {
  background: rgba(35, 197, 94, 0.15);
}

.diff-line.added .diff-line-content {
  color: #3fb950;
}

.diff-line.removed {
  background: rgba(248, 81, 73, 0.15);
}

.diff-line.removed .diff-line-content {
  color: #f85149;
}

.diff-line.unchanged {
  color: #d4d4d4;
}

.diff-sections {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.diff-section-title {
  font-size: 14px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.diff-section-code {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  color: #333;
}
</style>
