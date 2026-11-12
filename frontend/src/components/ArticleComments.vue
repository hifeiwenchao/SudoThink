<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { commentsApi, type PublicComment } from '@/api/comments'
import { readCommenter, saveCommenter, validateComment, validateCommenter, type Commenter } from '@/utils/commenter'

const props = defineProps<{ articleId: number }>()
const remembered = readCommenter()
const nickname = ref(remembered.nickname)
const email = ref(remembered.email)
const savedIdentity = ref<Commenter | null>(validateCommenter(remembered) ? null : remembered)
const editingIdentity = ref(!savedIdentity.value)
const nicknameInput = ref<HTMLInputElement | null>(null)
const identityButton = ref<HTMLButtonElement | null>(null)
const content = ref('')
const comments = ref<PublicComment[]>([])
const total = ref(0)
const page = ref(1)
const loading = ref(false)
const loadError = ref(false)
const submitting = ref(false)
const submitError = ref('')
const submitted = ref(false)
const contentLength = computed(() => Array.from(content.value.trim()).length)
const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 10)))
let listRequest: AbortController | undefined
let submitRequest: AbortController | undefined
let requestVersion = 0
let disposed = false

async function toggleIdentity() {
  if (submitting.value || !savedIdentity.value) return
  submitError.value = ''
  if (editingIdentity.value) {
    nickname.value = savedIdentity.value.nickname
    email.value = savedIdentity.value.email
    editingIdentity.value = false
  } else {
    editingIdentity.value = true
  }
  await nextTick()
  if (disposed) return
  if (editingIdentity.value) nicknameInput.value?.focus()
  else identityButton.value?.focus()
}

async function load(targetPage = page.value) {
  listRequest?.abort()
  listRequest = new AbortController()
  const version = ++requestVersion
  page.value = targetPage
  loading.value = true
  loadError.value = false
  try {
    const result = await commentsApi.list(props.articleId, targetPage, 10, listRequest.signal)
    if (version !== requestVersion || disposed) return
    comments.value = result.items
    total.value = result.total
    page.value = result.page
  } catch {
    if (version === requestVersion && !disposed) loadError.value = true
  } finally {
    if (version === requestVersion && !disposed) loading.value = false
  }
}

async function submit() {
  if (submitting.value) return
  submitted.value = false
  const identity = { nickname: nickname.value.trim(), email: email.value.trim() }
  const text = content.value.trim()
  submitError.value = validateComment({ ...identity, content: text }) || ''
  if (submitError.value) return
  submitting.value = true
  submitRequest = new AbortController()
  try {
    await commentsApi.create(props.articleId, {
      nickname: identity.nickname,
      ...(identity.email ? { email: identity.email } : {}),
      content: text,
    }, submitRequest.signal)
    if (disposed) return
    saveCommenter(identity)
    savedIdentity.value = identity
    editingIdentity.value = false
    nickname.value = identity.nickname
    email.value = identity.email
    content.value = ''
    submitted.value = true
  } catch (error: unknown) {
    if (disposed) return
    const failure = error as { response?: { data?: { message?: string } }; message?: string }
    submitError.value = failure.response?.data?.message || failure.message || '提交失败，请稍后重试，评论内容已保留'
  } finally {
    if (!disposed) submitting.value = false
  }
}

function dateLabel(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

watch(() => props.articleId, () => {
  comments.value = []
  total.value = 0
  void load(1)
}, { immediate: true })

onBeforeUnmount(() => {
  disposed = true
  requestVersion++
  listRequest?.abort()
  submitRequest?.abort()
})
</script>

<template>
  <section class="article-comments" :aria-labelledby="`comments-title-${articleId}`">
    <header class="comments-header">
      <h2 :id="`comments-title-${articleId}`">评论 <span>{{ total }}</span></h2>
      <span class="comments-eyebrow">LEAVE A THOUGHT</span>
    </header>

    <form class="comment-form" novalidate :aria-busy="submitting" @submit.prevent="submit">
      <div v-if="savedIdentity" class="comment-identity-summary">
        <p>以 <strong>{{ savedIdentity.nickname }}</strong> 评论</p>
        <button
          ref="identityButton"
          type="button"
          :data-action="editingIdentity ? 'cancel-identity' : 'edit-identity'"
          :aria-expanded="editingIdentity"
          :aria-controls="`comment-identity-${articleId}`"
          :disabled="submitting"
          @click="toggleIdentity"
        >{{ editingIdentity ? '取消修改' : '修改信息' }}</button>
      </div>
      <div v-if="editingIdentity" :id="`comment-identity-${articleId}`" class="comment-identity">
        <div class="comment-field">
          <label :for="`comment-nickname-${articleId}`">昵称 <span aria-hidden="true">*</span></label>
          <input :id="`comment-nickname-${articleId}`" ref="nicknameInput" v-model="nickname" name="nickname" autocomplete="nickname" required maxlength="64" :disabled="submitting" :aria-describedby="`comment-help-${articleId}`" placeholder="中文、英文、数字或下划线" />
        </div>
        <div class="comment-field">
          <label :for="`comment-email-${articleId}`">邮箱 <small>选填，不公开</small></label>
          <input :id="`comment-email-${articleId}`" v-model="email" name="email" type="email" autocomplete="email" maxlength="254" :disabled="submitting" placeholder="reader@example.com" />
        </div>
      </div>
      <div class="comment-field">
        <label :for="`comment-content-${articleId}`">评论内容 <span aria-hidden="true">*</span></label>
        <textarea :id="`comment-content-${articleId}`" v-model="content" name="content" required rows="5" maxlength="2000" :disabled="submitting" :aria-describedby="`comment-help-${articleId}`" placeholder="分享你的想法，让交流继续。" />
      </div>
      <p :id="`comment-help-${articleId}`" class="comment-help"><template v-if="editingIdentity">昵称 1–32 字，邮箱选填，提交成功后会记住并收起。昵称仅限中文、英文、数字或下划线。</template>正文 1–1000 字，审核后展示。邮箱不公开，IP 仅用于管理和归属地展示。</p>
      <div class="comment-form-actions">
        <span class="comment-count" :class="{ exceeded: contentLength > 1000 }">{{ contentLength }} / 1000</span>
        <button type="submit" class="comment-submit" :disabled="submitting">{{ submitting ? '正在提交…' : '提交评论' }}</button>
      </div>
      <p v-if="submitError" class="comment-message error" role="alert">{{ submitError }}</p>
      <p v-if="submitted" class="comment-message success" role="status">评论已提交，等待审核后展示。感谢你的分享。</p>
    </form>

    <div class="comment-list" :aria-busy="loading" aria-live="polite">
      <p v-if="loading" class="comments-empty" role="status">正在加载评论…</p>
      <div v-else-if="loadError" class="comment-load-error" role="alert">
        <span>评论加载失败，请稍后重试。</span>
        <button type="button" data-action="retry" @click="load()">重新加载</button>
      </div>
      <template v-else>
        <p v-if="!comments.length" class="comments-empty">还没有公开评论，来分享你的想法吧。</p>
        <article v-for="comment in comments" :key="comment.id" class="comment-item">
          <header class="comment-meta">
            <span class="comment-nickname">{{ comment.nickname }}</span>
            <span v-if="comment.location" class="comment-location">IP 属地：{{ comment.location }}</span>
            <time :datetime="comment.created_at">{{ dateLabel(comment.created_at) }}</time>
          </header>
          <p class="comment-content">{{ comment.content }}</p>
        </article>
        <nav v-if="pageCount > 1" class="comment-pagination" aria-label="评论分页">
          <button type="button" aria-label="上一页评论" :disabled="page <= 1" @click="load(page - 1)">上一页</button>
          <span>{{ page }} / {{ pageCount }}</span>
          <button type="button" aria-label="下一页评论" :disabled="page >= pageCount" @click="load(page + 1)">下一页</button>
        </nav>
      </template>
    </div>
  </section>
</template>

<style scoped>
.article-comments { margin-top: 48px; padding-top: 30px; border-top: 1px solid var(--blog-border); color: var(--blog-text); }
.comments-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 24px; }
.comments-header h2 { display: flex; align-items: baseline; gap: 10px; margin: 0; font-size: 21px; line-height: 1.5; }
.comments-header h2 span { color: var(--blog-accent); font: 13px var(--blog-mono); }
.comments-eyebrow { color: var(--blog-muted); font: 9px var(--blog-mono); letter-spacing: .08em; }
.comment-form { padding: 22px; border: 1px solid var(--blog-border); border-radius: 9px; background: var(--blog-surface-alt); }
.comment-identity { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }
.comment-identity-summary { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 16px; margin-bottom: 18px; color: var(--blog-muted); font-size: 12px; }
.comment-identity-summary p { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.comment-identity-summary strong { color: var(--blog-text); font-weight: 600; }
.comment-identity-summary button { padding: 4px 0; border: 0; background: transparent; color: var(--blog-accent); font: inherit; cursor: pointer; }
.comment-identity-summary button:hover:not(:disabled) { text-decoration: underline; text-underline-offset: 3px; }
.comment-identity-summary button:disabled { cursor: default; opacity: .45; }
.comment-field { display: flex; flex-direction: column; gap: 9px; min-width: 0; }
.comment-field label { color: var(--blog-text); font-size: 12px; font-weight: 600; }
.comment-field label > span { color: var(--blog-accent); }
.comment-field label small { margin-left: 6px; color: var(--blog-muted); font-size: 11px; font-weight: 400; }
.comment-field input, .comment-field textarea { box-sizing: border-box; width: 100%; min-width: 0; padding: 11px 12px; border: 1px solid var(--blog-border); border-radius: 6px; background: var(--blog-surface); color: var(--blog-text); font: inherit; font-size: 13px; line-height: 1.7; }
.comment-field textarea { min-height: 132px; resize: vertical; }
.comment-field input::placeholder, .comment-field textarea::placeholder { color: var(--blog-muted); opacity: .8; }
.comment-field input:focus, .comment-field textarea:focus { border-color: var(--blog-accent); outline: 2px solid var(--blog-accent-soft); }
.comment-field input:disabled, .comment-field textarea:disabled { opacity: .65; }
.comment-help { margin: 12px 0 0; color: var(--blog-muted); font-size: 11px; line-height: 1.9; }
.comment-form-actions { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 17px; }
.comment-count { color: var(--blog-muted); font: 11px var(--blog-mono); }
.comment-count.exceeded, .comment-message.error { color: var(--el-color-danger); }
.comment-submit, .comment-pagination button, .comment-load-error button { padding: 9px 16px; border: 1px solid var(--blog-border); border-radius: 6px; background: var(--blog-surface); color: var(--blog-accent); font: inherit; font-size: 12px; cursor: pointer; }
.comment-submit { border-color: var(--blog-accent); font-weight: 600; }
.comment-submit:hover, .comment-pagination button:hover:not(:disabled), .comment-load-error button:hover { background: var(--blog-accent-soft); border-color: var(--blog-accent); }
.comment-submit:disabled, .comment-pagination button:disabled { cursor: default; opacity: .45; }
.article-comments button:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 3px; }
.comment-message { margin: 16px 0 0; font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; }
.comment-message.success { color: var(--blog-accent); }
.comment-list { margin-top: 22px; }
.comments-empty { margin: 0; padding: 30px 0; color: var(--blog-muted); text-align: center; font-size: 13px; line-height: 1.8; }
.comment-item { padding: 24px 0; border-bottom: 1px solid var(--blog-border); }
.comment-meta { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px 14px; color: var(--blog-muted); font-size: 11px; }
.comment-nickname { color: var(--blog-text); font-size: 13px; font-weight: 600; overflow-wrap: anywhere; }
.comment-meta time { margin-left: auto; font: 10px var(--blog-mono); }
.comment-content { margin: 12px 0 0; color: var(--blog-text); font-size: 14px; line-height: 1.9; white-space: pre-wrap; overflow-wrap: anywhere; }
.comment-load-error { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 14px; padding: 28px 0; color: var(--blog-muted); font-size: 13px; }
.comment-pagination { display: flex; align-items: center; justify-content: center; gap: 18px; margin-top: 24px; }
.comment-pagination > span { color: var(--blog-muted); font: 11px var(--blog-mono); }
@media (max-width: 640px) {
  .article-comments { margin-top: 36px; padding-top: 24px; }
  .comment-form { padding: 18px; }
  .comment-identity { grid-template-columns: 1fr; gap: 16px; }
  .comments-eyebrow { font-size: 8px; }
  .comment-meta time { flex-basis: 100%; margin-left: 0; }
}
</style>
