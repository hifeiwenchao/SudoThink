import { defineStore } from 'pinia'
import { ref } from 'vue'
import { taxonomyApi, type Category } from '@/api/taxonomy'

export const useTaxonomyStore = defineStore('taxonomy', () => {
  const categories = ref<Category[]>([])
  const loaded = ref(false)
  let pending: Promise<Category[]> | null = null

  function loadCategories(): Promise<Category[]> {
    if (pending) return pending
    pending = taxonomyApi.categories().then((items) => {
      categories.value = [...items].sort((a, b) => b.weight - a.weight || a.id - b.id)
      loaded.value = true
      return categories.value
    }).finally(() => { pending = null })
    return pending
  }

  return { categories, loaded, loadCategories }
})
