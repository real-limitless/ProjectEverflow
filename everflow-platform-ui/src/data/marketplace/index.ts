import catalogJson from './catalog.json'
import type { MarketplaceCatalog } from './types'

export type {
  MarketplaceCatalog,
  MarketplaceInstalledItem,
  MarketplaceInstalledResponse,
  MarketplaceItem,
  MarketplaceKind,
  MarketplaceTab,
} from './types'
export { MARKETPLACE_TABS, itemsForTab, tabToKind } from './types'

/** Vendored ECC + curated catalog (offline / demo fallback). */
export const LOCAL_MARKETPLACE_CATALOG = catalogJson as MarketplaceCatalog
