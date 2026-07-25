import { itemIconStyle } from '@/data/marketplace'

interface MarketplaceItemIconProps {
  id: string
  name?: string
  size?: 'sm' | 'md' | 'lg'
  className?: string
}

export function MarketplaceItemIcon({
  id,
  name,
  size = 'md',
  className = '',
}: MarketplaceItemIconProps) {
  const { hue, monogram } = itemIconStyle(id, name)
  return (
    <span
      className={`mp-icon mp-icon--${size} ${className}`.trim()}
      style={{
        background: `linear-gradient(145deg, hsl(${hue} 55% 42%), hsl(${(hue + 40) % 360} 60% 28%))`,
      }}
      aria-hidden
    >
      {monogram}
    </span>
  )
}
