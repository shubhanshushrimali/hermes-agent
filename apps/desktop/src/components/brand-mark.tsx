import { cn } from '@/lib/utils'

const assetPath = (path: string) => `${import.meta.env.BASE_URL}${path.replace(/^\/+/, '')}`

// Brand badge: Aizen manga avatar on a dark tile.
// The ring glow matches the theme's midground accent.
// Fills the tile (softly rounded); size via className (default size-14).
export function BrandMark({ className, ...props }: React.ComponentProps<'span'>) {
  return (
    <span
      className={cn(
        'inline-flex size-14 shrink-0 items-center justify-center overflow-hidden rounded-md bg-[#0B0D10]',
        'ring-1 ring-[color:var(--dt-midground,#6366F1)]/20',
        'transition-transform duration-200 ease-out hover:scale-[1.03]',
        className
      )}
      {...props}
    >
      <img alt="Aizen" className="size-full object-cover" src={assetPath('aizen-avatar.jpg')} />
    </span>
  )
}
