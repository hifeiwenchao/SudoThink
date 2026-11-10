<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Image from '@tiptap/extension-image'
import Placeholder from '@tiptap/extension-placeholder'
import TextAlign from '@tiptap/extension-text-align'
import { Link, Picture, RefreshLeft, RefreshRight, Minus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { sanitizeArticleHtml, toArticleHtml } from '@/utils/articleContent'
import '@/styles/article.css'

const props = withDefaults(defineProps<{ modelValue: string; disabled?: boolean; ariaLabel?: string }>(), {
  disabled: false,
  ariaLabel: '文章正文',
})
const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const dialog = ref<'link' | 'image' | null>(null)
const media = reactive({ url: '', alt: '' })
const dialogError = ref('')

const editor = useEditor({
  content: toArticleHtml(props.modelValue),
  editable: !props.disabled,
  extensions: [
    StarterKit.configure({
      heading: { levels: [2, 3, 4] },
      link: { openOnClick: false, defaultProtocol: 'https', HTMLAttributes: { rel: 'noopener noreferrer', target: '_blank' } },
    }),
    Image.configure({ allowBase64: false }),
    Placeholder.configure({ placeholder: '写下你的想法，或者粘贴已有内容…' }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
  ],
  editorProps: {
    attributes: { class: 'article-prose editor-document', role: 'textbox', 'aria-label': props.ariaLabel, 'aria-multiline': 'true' },
    transformPastedHTML: sanitizeArticleHtml,
    handlePaste: (_view, event) => {
      if (!event.clipboardData?.files.length) return false
      ElMessage.info('请使用工具栏的“插入图片”，填写图片地址')
      return true
    },
    handleDrop: (_view, event) => {
      if (!event.dataTransfer?.files.length) return false
      ElMessage.info('请使用图片地址插入图片')
      return true
    },
  },
  onUpdate: ({ editor: instance }) => emit('update:modelValue', instance.isEmpty ? '' : instance.getHTML()),
})

watch(() => props.modelValue, (value) => {
  if (!editor.value) return
  const html = toArticleHtml(value)
  if (editor.value.getHTML() !== html) editor.value.commands.setContent(html, { emitUpdate: false })
})
watch(() => props.disabled, (disabled) => editor.value?.setEditable(!disabled))

const blockType = computed(() => {
  for (const level of [2, 3, 4]) {
    if (editor.value?.isActive('heading', { level })) return `h${level}`
  }
  return 'paragraph'
})

function setBlock(value: string) {
  const chain = editor.value?.chain().focus()
  if (value === 'paragraph') chain?.setParagraph().run()
  else chain?.toggleHeading({ level: Number(value.slice(1)) as 2 | 3 | 4 }).run()
}

function openDialog(type: 'link' | 'image') {
  media.url = type === 'link' ? (editor.value?.getAttributes('link').href || '') : ''
  media.alt = ''
  dialogError.value = ''
  dialog.value = type
}

function insertMedia() {
  if (!dialog.value || props.disabled) return
  const url = media.url.trim()
  try {
    const parsed = new URL(url)
    const protocols = dialog.value === 'link' ? ['https:', 'http:', 'mailto:'] : ['https:', 'http:']
    if (!protocols.includes(parsed.protocol)) throw new Error('invalid protocol')
  } catch {
    dialogError.value = dialog.value === 'image' ? '请填写完整的 HTTP 或 HTTPS 图片地址' : '请填写完整的 HTTP、HTTPS 或 mailto 链接'
    return
  }
  if (dialog.value === 'link') {
    const chain = editor.value?.chain().focus().extendMarkRange('link')
    if (editor.value?.state.selection.empty && !editor.value.isActive('link')) {
      chain?.insertContent({ type: 'text', text: url, marks: [{ type: 'link', attrs: { href: url } }] }).run()
    } else {
      chain?.setLink({ href: url }).run()
    }
  } else {
    editor.value?.chain().focus().setImage({ src: url, alt: media.alt.trim() }).run()
  }
  dialog.value = null
}

function removeLink() {
  editor.value?.chain().focus().extendMarkRange('link').unsetLink().run()
  dialog.value = null
}
</script>

<template>
  <div class="rich-editor" :class="{ 'is-disabled': disabled }">
    <div v-if="editor" class="editor-toolbar" role="toolbar" aria-label="正文格式工具栏" :aria-disabled="disabled">
      <el-select :model-value="blockType" class="block-select" size="small" aria-label="段落样式" :disabled="disabled" @change="setBlock">
        <el-option label="正文" value="paragraph" />
        <el-option label="标题 2" value="h2" />
        <el-option label="标题 3" value="h3" />
        <el-option label="标题 4" value="h4" />
      </el-select>
      <span class="toolbar-divider" />
      <div class="tool-group">
        <button type="button" class="tool-button bold" title="加粗（⌘ / Ctrl + B）" aria-label="加粗" :aria-pressed="editor.isActive('bold')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleBold().run()">B</button>
        <button type="button" class="tool-button italic" title="斜体（⌘ / Ctrl + I）" aria-label="斜体" :aria-pressed="editor.isActive('italic')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleItalic().run()">I</button>
        <button type="button" class="tool-button underline" title="下划线" aria-label="下划线" :aria-pressed="editor.isActive('underline')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleUnderline().run()">U</button>
        <button type="button" class="tool-button strike" title="删除线" aria-label="删除线" :aria-pressed="editor.isActive('strike')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleStrike().run()">S</button>
      </div>
      <span class="toolbar-divider" />
      <div class="tool-group">
        <button type="button" class="tool-button list-button" title="无序列表" aria-label="无序列表" :aria-pressed="editor.isActive('bulletList')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleBulletList().run()">☷</button>
        <button type="button" class="tool-button" title="有序列表" aria-label="有序列表" :aria-pressed="editor.isActive('orderedList')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleOrderedList().run()">1.</button>
        <button type="button" class="tool-button quote-button" title="引用" aria-label="引用" :aria-pressed="editor.isActive('blockquote')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleBlockquote().run()">“</button>
        <button type="button" class="tool-button code-button" title="代码块" aria-label="代码块" :aria-pressed="editor.isActive('codeBlock')" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().toggleCodeBlock().run()">&lt;/&gt;</button>
      </div>
      <el-select :model-value="editor.getAttributes('paragraph').textAlign || editor.getAttributes('heading').textAlign || 'left'" class="align-select" size="small" aria-label="文字对齐" :disabled="disabled" @change="(value: string) => editor?.chain().focus().setTextAlign(value).run()">
        <el-option label="左对齐" value="left" />
        <el-option label="居中" value="center" />
        <el-option label="右对齐" value="right" />
      </el-select>
      <span class="toolbar-divider" />
      <div class="tool-group">
        <button type="button" class="tool-button" title="插入链接" aria-label="插入链接" :aria-pressed="editor.isActive('link')" :disabled="disabled" @mousedown.prevent @click="openDialog('link')"><el-icon><Link /></el-icon></button>
        <button type="button" class="tool-button" title="插入图片" aria-label="插入图片" :disabled="disabled" @mousedown.prevent @click="openDialog('image')"><el-icon><Picture /></el-icon></button>
        <button type="button" class="tool-button" title="分割线" aria-label="分割线" :disabled="disabled" @mousedown.prevent @click="editor.chain().focus().setHorizontalRule().run()"><el-icon><Minus /></el-icon></button>
      </div>
      <div class="tool-group history-tools">
        <button type="button" class="tool-button" title="撤销（⌘ / Ctrl + Z）" aria-label="撤销" :disabled="disabled || !editor.can().undo()" @mousedown.prevent @click="editor.chain().focus().undo().run()"><el-icon><RefreshLeft /></el-icon></button>
        <button type="button" class="tool-button" title="重做" aria-label="重做" :disabled="disabled || !editor.can().redo()" @mousedown.prevent @click="editor.chain().focus().redo().run()"><el-icon><RefreshRight /></el-icon></button>
      </div>
    </div>
    <EditorContent :editor="editor" />
    <div class="editor-help">支持粘贴排版内容，输入 ##、- 或 &gt; 后按空格可快速设置格式。</div>

    <el-dialog :model-value="dialog !== null" :title="dialog === 'image' ? '插入图片' : '插入链接'" width="min(460px, calc(100vw - 32px))" append-to-body @update:model-value="(visible: boolean) => { if (!visible) dialog = null }">
      <el-form label-position="top" @submit.prevent="insertMedia">
        <el-form-item :label="dialog === 'image' ? '图片地址' : '链接地址'" :error="dialogError">
          <el-input v-model="media.url" placeholder="https://" clearable @keydown.enter.prevent="insertMedia" />
        </el-form-item>
        <el-form-item v-if="dialog === 'image'" label="图片描述（选填）">
          <el-input v-model="media.alt" placeholder="简单描述图片内容" @keydown.enter.prevent="insertMedia" />
        </el-form-item>
        <p v-if="dialog === 'image'" class="media-hint">使用可公开访问的图片 URL。暂不支持本地文件上传。</p>
      </el-form>
      <template #footer>
        <el-button v-if="dialog === 'link' && editor?.isActive('link')" text type="danger" @click="removeLink">移除链接</el-button>
        <el-button @click="dialog = null">取消</el-button>
        <el-button type="primary" @click="insertMedia">{{ dialog === 'link' && editor?.isActive('link') ? '更新链接' : '插入' }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.rich-editor { background: var(--app-surface); }
.editor-toolbar { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; padding: 10px 20px; background: var(--app-surface-muted); border-top: 1px solid var(--el-border-color-lighter); border-bottom: 1px solid var(--el-border-color-lighter); }
.block-select { width: 94px; }
.align-select { width: 86px; }
.block-select :deep(.el-select__wrapper), .align-select :deep(.el-select__wrapper) { box-shadow: none; background: transparent; }
.block-select :deep(.el-select__wrapper.is-focused), .align-select :deep(.el-select__wrapper.is-focused) { outline: 2px solid var(--el-color-primary); outline-offset: -2px; }
.toolbar-divider { height: 17px; width: 1px; background: var(--el-border-color); margin: 0 3px; }
.tool-group { display: flex; align-items: center; gap: 2px; }
.tool-button { display: inline-flex; align-items: center; justify-content: center; width: 29px; height: 30px; padding: 0; background: transparent; border: 0; border-radius: 5px; color: var(--el-text-color-regular); cursor: pointer; font: inherit; font-size: 15px; transition: background .15s, color .15s; }
.tool-button:hover:not(:disabled) { background: var(--el-fill-color); color: var(--el-text-color-primary); }
.tool-button[aria-pressed='true'] { color: var(--el-color-primary); background: var(--el-color-primary-light-9); }
.tool-button[aria-pressed='true']:hover:not(:disabled) { color: var(--el-color-primary); background: var(--el-color-primary-light-8); }
.tool-button:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 2px; }
.tool-button:disabled { cursor: not-allowed; color: var(--el-text-color-disabled); }
.bold { font-weight: 800; }
.italic { font-style: italic; font-family: Georgia, serif; font-weight: 600; }
.underline { text-decoration: underline; text-underline-offset: 3px; }
.strike { text-decoration: line-through; }
.quote-button { font-size: 27px; font-family: Georgia, serif; padding-top: 7px; }
.code-button { font-family: monospace; font-size: 12px; }
.list-button { font-size: 24px; }
.history-tools { margin-left: auto; }
:deep(.editor-document) { min-height: 440px; padding: 27px 30px 40px; outline: none; caret-color: var(--el-text-color-primary); }
:deep(.editor-document p.is-editor-empty:first-child::before) { color: var(--el-text-color-placeholder); content: attr(data-placeholder); float: left; height: 0; pointer-events: none; }
:deep(.editor-document .ProseMirror-selectednode) { outline: 2px solid var(--el-color-primary); }
.editor-help { padding: 0 28px 19px; color: var(--el-text-color-secondary); font-size: 11px; line-height: 1.7; }
.is-disabled { opacity: .65; }
.media-hint { font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.7; }
@media (max-width: 640px) {
  .editor-toolbar { padding: 9px 12px; gap: 4px; }
  :deep(.editor-document) { padding: 22px 18px; min-height: 340px; }
  .editor-help { padding: 0 18px 16px; }
  .toolbar-divider { margin: 0 1px; }
}
</style>
