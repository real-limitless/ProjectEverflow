import { Button, Label } from '@patternfly/react-core'
import { Link } from 'react-router-dom'
import {
  detailPath,
  kindLabel,
  originLabel,
  type MarketplaceItem,
} from '@/data/marketplace'
import { MarketplaceItemIcon } from './MarketplaceItemIcon'

interface MarketplaceCardProps {
  item: MarketplaceItem
  installed?: boolean
  featured?: boolean
  onGet: (item: MarketplaceItem) => void
}

export function MarketplaceCard({ item, installed, featured, onGet }: MarketplaceCardProps) {
  const to = detailPath(item.kind, item.id)
  return (
    <article className={`mp-card${featured ? ' mp-card--featured' : ''}`}>
      <Link to={to} className="mp-card-main" aria-label={`Open ${item.name}`}>
        <MarketplaceItemIcon id={item.id} name={item.name} size={featured ? 'lg' : 'md'} />
        <div className="mp-card-body">
          <div className="mp-card-head">
            <h2 className="mp-card-title">{item.name}</h2>
            <Label color={item.origin === 'everflow' ? 'green' : item.origin === 'ecc' ? 'blue' : 'grey'} isCompact>
              {originLabel(item.origin)}
            </Label>
          </div>
          <p className="mp-card-desc">{item.description}</p>
          <div className="mp-card-meta">
            <span className="mp-card-kind">{kindLabel(item.kind)}</span>
            {installed ? (
              <Label color="grey" isCompact>
                Installed
              </Label>
            ) : null}
          </div>
        </div>
      </Link>
      <div className="mp-card-actions">
        <Link className="pf-v6-c-button pf-m-secondary pf-m-small" to={to}>
          Open
        </Link>
        <Button
          variant="primary"
          size="sm"
          onClick={(e) => {
            e.preventDefault()
            onGet(item)
          }}
        >
          Get
        </Button>
      </div>
    </article>
  )
}
