<template>
  <section class="not-found" aria-labelledby="not-found-title">
    <p>404 / PAGE NOT FOUND</p>
    <h1 id="not-found-title">这个页面暂时找不到了</h1>
    <p>链接可能已失效，或页面已被移走。回到首页继续探索吧。</p>
    <RouterLink to="/">返回首页 →</RouterLink>
  </section>
</template>
<style scoped>
.not-found { max-width: 720px; margin: 80px auto; padding: 32px; color: var(--blog-text); text-align: center; }
.not-found p { color: var(--blog-muted); line-height: 1.8; }
.not-found a { display: inline-block; margin-top: 20px; color: var(--blog-accent); }
</style>
