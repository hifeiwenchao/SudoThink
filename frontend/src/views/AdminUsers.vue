<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminUser } from '@/api/admin'
import { readSession } from '@/utils/session'

const list = ref<AdminUser[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loadError = ref(false)
const actingId = ref<number | null>(null)
const currentUserId = readSession().user?.id
let requestId = 0

async function load() {
  const request = ++requestId
  loading.value = true
  loadError.value = false
  try {
    const data = await adminApi.listUsers(page.value)
    if (request !== requestId) return
    list.value = data.items
    total.value = data.total
  } catch {
    if (request === requestId) loadError.value = true
  } finally {
    if (request === requestId) loading.value = false
  }
}

async function handleToggleAdmin(uid: number) {
  if (actingId.value !== null || uid === currentUserId || loading.value) return
  actingId.value = uid
  try {
    await ElMessageBox.confirm('确定切换该用户的管理员权限？', '修改权限', { confirmButtonText: '确认修改', cancelButtonText: '取消', type: 'warning' })
    await adminApi.toggleAdmin(uid)
    ElMessage.success('权限已更新')
    await load()
  } catch { /* Cancellation or shared HTTP error feedback. */ }
  finally { actingId.value = null }
}

async function handleToggleActive(uid: number) {
  if (actingId.value !== null || uid === currentUserId || loading.value) return
  actingId.value = uid
  try {
    await ElMessageBox.confirm('确定修改该用户的启用状态？', '修改账号状态', { confirmButtonText: '确认修改', cancelButtonText: '取消', type: 'warning' })
    await adminApi.toggleActive(uid)
    ElMessage.success('账号状态已更新')
    await load()
  } catch { /* Cancellation or shared HTTP error feedback. */ }
  finally { actingId.value = null }
}

onMounted(load)
onBeforeUnmount(() => { requestId++ })
</script>

<template>
  <div>
    <header class="page-heading"><div><h2>用户管理</h2><p class="admin-description">查看账号资料与状态，权限调整请谨慎操作。</p></div><el-button :loading="loading" :disabled="actingId !== null" @click="load">刷新列表</el-button></header>
    <div v-if="loadError" class="admin-feedback" role="alert"><span>用户列表加载失败，请稍后重试。</span><el-button @click="load">重新加载</el-button></div>
    <div v-else-if="loading && !list.length" class="admin-initial-loading" role="status" aria-label="用户加载中"><p>正在读取用户…</p><el-skeleton :rows="5" animated /></div>
    <el-empty v-else-if="!list.length" description="暂无用户" />
    <el-table v-else :data="list" v-loading="loading" row-key="id" style="width: 100%">
      <el-table-column label="账号" min-width="180"><template #default="{ row }"><strong>{{ row.nickname || row.username }}</strong><p class="user-meta">{{ row.username }} · #{{ row.id }}</p><p class="user-meta">{{ row.email || '未填写邮箱' }}</p></template></el-table-column>
      <el-table-column label="管理员" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_admin ? 'success' : 'info'" size="small">
            {{ row.is_admin ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'danger'" size="small">
            {{ row.is_active ? '正常' : '禁用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="right">
        <template #default="{ row }">
          <span v-if="row.id === currentUserId" class="user-meta">当前账号</span>
          <el-dropdown v-else :disabled="actingId !== null || loading" trigger="click" @command="(command: string) => command === 'role' ? handleToggleAdmin(row.id) : handleToggleActive(row.id)">
            <el-button size="small" :disabled="actingId !== null || loading" :loading="actingId === row.id" :aria-label="`用户 ${row.username} 的更多操作`">更多</el-button>
            <template #dropdown><el-dropdown-menu><el-dropdown-item command="role">{{ row.is_admin ? '取消管理员' : '设为管理员' }}</el-dropdown-item><el-dropdown-item command="active" divided>{{ row.is_active ? '禁用账号' : '启用账号' }}</el-dropdown-item></el-dropdown-menu></template>
          </el-dropdown>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-if="total > 10"
      v-model:current-page="page"
      :page-size="10"
      :total="total"
      layout="prev, pager, next"
      class="pagination"
      @current-change="load"
    />
  </div>
</template>

<style scoped>
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.page-heading h2 { margin: 0; }
.user-meta { font-size: 12px; line-height: 1.7; margin: 4px 0 0; color: var(--el-text-color-secondary); overflow-wrap: anywhere; }
.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
