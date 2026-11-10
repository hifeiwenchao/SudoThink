<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import CopyButton from '@/components/tools/CopyButton.vue'
import {
  decodeBase64, decryptRsa, decryptSymmetric, digestText, encodeBase64,
  encryptRsa, encryptSymmetric, generateRsaKeyPair,
  MAX_PLAINTEXT_LENGTH, MAX_ENCODED_LENGTH,
  type DigestAlgorithm, type SymmetricAlgorithm,
} from '@/utils/tools/crypto'

type Kind = 'symmetric' | 'rsa' | 'digest' | 'base64'
const kind = ref<Kind>('symmetric')
const symmetricAlgorithm = ref<SymmetricAlgorithm>('AES')
const digestAlgorithm = ref<DigestAlgorithm>('SHA256')
const input = ref('')
const password = ref('')
const publicKey = ref('')
const privateKey = ref('')
const output = ref('')
const outputReady = ref(false)
const error = ref('')
const generating = ref(false)
let generationVersion = 0
let generationController: AbortController | undefined
const forwardLabel = computed(() => kind.value === 'digest' ? '计算摘要' : kind.value === 'base64' ? 'Base64 编码' : '加密')
const reverseLabel = computed(() => kind.value === 'base64' ? 'Base64 解码' : '解密')
const outputLabel = computed(() => kind.value === 'digest' ? '十六进制摘要' : '处理结果')
const inputMaxLength = computed(() => kind.value === 'digest' ? MAX_PLAINTEXT_LENGTH : MAX_ENCODED_LENGTH)

function resetOutput() {
  output.value = ''
  outputReady.value = false
  error.value = ''
}

watch([kind, symmetricAlgorithm, digestAlgorithm, input, password, publicKey, privateKey], resetOutput)
watch(kind, (value, previous) => {
  if (previous === 'rsa' && value !== 'rsa') cancelGeneration()
})

function cancelGeneration() {
  generationVersion++
  generationController?.abort()
  generationController = undefined
  generating.value = false
}

function process(reverse = false) {
  resetOutput()
  try {
    if (kind.value === 'symmetric') {
      output.value = reverse
        ? decryptSymmetric(symmetricAlgorithm.value, input.value, password.value)
        : encryptSymmetric(symmetricAlgorithm.value, input.value, password.value)
    } else if (kind.value === 'rsa') {
      output.value = reverse ? decryptRsa(input.value, privateKey.value) : encryptRsa(input.value, publicKey.value)
    } else if (kind.value === 'digest') {
      output.value = digestText(digestAlgorithm.value, input.value)
    } else {
      output.value = reverse ? decodeBase64(input.value) : encodeBase64(input.value)
    }
    outputReady.value = true
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : '处理失败，请检查输入内容。'
  }
}

async function generateKeys() {
  cancelGeneration()
  const version = ++generationVersion
  const controller = new AbortController()
  generationController = controller
  generating.value = true
  resetOutput()
  try {
    const pair = await generateRsaKeyPair(controller.signal)
    if (version !== generationVersion) return
    publicKey.value = pair.publicKey
    privateKey.value = pair.privateKey
  } catch (caught) {
    if (version !== generationVersion) return
    error.value = caught instanceof Error ? caught.message : '密钥生成失败，请重试。'
  } finally {
    if (version === generationVersion) {
      generating.value = false
      generationController = undefined
    }
  }
}

function useOutput() {
  input.value = output.value
}

function clearAll() {
  cancelGeneration()
  input.value = ''
  password.value = ''
  publicKey.value = ''
  privateKey.value = ''
  resetOutput()
}

onBeforeUnmount(cancelGeneration)
</script>

<template>
  <div class="tool-stack">
    <p class="tool-note">所有计算在当前浏览器完成，内容、口令和密钥不会上传或保存。离开工具后请自行保管需要的结果。</p>
    <div class="tool-grid">
      <div class="tool-field">
        <label for="crypto-kind">功能</label>
        <el-select id="crypto-kind" v-model="kind" :teleported="false" aria-label="加密工具功能">
          <el-option label="口令加密 / 解密" value="symmetric" />
          <el-option label="RSA 公钥加密 / 私钥解密" value="rsa" />
          <el-option label="摘要（不可解密）" value="digest" />
          <el-option label="UTF-8 Base64 编码 / 解码" value="base64" />
        </el-select>
      </div>
      <div v-if="kind === 'symmetric'" class="tool-field">
        <label for="crypto-symmetric-algorithm">对称算法</label>
        <el-select id="crypto-symmetric-algorithm" v-model="symmetricAlgorithm" :teleported="false" aria-label="对称加密算法">
          <el-option label="AES-256" value="AES" />
          <el-option label="DES（兼容旧系统）" value="DES" />
          <el-option label="3DES（兼容旧系统）" value="3DES" />
        </el-select>
      </div>
      <div v-if="kind === 'digest'" class="tool-field">
        <label for="crypto-digest-algorithm">摘要算法</label>
        <el-select id="crypto-digest-algorithm" v-model="digestAlgorithm" :teleported="false" aria-label="摘要算法">
          <el-option label="MD5" value="MD5" />
          <el-option label="SHA-1" value="SHA1" />
          <el-option label="SHA-256" value="SHA256" />
          <el-option label="SHA-512" value="SHA512" />
        </el-select>
      </div>
    </div>

    <template v-if="kind === 'symmetric'">
      <label class="tool-field" for="crypto-password">
        <span>口令</span>
        <input id="crypto-password" v-model="password" class="tool-input" type="password" maxlength="1000000" autocomplete="off" placeholder="加密与解密必须使用同一口令，空格会保留" />
      </label>
      <p class="tool-note">格式：CryptoJS / OpenSSL 盐值 Base64，CBC 模式 + PKCS#7 填充，EVP_BytesToKey（MD5）派生密钥。与 OpenSSL 命令互通时需匹配这些参数。此兼容格式不带完整性校验。</p>
    </template>
    <template v-else-if="kind === 'rsa'">
      <div class="tool-actions">
        <button class="tool-button" type="button" :disabled="generating" @click="generateKeys">{{ generating ? '正在生成 2048 位密钥…' : '生成 2048 位密钥对' }}</button>
      </div>
      <div class="tool-grid" :aria-busy="generating">
        <label class="tool-field" for="crypto-public-key">
          <span>PEM 公钥（加密使用）</span>
          <textarea id="crypto-public-key" v-model="publicKey" class="tool-textarea tool-code" rows="6" maxlength="32768" :disabled="generating" placeholder="-----BEGIN PUBLIC KEY-----" spellcheck="false" />
          <CopyButton v-if="publicKey" :text="publicKey" label="复制公钥" />
        </label>
        <label class="tool-field" for="crypto-private-key">
          <span>PEM 私钥（解密使用）</span>
          <textarea id="crypto-private-key" v-model="privateKey" class="tool-textarea tool-code" rows="6" maxlength="32768" :disabled="generating" placeholder="-----BEGIN RSA PRIVATE KEY-----" spellcheck="false" />
          <CopyButton v-if="privateKey" :text="privateKey" label="复制私钥" />
        </label>
      </div>
      <p class="tool-note">使用 RSAES-PKCS1-v1_5，明文按标准 UTF-8 编码，密文为 Base64。2048 位密钥最多加密 245 字节，中文通常占 3 字节、表情通常占 4 字节。仅支持未加密的 PEM 密钥。</p>
    </template>
    <p v-else-if="kind === 'digest'" class="tool-note">摘要用于比较数据是否一致，不能反向解密。MD5、SHA-1 适合兼容与校验；密码存储请使用专用密码哈希算法。</p>
    <p v-else class="tool-note">Base64 是文本编码，不提供保密性。采用标准 Base64 字符表；解码结果必须是有效的 UTF-8 文本。</p>

    <label class="tool-field" for="crypto-input">
      <span>{{ kind === 'digest' ? '待计算摘要的文本（可以为空）' : '输入文本或待解密的密文' }}</span>
      <textarea id="crypto-input" v-model="input" class="tool-textarea tool-code" rows="6" :maxlength="inputMaxLength" spellcheck="false" placeholder="粘贴需要处理的内容" />
    </label>
    <p class="tool-note">明文或解码后的文本最多 100 万个字符{{ kind === 'digest' ? '。' : '；Base64 或密文输入最多 4,001,024 个字符（含空白），预留 UTF-8 编码、盐值与填充的空间。' }}</p>
    <div class="tool-actions">
      <button class="tool-button primary" type="button" :disabled="kind === 'rsa' && generating" @click="process(false)">{{ forwardLabel }}</button>
      <button v-if="kind !== 'digest'" class="tool-button" type="button" :disabled="kind === 'rsa' && generating" @click="process(true)">{{ reverseLabel }}</button>
      <button class="tool-button" type="button" @click="clearAll">清空内容和密钥</button>
    </div>
    <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
    <div v-if="outputReady" class="tool-result tool-stack" aria-live="polite">
      <div class="tool-actions">
        <span>{{ outputLabel }}</span>
        <CopyButton :text="output" label="复制结果" />
        <button class="tool-button" type="button" @click="useOutput">将结果放入输入框</button>
      </div>
      <pre class="tool-output">{{ output || '（空文本）' }}</pre>
    </div>
  </div>
</template>
