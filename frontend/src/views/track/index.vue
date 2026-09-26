<template>
  <section class="page" data-module="track">
    <header class="page-head">
      <div>
        <h2>轨道电路管理</h2>
        <p class="page-desc">维护轨道电路，围绕设备编号、制式类型、区段长度、分路灵敏度做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记轨道电路</button>
        <button class="btn" type="button" @click="exportRows">导出轨道电路清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>设备状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>异常标识</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <template v-if="column === '设备状态'">
              <span class="status-badge" :class="statusClass(row.status)">{{ row.status }}</span>
            </template>
            <template v-else>{{ displayValue(row, column) }}</template>
          </td>
          <td>
            <span v-if="row.abnormal" class="abnormal-flag">分路不良</span>
            <span v-else class="normal-flag">正常</span>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无轨道电路数据，可先登记轨道电路</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条轨道电路记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detailRow" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>轨道电路详情 · {{ detailRow['设备编号'] }}</h3>
          <button class="btn ghost" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <template v-for="column in columns" :key="column">
            <dt>{{ column }}</dt>
            <dd>
              <template v-if="column === '设备状态'">
                <span class="status-badge" :class="statusClass(detailRow.status)">{{ detailRow.status }}</span>
              </template>
              <template v-else>{{ displayValue(detailRow, column) }}</template>
            </dd>
          </template>
          <dt>异常标识</dt>
          <dd>
            <span v-if="detailRow.abnormal" class="abnormal-flag">分路不良</span>
            <span v-else class="normal-flag">正常</span>
          </dd>
        </dl>
      </div>
    </div>

    <div v-if="testTarget" class="modal-mask" @click.self="closeTestDialog">
      <form class="modal-card" @submit.prevent="submitTest">
        <header class="modal-head">
          <h3>提交测试 · {{ testTarget['设备编号'] }}</h3>
          <button class="btn ghost" type="button" @click="closeTestDialog">取消</button>
        </header>
        <div class="form-stack">
          <label class="filter-item">
            <span>测试结论（判定依据）</span>
            <select v-model="testForm['测试结论']" required>
              <option value="合格">合格 → 运用正常</option>
              <option value="不合格">不合格 → 分路不良</option>
            </select>
          </label>
          <label class="filter-item">
            <span>分路灵敏度（实测值）</span>
            <input v-model="testForm['分路灵敏度']" placeholder="如 0.12Ω" />
          </label>
          <label class="filter-item">
            <span>标准范围</span>
            <input v-model="testForm['标准范围']" placeholder="分路残压 ≤ 0.15Ω" />
          </label>
          <label class="filter-item">
            <span>测试人员</span>
            <input v-model="testForm['测试人员']" placeholder="测试人员" />
          </label>
        </div>
        <footer class="modal-foot">
          <button class="btn primary" type="submit">确认提交</button>
        </footer>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/track'
const columns = ["设备编号", "制式类型", "区段长度", "分路灵敏度", "所属区段", "上次测试日", "下次测试日", "设备状态"]
const statuses = ["待测试", "运用正常", "分路不良", "已更换"]
// 与后端状态机一致：待测试/分路不良可提交测试，分路不良可确认正常，未更换的设备可更换。
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  "待测试": ["提交测试", "更换设备"],
  "运用正常": ["更换设备"],
  "分路不良": ["提交测试", "确认正常", "更换设备"],
  "已更换": [],
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)

// 统计始终按当前列表实时重算，不再写死 0。
const stats = computed(() => {
  const current = rows.value
  return [
    { label: "在运轨道电路", value: current.filter((row) => row.status !== "已更换").length },
    { label: "分路不良区段", value: current.filter((row) => row.status === "分路不良").length },
    { label: "待测试设备", value: current.filter((row) => row.status === "待测试").length },
  ]
})

const detailRow = ref<Row | null>(null)
const testTarget = ref<Row | null>(null)
const testForm = reactive<Record<string, string>>({
  "测试结论": "合格",
  "分路灵敏度": "",
  "标准范围": "分路残压 ≤ 0.15Ω",
  "测试人员": "",
})

function availableActions(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? "")] ?? []
}

function statusClass(status: unknown): string {
  return {
    "待测试": "status-pending",
    "运用正常": "status-normal",
    "分路不良": "status-abnormal",
    "已更换": "status-replaced",
  }[String(status)] ?? "status-pending"
}

function displayValue(row: Row, column: string): string {
  const value = row[column]
  return value === null || value === undefined || value === '' ? '—' : String(value)
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '轨道电路登记入口尚未接入审批流'
}

function openDetail(row: Row) {
  // 直接复用列表里的同一行数据，详情的制式类型等字段天然与列表同步
  detailRow.value = row
}

function closeDetail() {
  detailRow.value = null
}

function closeTestDialog() {
  testTarget.value = null
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  if (action === '提交测试') {
    testTarget.value = row
    testForm['测试结论'] = '合格'
    testForm['分路灵敏度'] = ''
    return
  }
  await postAction(row, { action })
}

async function submitTest() {
  if (!testTarget.value) {
    return
  }
  const target = testTarget.value
  closeTestDialog()
  await postAction(target, { action: '提交测试', ...testForm })
}

async function postAction(row: Row, values: Record<string, unknown>) {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = (await response.json().catch(() => null)) as { ok?: boolean; message?: string } | null
    if (!response.ok || payload?.ok === false) {
      throw new Error(payload?.message || '轨道电路动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '轨道电路操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>)
  if (statusFilter.value) {
    query.set('status', statusFilter.value)
  }
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('轨道电路列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '轨道电路列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  line-height: 18px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.status-pending {
  color: #92600a;
  background: #fdf3d7;
  border-color: #e9c46a;
}
.status-normal {
  color: #177245;
  background: #e3f6ec;
  border-color: #7bd4a4;
}
.status-abnormal {
  color: #b42318;
  background: #fde7e4;
  border-color: #f2a39a;
}
.status-replaced {
  color: #475569;
  background: #eef2f7;
  border-color: #cbd5e1;
}
.abnormal-flag {
  color: #b42318;
  font-weight: 600;
  white-space: nowrap;
}
.normal-flag {
  color: #177245;
  white-space: nowrap;
}
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 20;
}
.modal-card {
  width: 560px;
  max-width: calc(100vw - 32px);
  background: #fff;
  border-radius: 10px;
  padding: 16px 20px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.18);
}
.modal-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.modal-head h3 {
  margin: 0;
  font-size: 16px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 110px 1fr;
  gap: 8px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.form-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.form-stack input,
.form-stack select,
.filter-bar select {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.modal-foot {
  display: flex;
  justify-content: flex-end;
  margin-top: 14px;
}
</style>
