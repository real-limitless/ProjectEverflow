import catalogJson from './catalog.json'
import type { MarketplaceCatalog } from './types'

export type {
  MarketplaceCatalog,
  MarketplaceInstalledItem,
  MarketplaceInstalledResponse,
  MarketplaceItem,
  MarketplaceItemContent,
  MarketplaceKind,
  MarketplaceTab,
} from './types'
export { MARKETPLACE_TABS, itemsForTab, tabToKind } from './types'
export {
  collectOrigins,
  collectTags,
  detailPath,
  featuredItems,
  filterMarketplaceItems,
  findCatalogItem,
  itemIconStyle,
  kindLabel,
  kindToTab,
  originLabel,
  paginateItems,
  parseKindParam,
  supportsContentPreview,
  supportsTryChat,
} from './helpers'

/** Vendored ECC + curated catalog (offline / demo fallback). */
export const LOCAL_MARKETPLACE_CATALOG = catalogJson as MarketplaceCatalog
