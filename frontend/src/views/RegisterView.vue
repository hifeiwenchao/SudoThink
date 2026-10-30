<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: '',
  email: '',
  password: '',
  nickname: '',
})

async function submit() {
  if (!form.username || !form.email || !form.password) {
    ElMessage.warning('请填写必填字段')
    return
  }
  loading.value = true
  try {
    await userStore.register(form)
    ElMessage.success('注册成功')
    router.replace('/')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth">
    <h2>注册</h2>
    <el-form :model="form" label-width="80px">
      <el-form-item label="用户名">
        <el-input v-model="form.username" />
      </el-form-item>
      <el-form-item label="邮箱">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input v-model="form.password" type="password" show-password />
      </el-form-item>
      <el-form-item label="昵称">
        <el-input v-model="form.nickname" placeholder="可选" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="loading" @click="submit">注册</el-button>
        <RouterLink to="/login" class="login-link">已有账号？登录</RouterLink>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
.auth {
  max-width: 480px;
  margin: 40px auto;
  background: #fff;
  padding: 24px;
  border-radius: 8px;
}
.login-link {
  margin-left: 12px;
}
</style>
