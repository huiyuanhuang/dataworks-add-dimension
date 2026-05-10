<template>
  <div class="app-container">
    <!-- Header -->
    <header class="app-header">
      <div class="header-left">
        <div class="logo">
          <el-icon :size="24" color="#ffffff"><Setting /></el-icon>
        </div>
        <h1>DataWorks 加维度工具</h1>
      </div>
      <div class="header-right">
        <el-tag type="info" effect="plain" size="large">v1.0</el-tag>
      </div>
    </header>

    <!-- Top Tab Navigation -->
    <nav class="tab-nav">
      <div
        v-for="(tab, index) in tabs"
        :key="index"
        :class="['tab-item', { active: currentTab === index }]"
        @click="currentTab = index"
      >
        <span class="tab-number">{{ index + 1 }}</span>
        <span class="tab-title">{{ tab }}</span>
      </div>
    </nav>

    <!-- Main Content -->
    <main class="main-content">
      <!-- Step Config -->
      <StepConfig
        v-if="currentStep === 0"
        :config="config"
        @next="onConfigNext"
      />

      <!-- Step Analyze -->
      <StepAnalyze
        v-else-if="currentStep === 1"
        :config="config"
        :analysis="analysis"
        @prev="currentStep--"
        @next="onAnalyzeNext"
      />

      <!-- Step Modify -->
      <StepModify
        v-else-if="currentStep === 2"
        :config="config"
        :analysis="analysis"
        :modifyResult="modifyResult"
        @prev="currentStep--"
        @next="onModifyNext"
      />

      <!-- Step Execute -->
      <StepExecute
        v-else-if="currentStep === 3"
        :config="config"
        :analysis="analysis"
        :modifyResult="modifyResult"
        @prev="currentStep--"
        @next="onExecuteNext"
      />

      <!-- Step Complete -->
      <StepComplete
        v-else-if="currentStep === 4"
        :config="config"
        :executionResult="executionResult"
        @prev="currentStep--"
      />
    </main>
  </div>
</template>

<script setup>
import { ref } from "vue"
import { ElMessage } from "element-plus"
import { Setting } from "@element-plus/icons-vue"
import StepConfig from "./components/StepConfig.vue"
import StepAnalyze from "./components/StepAnalyze.vue"
import StepModify from "./components/StepModify.vue"
import StepExecute from "./components/StepExecute.vue"
import StepComplete from "./components/StepComplete.vue"
import api from "./api/index.js"

const tabs = ['配置', '分析', '修改', '执行', '完成']
const currentTab = ref(0)
const currentStep = ref(0)

const config = ref({ projectId: "", tableName: "", dimensionName: "", dimensionChineseName: "" })
const analysis = ref(null)
const modifyResult = ref(null)
const executionResult = ref(null)

async function onConfigNext(cfg) {
  config.value = cfg
  currentStep.value = 1
  currentTab.value = 1
  try {
    const result = await api.analyze({
      project_id: cfg.projectId,
      table_name: cfg.tableName,
      dimension_name: cfg.dimensionName,
      dimension_chinese_name: cfg.dimensionChineseName,
    })
    analysis.value = result
    if (!result.error && (!result.issues || result.issues.length === 0)) {
      ElMessage.success("分析通过，无问题")
      const mod = await api.modify({
        project_id: cfg.projectId,
        table_name: cfg.tableName,
        dimension_name: cfg.dimensionName,
        dimension_chinese_name: cfg.dimensionChineseName,
        expansion_type: result.expansion_type,
        file_id: result.file_id,
        node_id: result.node_id,
      })
      modifyResult.value = mod
    }
  } catch (e) {
    ElMessage.error("分析失败: " + e.message)
  }
}

async function onAnalyzeNext(data) {
  currentStep.value = 2
  currentTab.value = 2
  
  // Fetch modify result if not already loaded
  if (!modifyResult.value) {
    try {
      const res = await api.modify({
        project_id: config.value.projectId,
        table_name: config.value.tableName,
        dimension_name: config.value.dimensionName,
        dimension_chinese_name: config.value.dimensionChineseName,
        expansion_type: analysis.value?.expansion_type,
        file_id: analysis.value?.file_id,
        node_id: analysis.value?.node_id,
      })
      modifyResult.value = res
    } catch (e) {
      ElMessage.error("修改失败: " + e.message)
    }
  }
}

async function onModifyNext(data) {
  currentStep.value = 3
  currentTab.value = 3
}

async function onExecuteNext(result) {
  executionResult.value = result
  currentStep.value = 4
  currentTab.value = 4
}
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background: #f0f2f5;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: linear-gradient(135deg, #409eff 0%, #1677ff 100%);
  color: white;
  padding: 0 32px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-left h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.logo {
  width: 40px;
  height: 40px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tab-nav {
  display: flex;
  background: #fff;
  padding: 0 32px;
  border-bottom: 1px solid #e4e7ed;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.04);
}

.tab-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 24px;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.3s ease;
  color: #606266;
  font-size: 15px;
}

.tab-item:hover {
  color: #409eff;
}

.tab-item.active {
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 600;
}

.tab-number {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #e4e7ed;
  color: #606266;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
}

.tab-item.active .tab-number {
  background: #409eff;
  color: #fff;
}

.main-content {
  flex: 1;
  padding: 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}
</style>
