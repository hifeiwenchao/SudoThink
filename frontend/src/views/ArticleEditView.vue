<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { articleApi } from '@/api/article'

const router = useRouter()
const submitting = ref(false)

const form = reactive({
  title: '',
  summary: '',
  content: '',
  cover: '',
  is_published: true,
})

async function submit() {
  if (!form.title.trim() || !form.content.trim()) {
    ElMessage.warning('标题和正文不能为空')
    return
  }
  submitting.value = true
  try {
    const data = await articleApi.create({ ...form })
    ElMessage.success('发布成功')
    router.replace(`/articles/${data.id}`)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="edit">
    <h2>写文章</h2>
    <el-form :model="form" label-width="80px">
      <el-form-item label="标题">
        <el-input v-model="form.title" placeholder="请输入标题" />
      </el-form-item>
      <el-form-item label="摘要">
        <el-input v-model="form.summary" placeholder="可选" />
      </el-form-item>
      <el-form-item label="封面图">
        <el-input v-model="form.cover" placeholder="可选 URL" />
      </el-form-item>
      <el-form-item label="正文">
        <el-input
          v-model="form.content"
          type="textarea"
          :rows="14"
          placeholder="支持 Markdown"
        />
      </el-form-item>
      <el-form-item label="立即发布">
        <el-switch v-model="form.is_published" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">
          发布
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<style scoped>
.edit {
  max-width: 800px;
  margin: 0 auto;
  background: #fff;
  padding: 24px;
  border-radius: 8px;
}
</style>
