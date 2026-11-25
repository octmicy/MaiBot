import { badgeVariants } from '@/components/ui/badge'
import { cn } from '@/lib/utils'

export function DesktopPetBadge() {
  return (
    <span className={cn(badgeVariants({ variant: 'secondary' }), 'shrink-0 px-1.5 py-0.5 text-[10px] leading-none')}>
      桌宠对话
    </span>
  )
}
