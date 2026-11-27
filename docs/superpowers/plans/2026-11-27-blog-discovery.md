# 博客内容探索与布局优化 Implementation Plan

> **For agentic workers:** 使用 subagent-driven-development 执行，保留此前未提交优化，不提交或部署。

**Goal:** 让首页侧栏内容更丰富，让文章页更容易继续阅读。

**Architecture:** 沿用 Vue/Sanic，关于我设置保存精选文章 ID 与最多三条项目动态；公开侧栏接口只返回公开文章与安全项目数据。相关阅读按同分类、共同标签匹配，独立接口不计阅读数。阅读操作使用现有滚动监听生命周期。

**Tech Stack:** Vue 3、TypeScript、Sanic、Tortoise、MySQL。

**Spec:** 用户已批准上一条回复的五项方案；本文记录实现细节。

## Global Constraints

- 保留此前未提交修改；当前工作区连续集成，不移动或重置文件。
- 不提交、不部署、不写生产业务数据；不增加依赖。
- 首页最大宽度 1280px；正文保持 720px；小屏侧栏移到底部，左侧操作栏隐藏。
- 精选文章最多5篇，正在折腾最多3条；空模块隐藏；草稿、回收站文章不公开。
- 后台入口放在关于我；项目字段名称60字、说明160字、可选完整HTTP(S)链接512字；公开内容不可含凭据链接。

## Review Focus

- 精选中的文章下架或删除后必须隐藏。
- 没有相关内容时隐藏推荐，不发送额外详情请求增加阅读数。
- 页面切换/请求乱序不得显示上一页推荐。
- 正文很短、没有目录时阅读进度仍正常，且无除零/越界。
- 手机、深色模式、键盘操作和减少动画偏好保持可用。

## Task 1: 后端内容契约
- [x] 先添加输入校验、公开可见性、相关推荐及升级幂等测试，确认缺失功能失败。
- [x] AboutPage新增 featured_article_ids/current_projects JSON字段，AboutIn验证；管理员关于我响应含配置，公开关于我排除原始配置。
- [x] GET /api/about/sidebar -> {featured_articles: ArticleRecommendation[], current_projects: CurrentProject[]}。
- [x] GET /api/articles/<aid>/related -> ArticleRecommendation[]，最多3篇，同分类优先，再共同标签；排除当前、草稿、回收站，不增加阅读数。
- [x] ArticleRecommendation = {id,title,summary,category:{id,name,slug}|null}；空配置返回空数组，精选按配置顺序。
- [x] 升级脚本添加可重复执行的列升级，保留历史数据，运行后端测试。

## Task 2: 首页布局
- [x] 新增独立 HomeDiscovery.vue 组件，调用 aboutApi.sidebar()；精选列表和项目卡片，空/失败隐藏，不影响文章列表。
- [x] HomeView 挂载组件、最大1280px、右栏约300px，调整间距与细微网格装饰；手机降为单栏。
- [x] 验证有内容/无内容、链接安全及卸载响应保护。

## Task 3: 文章阅读探索
- [x] 先测试进度边界/相关推荐切换和错误隔离。
- [x] ArticleDetailView调用 articleApi.related(id)，目录下显示最多3篇相关内容，小屏移正文后。
- [x] 宽屏左侧滚动后出现操作栏：正文阅读进度、跳转评论、回到顶部；有无目录均正常；移除监听和RAF。
- [x] 最大1280px，正文720px，预留操作轨道，窄屏不溢出。

## Task 4: 后台设置与集成
- [x] about.ts声明 CurrentProject/SidebarContent 和可选配置字段，article.ts新增推荐类型/方法。
- [x] 后台关于我增加按已发布文章搜索选择最多5篇（顺序为展示顺序），动态项目编辑最多3条；验证URL及长度，追踪未保存状态，保留旧关于我内容。
- [x] 新增后台保存/清空配置回归；更新功能文档。
- [x] 前后端全量测试、生产构建、浏览器宽屏/手机与浅深色验证，独立审查修改。
