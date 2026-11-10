import assert from 'node:assert/strict'
import { constants, generateKeyPairSync, privateDecrypt, publicEncrypt } from 'node:crypto'
import { describe, it } from 'node:test'
import { AES } from 'crypto-es'
import {
  digestText,
  encodeBase64,
  decodeBase64,
  encryptSymmetric,
  decryptSymmetric,
  encryptRsa,
  decryptRsa,
  generateRsaKeyPair,
} from './tools/crypto'

describe('digest and UTF-8 Base64 tools', () => {
  it('matches known digest vectors including the empty string', () => {
    assert.equal(digestText('MD5', 'abc'), '900150983cd24fb0d6963f7d28e17f72')
    assert.equal(digestText('SHA1', 'abc'), 'a9993e364706816aba3e25717850c26c9cd0d89d')
    assert.equal(digestText('SHA256', 'abc'), 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad')
    assert.equal(digestText('SHA512', 'abc'), 'ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f')
    assert.equal(digestText('MD5', ''), 'd41d8cd98f00b204e9800998ecf8427e')
  })

  it('encodes Chinese and supplementary Unicode characters as UTF-8', () => {
    assert.equal(encodeBase64('你好🌍'), '5L2g5aW98J+MjQ==')
    assert.equal(decodeBase64('5L2g5aW9 8J+MjQ==\n'), '你好🌍')
    assert.equal(decodeBase64('SGVsbG8'), 'Hello')
    assert.equal(decodeBase64(''), '')
  })

  it('rejects malformed Base64 and non-UTF-8 bytes', () => {
    for (const value of ['a', 'not base64!', 'SGVsbG8===', '/w==']) {
      assert.throws(() => decodeBase64(value), /Base64|UTF-8/)
    }
  })

  it('roundtrips the maximum plaintext after UTF-8 and Base64 expansion', () => {
    const plaintext = '中'.repeat(1_000_000)
    const encoded = encodeBase64(plaintext)
    assert.equal(encoded.length, 4_000_000)
    assert.equal(decodeBase64(encoded + '\n'.repeat(1024)), plaintext)
  })

  it('keeps plaintext and encoded input limits separate and rejects excessive decoded text', () => {
    const excessivePlaintext = 'a'.repeat(1_000_001)
    assert.throws(() => encodeBase64(excessivePlaintext), /100 万/)
    assert.throws(() => decodeBase64(Buffer.from(excessivePlaintext).toString('base64')), /100 万/)
    assert.throws(() => decodeBase64(' '.repeat(4_001_025)), /过长/)
  })
})

describe('password based ciphers', () => {
  for (const algorithm of ['AES', 'DES', '3DES'] as const) {
    it(`${algorithm} preserves Unicode and uses a randomized OpenSSL salted ciphertext`, () => {
      const plaintext = '有空格的口令与正文 🌍\n第二行'
      const ciphertext = encryptSymmetric(algorithm, plaintext, ' secret 密钥 ')
      assert.ok(ciphertext.startsWith('U2FsdGVkX1'))
      assert.equal(decryptSymmetric(algorithm, ciphertext, ' secret 密钥 '), plaintext)
      assert.notEqual(encryptSymmetric(algorithm, plaintext, ' secret 密钥 '), ciphertext)
      assert.throws(() => decryptSymmetric(algorithm, ciphertext, 'incorrect'), /解密失败/)
    })
  }

  it('rejects empty passwords and ciphertext without an OpenSSL salt envelope', () => {
    assert.throws(() => encryptSymmetric('AES', 'hello', ''), /口令/)
    assert.throws(() => encryptSymmetric('AES', '', 'password'), /内容/)
    assert.throws(() => decryptSymmetric('AES', 'SGVsbG8=', 'password'), /密文|解密/)
    assert.throws(() => decryptSymmetric('AES', '!!!!', 'password'), /密文|解密/)
  })

  it('roundtrips maximum multibyte plaintext with room for the salt envelope and block padding', () => {
    const plaintext = '中'.repeat(1_000_000)
    const ciphertext = encryptSymmetric('AES', plaintext, 'password')
    assert.ok(ciphertext.length > 4_000_000)
    assert.equal(decryptSymmetric('AES', ciphertext, 'password'), plaintext)
  })

  it('rejects externally generated ciphertext whose decrypted plaintext exceeds the text budget', () => {
    const externalCiphertext = AES.encrypt('a'.repeat(1_000_001), 'password').toString()
    assert.throws(() => decryptSymmetric('AES', externalCiphertext, 'password'), /100 万/)
  })
})

describe('RSA encryption', () => {
  const pair = generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicKeyEncoding: { type: 'spki', format: 'pem' },
    privateKeyEncoding: { type: 'pkcs1', format: 'pem' },
  })

  it('encrypts with a PEM public key and decrypts Unicode with the matching private key', () => {
    const plaintext = 'SudoThink 中文 🌍'
    const ciphertext = encryptRsa(plaintext, pair.publicKey)
    assert.equal(Buffer.from(ciphertext, 'base64').length, 256)
    assert.equal(decryptRsa(ciphertext, pair.privateKey), plaintext)
  })

  it('accepts a full PKCS#1 byte budget and rejects excessive multibyte input and invalid keys', () => {
    assert.equal(decryptRsa(encryptRsa('a'.repeat(245), pair.publicKey), pair.privateKey), 'a'.repeat(245))
    assert.throws(() => encryptRsa('中'.repeat(82), pair.publicKey), /字节|过长/)
    assert.throws(() => encryptRsa('🌍'.repeat(62), pair.publicKey), /字节|过长/)
    assert.throws(() => encryptRsa('hello', 'invalid public key'), /公钥|PEM/)
    assert.throws(() => decryptRsa('AAAA', pair.publicKey), /私钥/)
    assert.throws(() => decryptRsa('!!!!', pair.privateKey), /密文|解密/)
  })

  it('interoperates with standard PKCS#1 UTF-8 ciphertext, including emoji at the byte limit', () => {
    const plaintext = '🌍'.repeat(61)
    const ciphertext = encryptRsa(plaintext, pair.publicKey)
    // Raw RSA avoids Node/OpenSSL builds that disable private PKCS#1 v1.5 unpadding.
    const padded = privateDecrypt({ key: pair.privateKey, padding: constants.RSA_NO_PADDING }, Buffer.from(ciphertext, 'base64'))
    assert.equal(padded[0], 0)
    assert.equal(padded[1], 2)
    const separator = padded.indexOf(0, 2)
    assert.ok(separator >= 10)
    assert.equal(padded.subarray(separator + 1).toString('utf8'), plaintext)
    const standardCiphertext = publicEncrypt({ key: pair.publicKey, padding: constants.RSA_PKCS1_PADDING }, Buffer.from('标准 UTF-8 🌍')).toString('base64')
    assert.equal(decryptRsa(standardCiphertext, pair.privateKey), '标准 UTF-8 🌍')
  })

  it('creates a 2048-bit PEM key pair asynchronously', async () => {
    const generated = await generateRsaKeyPair()
    assert.match(generated.publicKey, /BEGIN PUBLIC KEY/)
    assert.match(generated.privateKey, /BEGIN RSA PRIVATE KEY/)
    assert.equal(Buffer.from(encryptRsa('hello', generated.publicKey), 'base64').length, 256)
    assert.equal(decryptRsa(encryptRsa('密钥生成', generated.publicKey), generated.privateKey), '密钥生成')
  })

  it('cancels key generation immediately without leaving background computation running', async () => {
    const controller = new AbortController()
    const pending = generateRsaKeyPair(controller.signal)
    controller.abort()
    await assert.rejects(pending, { name: 'AbortError' })
    await assert.rejects(generateRsaKeyPair(controller.signal), { name: 'AbortError' })
  })
})
