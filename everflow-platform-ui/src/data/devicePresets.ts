/** Preview device frames — Expo/web apps render in an iframe inside these sizes. */

export type DeviceChrome = 'none' | 'desktop' | 'tablet' | 'phone' | 'fold'

export type DeviceCategory = 'full' | 'desktop' | 'tablet' | 'phone'

export type DevicePresetId =
  | 'full'
  | 'desktop'
  | 'ipad-10'
  | 'android-tablet'
  | 'iphone-11'
  | 'iphone-12'
  | 'iphone-14-pro'
  | 'pixel-7'
  | 'samsung-z-fold-folded'
  | 'samsung-z-fold-unfolded'
  | 'custom'

export interface DevicePreset {
  id: DevicePresetId
  label: string
  category: DeviceCategory
  /** CSS logical width of the viewport (px). Null = fill panel. */
  width: number | null
  /** CSS logical height of the viewport (px). Null = fill panel. */
  height: number | null
  chrome: DeviceChrome
  /** When true, user can drag-resize width (and optionally height). */
  resizable?: boolean
}

export const DEVICE_PRESETS: DevicePreset[] = [
  {
    id: 'full',
    label: 'Full',
    category: 'full',
    width: null,
    height: null,
    chrome: 'none',
  },
  {
    id: 'desktop',
    label: 'Desktop',
    category: 'desktop',
    width: 1280,
    height: 800,
    chrome: 'desktop',
    resizable: true,
  },
  {
    id: 'ipad-10',
    label: 'iPad (10th)',
    category: 'tablet',
    width: 820,
    height: 1180,
    chrome: 'tablet',
  },
  {
    id: 'android-tablet',
    label: 'Android tablet',
    category: 'tablet',
    width: 800,
    height: 1280,
    chrome: 'tablet',
  },
  {
    id: 'iphone-11',
    label: 'iPhone 11',
    category: 'phone',
    width: 414,
    height: 896,
    chrome: 'phone',
  },
  {
    id: 'iphone-12',
    label: 'iPhone 12',
    category: 'phone',
    width: 390,
    height: 844,
    chrome: 'phone',
  },
  {
    id: 'iphone-14-pro',
    label: 'iPhone 14 Pro',
    category: 'phone',
    width: 393,
    height: 852,
    chrome: 'phone',
  },
  {
    id: 'pixel-7',
    label: 'Pixel 7',
    category: 'phone',
    width: 412,
    height: 915,
    chrome: 'phone',
  },
  {
    id: 'samsung-z-fold-folded',
    label: 'Galaxy Z Fold (folded)',
    category: 'phone',
    width: 280,
    height: 653,
    chrome: 'fold',
  },
  {
    id: 'samsung-z-fold-unfolded',
    label: 'Galaxy Z Fold (unfolded)',
    category: 'phone',
    width: 717,
    height: 512,
    chrome: 'fold',
  },
  {
    id: 'custom',
    label: 'Custom',
    category: 'desktop',
    width: 390,
    height: 844,
    chrome: 'phone',
    resizable: true,
  },
]

const BY_ID = Object.fromEntries(DEVICE_PRESETS.map((p) => [p.id, p])) as Record<
  DevicePresetId,
  DevicePreset
>

export function getDevicePreset(id: string | undefined | null): DevicePreset {
  if (id && id in BY_ID) return BY_ID[id as DevicePresetId]
  return BY_ID.full
}

export function isFramedPreset(preset: DevicePreset): boolean {
  return preset.width != null
}

/** Group presets for select menus (skip repeating Full in groups). */
export function devicePresetsByCategory(): {
  category: DeviceCategory
  label: string
  presets: DevicePreset[]
}[] {
  const labels: Record<DeviceCategory, string> = {
    full: 'View',
    desktop: 'Desktop',
    tablet: 'Tablets',
    phone: 'Phones',
  }
  const order: DeviceCategory[] = ['full', 'desktop', 'tablet', 'phone']
  return order.map((category) => ({
    category,
    label: labels[category],
    presets: DEVICE_PRESETS.filter((p) => p.category === category),
  }))
}
