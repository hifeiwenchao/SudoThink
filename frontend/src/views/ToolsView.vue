<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import '@/styles/tools.css'

const route = useRoute()
const tools = [
  { id: 'timestamp', mark: 'TS', name: '时间戳转换', hint: '日期时间 · 秒 / 毫秒', description: '让时间在可读的日期与时间戳之间自由转换。', component: defineAsyncComponent(() => import('@/components/tools/TimestampTool.vue')) },
  { id: 'qrcode', mark: 'QR', name: '二维码生成器', hint: '生成 · 图片识别', description: '把文字变成二维码，也能从图片中读回内容。', component: defineAsyncComponent(() => import('@/components/tools/QrCodeTool.vue')) },
  { id: 'crypto', mark: '{#}', name: '加密解密', hint: '加解密 · 摘要 · 编码', description: '常用的文本加解密、摘要与编码转换。', component: defineAsyncComponent(() => import('@/components/tools/CryptoTool.vue')) },
  { id: 'random', mark: '#', name: '生成随机数', hint: '范围 · 精度 · 去重', description: '定义规则，生成一组符合条件的随机数。', component: defineAsyncComponent(() => import('@/components/tools/RandomTool.vue')) },
  { id: 'calculator', mark: '±', name: '计算器', hint: '表达式 · 键盘输入', description: '处理日常计算，鼠标与键盘都能顺手操作。', component: defineAsyncComponent(() => import('@/components/tools/CalculatorTool.vue')) },
  { id: 'json', mark: '{ }', name: 'JSON 解析', hint: '格式化 · 序列化', description: '整理结构化数据，检查语法，处理字符串转义。', component: defineAsyncComponent(() => import('@/components/tools/JsonTool.vue')) },
  { id: 'cron', mark: '*/5', name: 'cron 表达式', hint: '解析 · 执行时间预览', description: '读懂定时规则，预览下一次任务何时执行。', component: defineAsyncComponent(() => import('@/components/tools/CronTool.vue')) },
  { id: 'radix', mark: '0x', name: '进制转换', hint: '二 · 八 · 十 · 十六', description: '常用整数进制互转，保留大整数的完整精度。', component: defineAsyncComponent(() => import('@/components/tools/RadixTool.vue')) },
] as const
const active = computed(() => tools.find(tool => tool.id === route.query.tool) ?? tools[0])
const activeIndex = computed(() => tools.findIndex(tool => tool.id === active.value.id))
const directory = ref<HTMLElement | null>(null)

async function revealActiveTool() {
  await nextTick()
  const nav = directory.value
  const item = nav?.querySelector<HTMLElement>('[aria-current="page"]')
  if (!nav || !item || nav.scrollWidth <= nav.clientWidth) return
  const offset = item.getBoundingClientRect().left - nav.getBoundingClientRect().left
  if (offset < 0 || offset + item.offsetWidth > nav.clientWidth) {
    nav.scrollTo({ left: nav.scrollLeft + offset - (nav.clientWidth - item.offsetWidth) / 2 })
  }
}
watch(() => active.value.id, revealActiveTool, { flush: 'post' })
onMounted(() => {
  void revealActiveTool()
  window.addEventListener('resize', revealActiveTool)
})
onBeforeUnmount(() => window.removeEventListener('resize', revealActiveTool))
</script>

<template>
  <div class="tools-page">
    <div class="tools-path">
      <RouterLink to="/" class="tools-back"><ArrowLeft aria-hidden="true" />返回文章</RouterLink>
      <span>~ / tools</span>
    </div>
    <header class="tools-heading">
      <div>
        <p class="tools-eyebrow">// SMALL TOOLS, EVERYDAY IDEAS</p>
        <h1>工具箱<span aria-hidden="true">._</span></h1>
        <p class="tools-intro">把重复的操作交给工具，把注意力留给思考。</p>
      </div>
      <p class="tools-local"><span aria-hidden="true" />浏览器本地处理</p>
    </header>

    <div class="tools-layout">
      <aside class="tools-sidebar" aria-label="工具目录">
        <div class="tools-directory-label"><span>选择一个工具</span><span>08 / TOOLS</span></div>
        <nav ref="directory" class="tools-directory" aria-label="实用工具">
          <RouterLink
            v-for="(tool, index) in tools" :key="tool.id"
            :to="{ name: 'tools', query: { tool: tool.id } }"
            class="tools-directory-item" :class="{ 'is-active': tool.id === active.id }"
            :aria-current="tool.id === active.id ? 'page' : undefined"
          >
            <span class="tools-item-mark" aria-hidden="true">{{ tool.mark }}</span>
            <span class="tools-item-text"><strong>{{ tool.name }}</strong><small>{{ tool.hint }}</small></span>
            <span class="tools-item-index" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
          </RouterLink>
        </nav>
        <p class="tools-sidebar-note">一处小小的工作台，<br>给日常操作多一点便利。</p>
      </aside>

      <section class="tool-workspace" aria-labelledby="tool-title">
        <header class="tool-workspace-header">
          <div><span class="tool-number">TOOL / {{ String(activeIndex + 1).padStart(2, '0') }}</span><h2 id="tool-title">{{ active.name }}</h2><p>{{ active.description }}</p></div>
          <span class="tools-workspace-mark" aria-hidden="true">{{ active.mark }}</span>
        </header>
        <div class="tool-workspace-body">
          <Suspense :timeout="0">
            <component :is="active.component" :key="active.id" />
            <template #fallback><p class="tool-note" role="status">正在打开工具…</p></template>
          </Suspense>
        </div>
      </section>
    </div>

    <footer class="tools-end"><span>[ KEEP BUILDING ]</span><RouterLink to="/about">关于这里<ArrowRight aria-hidden="true" /></RouterLink></footer>
  </div>
</template>
