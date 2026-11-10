import { AES, DES, TripleDES, MD5, SHA1, SHA256, SHA512, Utf8, Base64, Hex, WordArray, NoPadding, CBC, Pkcs7 } from 'crypto-es'
import forge from 'node-forge'

export type DigestAlgorithm = 'MD5' | 'SHA1' | 'SHA256' | 'SHA512'
export type SymmetricAlgorithm = 'AES' | 'DES' | '3DES'
export const MAX_PLAINTEXT_LENGTH = 1_000_000
// One million UTF-16 units produce at most 3 MB of UTF-8 / 4 MB of Base64.
// Keep extra room for the OpenSSL salt envelope, block padding and pasted whitespace.
export const MAX_ENCODED_LENGTH = 4_001_024
const ciphers = { AES, DES, '3DES': TripleDES }
const digests = { MD5, SHA1, SHA256, SHA512 }

function checkInput(text: string): void {
  if (text.length > MAX_PLAINTEXT_LENGTH) throw new Error('明文内容过长，请控制在 100 万个字符以内。')
}

function checkEncodedInput(text: string): void {
  if (text.length > MAX_ENCODED_LENGTH) throw new Error('编码内容过长，请控制在 4,001,024 个字符以内（含空白）。')
}

function checkPassword(password: string): void {
  if (!password) throw new Error('请输入加解密口令，口令中的空格会保留。')
  checkInput(password)
}

function parseBase64(text: string): WordArray {
  checkEncodedInput(text)
  const compact = text.replace(/\s/g, '')
  if (!/^[A-Za-z0-9+/]*={0,2}$/.test(compact) || compact.length % 4 === 1 ||
      (compact.includes('=') && compact.length % 4 !== 0)) {
    throw new Error('Base64 格式无效，请检查字符和末尾填充。')
  }
  const bytes = Base64.parse(compact)
  if (Base64.stringify(bytes).replace(/=+$/, '') !== compact.replace(/=+$/, '')) {
    throw new Error('Base64 格式无效，请检查末尾字符。')
  }
  return bytes
}

export function digestText(algorithm: DigestAlgorithm, text: string): string {
  checkInput(text)
  try {
    return digests[algorithm](text).toString(Hex)
  } catch {
    throw new Error('摘要计算失败，请检查输入是否为有效的 Unicode 文本。')
  }
}

export function encodeBase64(text: string): string {
  checkInput(text)
  try {
    return Base64.stringify(Utf8.parse(text))
  } catch {
    throw new Error('Base64 编码失败，请检查输入是否为有效的 Unicode 文本。')
  }
}

export function decodeBase64(text: string): string {
  const bytes = parseBase64(text)
  let decoded: string
  try {
    decoded = Utf8.stringify(bytes)
  } catch {
    throw new Error('Base64 已解析，但其内容不是有效的 UTF-8 文本。')
  }
  checkInput(decoded)
  return decoded
}

function secureSalt(): WordArray {
  if (!globalThis.crypto?.getRandomValues) throw new Error('当前浏览器不支持安全随机数，请换用较新的浏览器。')
  return new WordArray(globalThis.crypto.getRandomValues(new Uint8Array(8)))
}

export function encryptSymmetric(algorithm: SymmetricAlgorithm, text: string, password: string): string {
  checkInput(text)
  checkPassword(password)
  if (!text) throw new Error('请输入需要加密的内容。')
  const salt = secureSalt()
  try {
    return ciphers[algorithm].encrypt(text, password, { salt, mode: CBC, padding: Pkcs7 }).toString()
  } catch {
    throw new Error('加密失败，请检查内容和口令是否为有效的 Unicode 文本。')
  }
}

function byteAt(bytes: WordArray, index: number): number {
  return (bytes.words[index >>> 2] >>> (24 - (index % 4) * 8)) & 255
}

export function decryptSymmetric(algorithm: SymmetricAlgorithm, text: string, password: string): string {
  checkPassword(password)
  checkEncodedInput(text)
  let decoded: string
  try {
    const envelope = parseBase64(text)
    const blockBytes = algorithm === 'AES' ? 16 : 8
    if (envelope.sigBytes < 16 + blockBytes || (envelope.sigBytes - 16) % blockBytes !== 0 ||
        envelope.words[0] !== 0x53616c74 || envelope.words[1] !== 0x65645f5f) throw new Error()
    // Verify PKCS#7 explicitly: the library's default unpad does not validate the password or padding.
    const plaintext = ciphers[algorithm].decrypt(Base64.stringify(envelope), password, { mode: CBC, padding: NoPadding })
    const padding = byteAt(plaintext, plaintext.sigBytes - 1)
    if (padding < 1 || padding > blockBytes || padding > plaintext.sigBytes) throw new Error()
    for (let index = plaintext.sigBytes - padding; index < plaintext.sigBytes; index++) {
      if (byteAt(plaintext, index) !== padding) throw new Error()
    }
    plaintext.sigBytes -= padding
    plaintext.clamp()
    decoded = Utf8.stringify(plaintext)
  } catch {
    throw new Error('解密失败，请检查算法、口令和 OpenSSL 格式密文是否匹配。')
  }
  checkInput(decoded)
  return decoded
}

function checkRsaPem(pem: string, privateKey: boolean): void {
  const label = privateKey ? '私钥' : '公钥'
  const header = privateKey ? /-----BEGIN (?:RSA )?PRIVATE KEY-----/ : /-----BEGIN (?:RSA )?PUBLIC KEY-----/
  if (pem.length > 32_768 || !header.test(pem)) throw new Error(`请输入有效的 PEM 格式 RSA ${label}。`)
}

function rsaByteLength(key: forge.pki.rsa.PublicKey | forge.pki.rsa.PrivateKey): number {
  const bits = key.n.bitLength()
  if (bits < 512 || bits > 8192) throw new Error('仅支持 512 至 8192 位的 RSA 密钥。')
  return Math.ceil(bits / 8)
}

export function encryptRsa(text: string, publicKey: string): string {
  checkInput(text)
  if (!text) throw new Error('请输入需要加密的内容。')
  checkRsaPem(publicKey, false)
  let key: forge.pki.rsa.PublicKey
  try {
    key = forge.pki.publicKeyFromPem(publicKey)
  } catch {
    throw new Error('RSA 公钥无法读取，请使用 PEM 格式公钥。')
  }
  const maxBytes = rsaByteLength(key) - 11
  let utf8: string
  try {
    utf8 = forge.util.encodeUtf8(text)
  } catch {
    throw new Error('RSA 加密失败，请检查输入是否为有效的 Unicode 文本。')
  }
  if (utf8.length > maxBytes) {
    throw new Error(`内容过长，此密钥最多容纳 ${maxBytes} 个 UTF-8 字节（中文通常为 3 字节，表情通常为 4 字节）。`)
  }
  // getRandomValues also works on HTTP origins; a secure context and crypto.subtle are not required.
  secureSalt()
  try {
    return forge.util.encode64(key.encrypt(utf8, 'RSAES-PKCS1-V1_5'))
  } catch {
    throw new Error('RSA 加密失败，请检查公钥和输入内容。')
  }
}

export function decryptRsa(text: string, privateKey: string): string {
  checkRsaPem(privateKey, true)
  let key: forge.pki.rsa.PrivateKey
  try {
    key = forge.pki.privateKeyFromPem(privateKey)
  } catch {
    throw new Error('RSA 私钥无法读取，请使用未加密的 PEM 格式私钥。')
  }
  const byteLength = rsaByteLength(key)
  try {
    const ciphertext = parseBase64(text)
    if (ciphertext.sigBytes !== byteLength) throw new Error()
    return forge.util.decodeUtf8(key.decrypt(forge.util.decode64(Base64.stringify(ciphertext)), 'RSAES-PKCS1-V1_5'))
  } catch {
    throw new Error('RSA 解密失败，请检查私钥和 Base64 密文是否匹配。')
  }
}

type KeyGenerationState = { keys: forge.pki.rsa.KeyPair | null }
// Forge documents these incremental APIs, but @types/node-forge omits their declarations.
const steppedRsa = forge.pki.rsa as typeof forge.pki.rsa & {
  createKeyPairGenerationState(bits: number, exponent: number): KeyGenerationState
  stepKeyPairGenerationState(state: KeyGenerationState, milliseconds: number): boolean
}

export async function generateRsaKeyPair(signal?: AbortSignal): Promise<{ publicKey: string; privateKey: string }> {
  const cancelled = () => new DOMException('RSA 密钥生成已取消。', 'AbortError')
  if (signal?.aborted) throw cancelled()
  secureSalt()
  return new Promise((resolve, reject) => {
    let state: KeyGenerationState
    try {
      state = steppedRsa.createKeyPairGenerationState(2048, 0x10001)
    } catch {
      reject(new Error('RSA 密钥生成失败，请重试。'))
      return
    }
    let timer: ReturnType<typeof setTimeout> | undefined
    const cleanup = () => {
      if (timer !== undefined) clearTimeout(timer)
      signal?.removeEventListener('abort', abort)
    }
    const abort = () => {
      cleanup()
      reject(cancelled())
    }
    signal?.addEventListener('abort', abort, { once: true })
    // Small main-thread slices work on HTTP and avoid external worker scripts or network requests.
    const step = () => {
      if (signal?.aborted) {
        abort()
        return
      }
      try {
        if (!steppedRsa.stepKeyPairGenerationState(state, 10)) {
          timer = setTimeout(step, 0)
          return
        }
        if (!state.keys) throw new Error()
        cleanup()
        resolve({
          publicKey: forge.pki.publicKeyToPem(state.keys.publicKey),
          privateKey: forge.pki.privateKeyToPem(state.keys.privateKey),
        })
      } catch {
        cleanup()
        reject(new Error('RSA 密钥生成失败，请重试。'))
      }
    }
    timer = setTimeout(step, 0)
  })
}
