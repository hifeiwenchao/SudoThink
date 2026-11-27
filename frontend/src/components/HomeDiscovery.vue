<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { aboutApi, type SidebarContent } from '@/api/about'
import { isContactUrl } from '@/utils/aboutContacts'

const route = useRoute()
const content = ref<SidebarContent | null>(null)
const featuredArticles = computed(() => content.value?.featured_articles.slice(0, 5) ?? [])
const projects = computed(() => (content.value?.current_projects.slice(0, 3) ?? []).map(project => ({
  ...project,
  href: project.url && isContactUrl(project.url) ? project.url : '',
})))
let active = true
onMounted(async () => {
  try {
    const data = await aboutApi.sidebar()
    if (active) content.value = data
  } catch {
    // Discovery is optional; article browsing remains available when it is offline.
  }
})
onBeforeUnmount(() => { active = false })
</script>

<template>
  <div v-if="featuredArticles.length || projects.length" class="home-discovery">
    <section v-if="featuredArticles.length" class="discovery-section" aria-labelledby="featured-heading">
      <p class="module-label"><span aria-hidden="true">01 /</span> SELECTED NOTES</p>
      <h2 id="featured-heading">精选文章<span aria-hidden="true">.</span></h2>
      <ol class="featured-list">
        <li v-for="(article, index) in featuredArticles" :key="article.id">
          <span class="article-number" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
          <div class="featured-copy">
            <RouterLink :to="{ path: `/articles/${article.id}`, query: { from: route.fullPath } }">{{ article.title }}</RouterLink>
            <p v-if="article.category" class="featured-category">{{ article.category.name }}</p>
          </div>
        </li>
      </ol>
    </section>
    <section v-if="projects.length" class="discovery-section" aria-labelledby="projects-heading">
      <p class="module-label"><span aria-hidden="true">02 /</span> WORK IN PROGRESS</p>
      <h2 id="projects-heading">正在折腾<span aria-hidden="true">.</span></h2>
      <div class="project-list">
        <article v-for="(project, index) in projects" :key="index" class="project-card">
          <h3>
            <a v-if="project.href" :href="project.href" target="_blank" rel="noopener noreferrer">{{ project.name }}<span aria-hidden="true">↗</span><span class="visually-hidden">（在新窗口打开）</span></a>
            <span v-else>{{ project.name }}</span>
          </h3>
          <p v-if="project.description">{{ project.description }}</p>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-discovery { min-width: 0; display: grid; gap: 30px; margin-top: 32px; padding-top: 27px; border-top: 1px dashed var(--blog-border); }
.discovery-section { min-width: 0; }
.module-label { margin: 0 0 10px; color: var(--blog-muted); font: 9px/1.6 var(--blog-mono); letter-spacing: .7px; }
.module-label > span { color: var(--blog-accent); margin-right: 6px; }
h2 { margin: 0 0 17px; font-size: 15px; font-weight: 650; letter-spacing: -.2px; }
h2 > span { color: var(--blog-accent); margin-left: 3px; }
a { color: var(--blog-text); text-decoration: none; overflow-wrap: anywhere; transition: color .15s ease; }
a:hover { color: var(--blog-accent); }
a:focus-visible { outline: 2px solid var(--blog-accent); outline-offset: 4px; border-radius: 2px; }
.featured-list { margin: 0; padding: 0; list-style: none; }
.featured-list li { display: grid; grid-template-columns: 23px minmax(0, 1fr); gap: 10px; padding: 12px 0; border-bottom: 1px solid var(--blog-border); }
.featured-list li:first-child { padding-top: 0; }
.featured-list li:last-child { border-bottom: 0; padding-bottom: 0; }
.article-number { padding-top: 3px; color: var(--blog-accent); font: 10px/1.6 var(--blog-mono); opacity: .8; }
.featured-copy { min-width: 0; }
.featured-copy > a { font-size: 13px; font-weight: 550; line-height: 1.75; }
.featured-category { margin: 5px 0 0; color: var(--blog-muted); font-size: 10px; line-height: 1.6; overflow-wrap: anywhere; }
.project-list { display: grid; gap: 10px; }
.project-card { min-width: 0; padding: 14px 15px; border: 1px solid var(--blog-border); border-left: 2px solid color-mix(in srgb, var(--blog-accent) 45%, var(--blog-border)); border-radius: 5px; background: var(--blog-surface); }
.project-card:focus-within { border-color: var(--blog-accent); }
h3 { margin: 0; font-size: 12px; line-height: 1.75; font-weight: 600; overflow-wrap: anywhere; }
h3 a > span[aria-hidden] { margin-left: 7px; color: var(--blog-accent); }
.project-card p { margin: 6px 0 0; color: var(--blog-muted); font-size: 11px; line-height: 1.85; overflow-wrap: anywhere; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
@media (max-width: 800px) { .home-discovery { margin-top: 0; padding-top: 26px; grid-column: 1 / -1; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 30px; } }
@media (max-width: 600px) { .home-discovery { grid-template-columns: minmax(0, 1fr); } .featured-copy > a { font-size: 14px; } .project-card p { font-size: 12px; } }
@media (prefers-reduced-motion: reduce) { a { transition: none; } }
</style>
