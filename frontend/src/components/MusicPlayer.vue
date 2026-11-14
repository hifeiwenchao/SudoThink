<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { musicApi, type MusicTrack } from '@/api/music'

const tracks = ref<MusicTrack[]>([])
const selectedIndex = ref(0)
const currentTrack = computed(() => tracks.value[selectedIndex.value])
const audio = ref<HTMLAudioElement>()
const expanded = ref(false)
const playing = ref(false)
const starting = ref(false)
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(0.5)
const error = ref('')
const playlist = ref<HTMLElement>()
const expandButton = ref<HTMLButtonElement>()
let active = true
let playVersion = 0
const controller = new AbortController()

function timeLabel(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00'
  return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`
}

function isCurrent(event: Event) {
  return active && event.currentTarget === audio.value
}

function syncPlayback(event: Event) {
  if (!isCurrent(event)) return
  playing.value = !audio.value!.paused
  if (playing.value) starting.value = false
}

function syncTime(event: Event) {
  if (!isCurrent(event)) return
  currentTime.value = Number.isFinite(audio.value!.currentTime) ? audio.value!.currentTime : 0
  duration.value = Number.isFinite(audio.value!.duration) ? audio.value!.duration : 0
}

async function play() {
  const element = audio.value
  if (!element || !active) return
  const version = ++playVersion
  if (error.value) element.load()
  error.value = ''
  starting.value = true
  element.volume = volume.value
  try {
    await element.play()
    if (active && version === playVersion && element === audio.value) {
      playing.value = !element.paused
    }
  } catch {
    if (active && version === playVersion && element === audio.value) {
      playing.value = false
      error.value = '暂时无法播放，请重试或切换其他曲目。'
    }
  } finally {
    if (active && version === playVersion) starting.value = false
  }
}

function togglePlay() {
  if (playing.value || starting.value) {
    ++playVersion
    audio.value?.pause()
    playing.value = false
    starting.value = false
  } else {
    void play()
  }
}

async function selectTrack(index: number) {
  if (!tracks.value.length || index < 0 || index >= tracks.value.length) return
  if (index === selectedIndex.value) { if (!playing.value) await play(); return }
  const version = ++playVersion
  audio.value?.pause()
  selectedIndex.value = index
  playing.value = false
  starting.value = false
  currentTime.value = duration.value = 0
  error.value = ''
  await nextTick()
  if (active && version === playVersion) await play()
}

function skip(direction: number) {
  if (!tracks.value.length) return
  const index = (selectedIndex.value + direction + tracks.value.length) % tracks.value.length
  if (index === selectedIndex.value) {
    if (audio.value) audio.value.currentTime = 0
    currentTime.value = 0
    void play()
  } else {
    void selectTrack(index)
  }
}

function ended(event: Event) {
  if (isCurrent(event)) skip(1)
}

function failed(event: Event) {
  if (!isCurrent(event)) return
  ++playVersion
  audio.value?.pause()
  playing.value = starting.value = false
  error.value = '音频加载失败，请重试或切换其他曲目。'
}

function seek(event: Event) {
  const seconds = Number((event.target as HTMLInputElement).value)
  if (audio.value && duration.value > 0 && Number.isFinite(seconds)) {
    audio.value.currentTime = Math.max(0, Math.min(seconds, duration.value))
    currentTime.value = audio.value.currentTime
  }
}

function changeVolume(event: Event) {
  volume.value = Number((event.target as HTMLInputElement).value)
  if (audio.value) audio.value.volume = volume.value
}

async function toggleExpanded() {
  expanded.value = !expanded.value
  if (expanded.value) { await nextTick(); playlist.value?.focus() }
}

function closePanel() {
  expanded.value = false
  expandButton.value?.focus()
}

onMounted(async () => {
  try {
    const data = await musicApi.get(controller.signal)
    if (active && data.enabled && Array.isArray(data.tracks)) tracks.value = data.tracks
  } catch {
    // Keep the optional player hidden when settings are unavailable.
  }
})

onBeforeUnmount(() => {
  active = false
  ++playVersion
  controller.abort()
  if (audio.value) {
    audio.value.pause()
    audio.value.removeAttribute('src')
    audio.value.load()
  }
})
</script>

<template>
  <section v-if="currentTrack" class="music-player" aria-label="网站音乐播放器">
    <audio ref="audio" :key="currentTrack.url" :src="currentTrack.url" preload="none" @play="syncPlayback" @pause="syncPlayback" @timeupdate="syncTime" @loadedmetadata="syncTime" @durationchange="syncTime" @ended="ended" @error="failed" />
    <div v-if="expanded" id="music-playlist" ref="playlist" class="music-panel" tabindex="-1" @keydown.esc.stop="closePanel">
      <div class="music-panel-heading"><span>听点音乐</span><span>{{ tracks.length }} 首</span><button type="button" aria-label="收起音乐列表" @click="closePanel">×</button></div>
      <div class="music-now-playing" aria-live="polite"><strong>{{ currentTrack.title }}</strong><span v-if="currentTrack.artist">{{ currentTrack.artist }}</span></div>
      <div class="music-controls">
        <button type="button" aria-label="上一首" :disabled="tracks.length < 2" @click="skip(-1)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h2v14H6zM18 5v14L8 12z" /></svg></button>
        <button type="button" class="music-play" :aria-label="playing || starting ? '暂停音乐' : '播放音乐'" @click="togglePlay"><svg v-if="playing || starting" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z" /></svg><svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="m8 4 13 8-13 8z" /></svg></button>
        <button type="button" aria-label="下一首" :disabled="tracks.length < 2" @click="skip(1)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 5h2v14h-2zM6 5v14l10-7z" /></svg></button>
      </div>
      <div class="music-progress"><span>{{ timeLabel(currentTime) }}</span><input type="range" aria-label="播放进度" min="0" :max="duration || 1" step="0.1" :value="currentTime" :disabled="!duration" :aria-valuetext="`${timeLabel(currentTime)} / ${timeLabel(duration)}`" @input="seek" /><span>{{ timeLabel(duration) }}</span></div>
      <label class="music-volume"><span>音量</span><input type="range" aria-label="音量" min="0" max="1" step="0.05" :value="volume" @input="changeVolume" /><span>{{ Math.round(volume * 100) }}%</span></label>
      <p v-if="error" class="music-error" role="alert">{{ error }}<button type="button" @click="play">重试</button></p>
      <p v-else-if="starting" class="music-status" role="status">正在加载音频…</p>
      <ol class="music-track-list" aria-label="音乐列表">
        <li v-for="(track, index) in tracks" :key="track.url"><button type="button" :class="{ 'is-current': index === selectedIndex }" :aria-current="index === selectedIndex ? 'true' : undefined" :aria-label="`播放 ${track.title}${track.artist ? `，${track.artist}` : ''}`" @click="selectTrack(index)"><span class="music-track-number">{{ String(index + 1).padStart(2, '0') }}</span><span class="music-track-copy"><span>{{ track.title }}</span><small v-if="track.artist">{{ track.artist }}</small></span><span v-if="index === selectedIndex && playing" class="music-playing-mark" aria-hidden="true">♫</span></button></li>
      </ol>
      <p class="music-hint">由你开启，按列表顺序循环播放</p>
    </div>
    <div class="music-mini">
      <button class="music-mini-play" type="button" :aria-label="playing || starting ? '暂停音乐' : '播放音乐'" @click="togglePlay"><svg v-if="playing || starting" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 5h4v14H6zm8 0h4v14h-4z" /></svg><svg v-else viewBox="0 0 24 24" aria-hidden="true"><path d="m8 4 13 8-13 8z" /></svg></button>
      <button ref="expandButton" class="music-mini-info" type="button" :aria-expanded="expanded" aria-controls="music-playlist" :aria-label="expanded ? '收起音乐列表' : '展开音乐列表'" @click="toggleExpanded"><span>{{ currentTrack.title }}</span><small>{{ error ? '播放失败 · 展开重试' : playing ? '正在播放' : starting ? '正在加载…' : '听点音乐' }}</small></button>
      <button class="music-mini-next" type="button" aria-label="下一首" :disabled="tracks.length < 2" @click="skip(1)"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 5h2v14h-2zM6 5v14l10-7z" /></svg></button>
    </div>
  </section>
</template>

<style scoped>
.music-player { position: fixed; left: 24px; bottom: calc(20px + env(safe-area-inset-bottom, 0px)); z-index: 45; width: 300px; max-width: calc(100vw - 48px); color: var(--blog-text); font-size: 13px; }
.music-player button { font: inherit; color: inherit; cursor: pointer; -webkit-tap-highlight-color: transparent; }
.music-player button:disabled { opacity: .35; cursor: default; }
.music-player svg { width: 18px; height: 18px; fill: currentColor; }
.music-mini, .music-panel { border: 1px solid var(--blog-border); border-radius: 14px; background: var(--blog-surface); box-shadow: 0 6px 24px rgb(0 0 0 / .08); }
.music-mini { display: flex; align-items: center; min-height: 58px; padding: 6px 10px; gap: 10px; }
.music-mini button, .music-controls button { display: grid; place-items: center; flex-shrink: 0; border: 0; background: transparent; border-radius: 50%; width: 36px; height: 36px; }
.music-mini .music-mini-play, .music-controls .music-play { background: var(--blog-accent); color: var(--blog-surface); }
.music-mini .music-mini-info { display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 3px; min-width: 0; flex: 1; width: auto; height: 42px; border-radius: 4px; padding: 0; text-align: left; }
.music-mini-info span { width: 100%; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12px; font-weight: 600; }
.music-mini-info small { font-size: 10px; color: var(--blog-muted); }
.music-panel { margin-bottom: 10px; padding: 16px; max-height: calc(100dvh - 112px); overflow-y: auto; outline: none; }
.music-panel-heading { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--blog-muted); }
.music-panel-heading > span:first-child { flex: 1; color: var(--blog-text); font-weight: 600; }
.music-panel-heading button { border: 0; background: transparent; font-size: 22px; width: 28px; height: 28px; border-radius: 4px; }
.music-now-playing { display: flex; flex-direction: column; gap: 5px; padding: 16px 0 8px; text-align: center; overflow-wrap: anywhere; }
.music-now-playing strong { font-size: 16px; }
.music-now-playing > span { font-size: 11px; color: var(--blog-muted); }
.music-controls { display: flex; justify-content: center; align-items: center; gap: 22px; margin: 10px 0; }
.music-controls .music-play { width: 42px; height: 42px; }
.music-progress, .music-volume { display: flex; align-items: center; gap: 9px; color: var(--blog-muted); font: 10px var(--blog-mono); }
.music-player input[type='range'] { min-width: 0; width: 100%; flex: 1; accent-color: var(--blog-accent); height: 20px; cursor: pointer; }
.music-progress > span, .music-volume > span { flex-shrink: 0; }
.music-volume { margin: 9px 0 14px; }
.music-volume > span:last-child { width: 28px; text-align: right; }
.music-track-list { list-style: none; margin: 12px -6px 0; padding: 0; max-height: 210px; overflow-y: auto; overscroll-behavior: contain; }
.music-track-list button { display: flex; align-items: center; gap: 10px; border: 0; background: transparent; text-align: left; padding: 10px 8px; width: 100%; border-radius: 6px; }
.music-track-list button:hover, .music-track-list button.is-current { background: var(--blog-accent-soft); color: var(--blog-accent); }
.music-track-number { font: 10px var(--blog-mono); opacity: .65; }
.music-track-copy { display: flex; flex: 1; min-width: 0; flex-direction: column; gap: 4px; overflow-wrap: anywhere; }
.music-track-copy > span { font-size: 12px; }
.music-track-copy small { font-size: 10px; color: var(--blog-muted); }
.music-hint { margin: 14px 0 0; font-size: 10px; color: var(--blog-muted); text-align: center; }
.music-error, .music-status { margin: 10px 0; line-height: 1.6; font-size: 11px; }
.music-error { color: var(--el-color-danger); }
.music-error button { padding: 2px 5px; margin-left: 4px; border: 0; border-radius: 4px; color: var(--blog-accent); background: transparent; text-decoration: underline; }
.music-status { color: var(--blog-muted); }
@media (max-width: 640px) { .music-player { left: 12px; bottom: calc(12px + env(safe-area-inset-bottom, 0px)); width: 270px; max-width: calc(100vw - 24px); } .music-mini { min-height: 54px; } }
</style>
