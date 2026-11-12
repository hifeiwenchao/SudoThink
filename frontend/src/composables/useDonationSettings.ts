import { inject, onBeforeUnmount, onMounted, provide, readonly, shallowRef, type InjectionKey, type Ref } from 'vue'
import type { DonationConfiguration } from '@/utils/donations'

const donationSettingsKey: InjectionKey<Readonly<Ref<DonationConfiguration | null>>> = Symbol('donation-settings')

export function provideDonationSettings(loadSettings: (signal: AbortSignal) => Promise<DonationConfiguration>) {
  const settings = shallowRef<DonationConfiguration | null>(null)
  const controller = new AbortController()
  provide(donationSettingsKey, readonly(settings))

  onMounted(async () => {
    try {
      const data = await loadSettings(controller.signal)
      if (!controller.signal.aborted) settings.value = data
    } catch {
      // Optional support entries stay hidden when public settings are unavailable.
    }
  })
  onBeforeUnmount(() => controller.abort())
}

export function useDonationSettings() {
  return inject(donationSettingsKey, readonly(shallowRef<DonationConfiguration | null>(null)))
}
