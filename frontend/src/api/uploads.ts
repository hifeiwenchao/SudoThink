import http from './http'
import type { UploadConfig, UploadPolicy, UploadPolicyInput } from '@/utils/mediaUpload'

export const uploadsApi = {
  config(signal?: AbortSignal) {
    return http.get<unknown, UploadConfig>('/admin/uploads/config', { signal })
  },
  policy(input: UploadPolicyInput, signal?: AbortSignal) {
    return http.post<unknown, UploadPolicy>('/admin/uploads/policy', input, { signal })
  },
}
