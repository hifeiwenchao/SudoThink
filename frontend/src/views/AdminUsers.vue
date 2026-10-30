<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { adminApi, type AdminUser } from '@/api/admin'

const list = ref<AdminUser[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await adminApi.listUsers(page.value)
    list.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

async function handleToggleAdmin(uid: number) {
  await ElMessageBox.confirm('确定切换该用户的管理员权限？', '提示')
  await adminApi.toggleAdmin(uid)
  ElMessage.success('操作成功')
  load()
}

async function handleToggleActive(uid: number) {
  await adminApi.toggleActive(uid)
  ElMessage.success('操作成功')
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <h2>用户管理</h2>
    <el-table :data="list" v-loading="loading" stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="60" />
      <el-table-column prop="username" label="用户名" />
      <el-table-column prop="email" label="邮箱" />
      <el-table-column prop="nickname" label="昵称" />
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
      <el-table-column label="操作" width="160">
        <template #default="{ row }">
          <el-button
            size="small"
            @click="handleToggleAdmin(row.id)"
            :disabled="row.is_admin"
          >
            取消管理
          </el-button>
          <el-button
            size="small"
            type="warning"
            @click="handleToggleActive(row.id)"
          >
            {{ row.is_active ? '禁用' : '启用' }}
          </el-button>
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
.pagination {
  margin-top: 16px;
  justify-content: center;
}
</style>
