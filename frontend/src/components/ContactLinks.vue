<script setup lang="ts">
import { computed } from 'vue'
import { contactFields, isContactEmail, isContactUrl, type ContactFields } from '@/utils/aboutContacts'

const props = defineProps<{ contacts?: ContactFields | null }>()
const links = computed(() => contactFields.flatMap(field => {
  const value = props.contacts?.[field.key]?.trim() || ''
  if (!value || !(field.key === 'email' ? isContactEmail(value) : isContactUrl(value))) return []
  return [{ ...field, href: field.key === 'email' ? `mailto:${value}` : value }]
}))
const icons: Record<string, string> = {
  github_url: 'M12 .8a11.3 11.3 0 0 0-3.57 22.02c.57.1.77-.24.77-.54v-2.1c-3.16.69-3.83-1.34-3.83-1.34-.52-1.32-1.27-1.67-1.27-1.67-1.04-.7.08-.69.08-.69 1.15.08 1.75 1.18 1.75 1.18 1.02 1.75 2.67 1.24 3.32.95.1-.74.4-1.24.73-1.53-2.52-.29-5.17-1.26-5.17-5.62 0-1.24.44-2.26 1.17-3.05-.12-.28-.51-1.44.11-3 0 0 .96-.31 3.11 1.16a10.8 10.8 0 0 1 5.66 0c2.16-1.47 3.11-1.16 3.11-1.16.62 1.56.23 2.72.11 3 .73.79 1.17 1.81 1.17 3.05 0 4.37-2.65 5.33-5.18 5.61.41.35.77 1.04.77 2.1v3.11c0 .3.2.65.78.54A11.3 11.3 0 0 0 12 .8Z',
  email: 'M2 4h20v16H2V4Zm2 2v.5l8 6 8-6V6H4Zm16 12V9l-8 6-8-6v9h16Z',
  x_url: 'M18.9 2H22l-6.8 7.8L23.2 22h-6.3L12 14.6 5.5 22H2.3l8.2-9.4L.8 2h6.5l4.5 6.8L18.9 2Zm-1.1 18h1.7L6.3 4H4.5l13.3 16Z',
  facebook_url: 'M14 22v-9h3l.5-4H14V6.5c0-1.2.4-2 2-2H18V1.2A23 23 0 0 0 15 1c-3 0-5 1.8-5 5v3H7v4h3v9h4Z',
  instagram_url: 'M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5Zm0 2a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7Zm5 3a5 5 0 1 1 0 10 5 5 0 0 1 0-10Zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6Zm5.5-3a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z',
}
</script>

<template>
  <nav v-if="links.length" class="contact-links" aria-label="联系方式">
    <a v-for="link in links" :key="link.key" :href="link.href" :aria-label="link.label" :title="link.label" :target="link.key === 'email' ? undefined : '_blank'" :rel="link.key === 'email' ? undefined : 'noopener noreferrer'">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="icons[link.key]" /></svg>
    </a>
  </nav>
</template>

<style scoped>
.contact-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }
.contact-links a { display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; color: var(--blog-muted, var(--el-text-color-secondary)); border-radius: 8px; transition: color .18s, background .18s; }
.contact-links a:hover { color: var(--el-color-primary); background: var(--el-fill-color-light); }
.contact-links a:focus-visible { outline: 2px solid var(--el-color-primary); outline-offset: 3px; }
.contact-links svg { width: 21px; height: 21px; fill: currentColor; }
</style>
