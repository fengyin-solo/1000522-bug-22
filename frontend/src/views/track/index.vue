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
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <template v-for="column in columns" :key="column">
            <td v-if="column === '设备状态'">
              <span class="status-tag" :class="badgeClass(String(row[column] ?? ''))">{{ row[column] ?? '—' }}</span>
            </td>
            <td v-else>{{ row[column] ?? '—' }}</td>
          </template>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">详情</button>
            <button
              v-for="action in actions"
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
          <td :colspan="columns.length + 1" class="empty-state">暂无轨道电路数据，可先登记轨道电路</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条轨道电路记录</span>
      <span v-if="infoMessage" class="info-text">{{ infoMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="detail" class="modal-mask" @click.self="closeDetail">
      <div class="modal-card">
        <header class="modal-head">
          <h3>轨道电路详情 · {{ detail['设备编号'] }}</h3>
          <button class="link" type="button" @click="closeDetail">关闭</button>
        </header>
        <dl class="detail-grid">
          <div v-for="column in detailColumns" :key="column" class="detail-item">
            <dt>{{ column }}</dt>
            <dd v-if="column === '设备状态'">
              <span class="status-tag" :class="badgeClass(String(detail[column] ?? ''))">{{ detail[column] ?? '—' }}</span>
            </dd>
            <dd v-else>{{ detail[column] ?? '—' }}</dd>
          </div>
          <div class="detail-item">
            <dt>测试结论</dt>
            <dd>
              <span v-if="detail['测试结论']" class="status-tag" :class="badgeClass(conclusionLabel(String(detail['测试结论'])))">
                {{ detail['测试结论'] }}
              </span>
              <span v-else>—</span>
            </dd>
          </div>
        </dl>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/track'
const columns = ["设备编号", "制式类型", "区段长度", "分路灵敏度", "所属区段", "上次测试日", "下次测试日", "设备状态"]
const detailColumns = columns.slice()
const actions = ["提交测试", "确认正常", "更换设备"]
const filterFields = columns.slice(0, 3)

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const infoMessage = ref('')
const filters = ref<Record<string, string>>({})
const detail = ref<Row | null>(null)

const stats = computed(() => {
  const statusOf = (row: Row) => String(row['设备状态'] ?? row.status ?? '')
  const active = rows.value.filter((row) => ['运用正常', '分路不良'].includes(statusOf(row))).length
  const bad = rows.value.filter((row) => statusOf(row) === '分路不良').length
  const pending = rows.value.filter((row) => statusOf(row) === '待测试').length
  return [
    { label: '在运轨道电路', value: active },
    { label: '分路不良区段', value: bad },
    { label: '待测试设备', value: pending },
  ]
})

function badgeClass(status: string) {
  if (status === '分路不良' || status === '不合格') return 'status-bad'
  if (status === '运用正常' || status === '合格') return 'status-ok'
  if (status === '已更换') return 'status-done'
  return 'status-pending'
}

function conclusionLabel(conclusion: string) {
  // 测试结论（合格/不合格）复用同一套颜色规则
  return conclusion === '不合格' ? '分路不良' : conclusion === '合格' ? '运用正常' : conclusion
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '轨道电路登记入口尚未接入审批流'
}

function closeDetail() {
  detail.value = null
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}`)
    if (!response.ok) {
      throw new Error('轨道电路详情读取失败')
    }
    detail.value = await response.json()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '轨道电路详情读取失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  infoMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    let payload: { ok?: boolean; message?: string } = {}
    try {
      payload = await response.json()
    } catch {
      payload = {}
    }
    // 服务端业务校验结论（ok/message）与页面保持一致：失败时原样展示，不刷新成旧状态
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || '轨道电路动作未生效，请稍后重试')
    }
    infoMessage.value = payload.message || '轨道电路动作已生效'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '轨道电路操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  infoMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
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
