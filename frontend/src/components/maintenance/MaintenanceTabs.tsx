import { useNavigate } from 'react-router-dom'

import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import MissingCoverTab from '@/components/maintenance/MissingCoverTab'
import UnimportedTab from '@/components/maintenance/UnimportedTab'
import BpmTab from '@/components/maintenance/BpmTab'

export const MAINTENANCE_TABS = ['cover-art', 'unimported', 'bpm'] as const
export type MaintenanceTab = (typeof MAINTENANCE_TABS)[number]

export function isMaintenanceTab(value: string): value is MaintenanceTab {
  return (MAINTENANCE_TABS as readonly string[]).includes(value)
}

interface MaintenanceTabsProps {
  slug: string
  tab: MaintenanceTab
}

/** The maintenance action tabs; the active tab is the URL segment after /maintenance/. */
export default function MaintenanceTabs({ slug, tab }: MaintenanceTabsProps) {
  const navigate = useNavigate()

  return (
    <Tabs
      value={tab}
      onValueChange={(value) => navigate(`/libraries/${slug}/maintenance/${value}`)}
      className="w-full"
    >
      <TabsList className="grid w-full max-w-lg grid-cols-3">
        <TabsTrigger value="cover-art">Missing cover art</TabsTrigger>
        <TabsTrigger value="unimported">Unimported</TabsTrigger>
        <TabsTrigger value="bpm">BPM</TabsTrigger>
      </TabsList>

      <TabsContent value="cover-art" className="mt-4">
        <MissingCoverTab slug={slug} />
      </TabsContent>
      <TabsContent value="unimported" className="mt-4">
        <UnimportedTab slug={slug} />
      </TabsContent>
      <TabsContent value="bpm" className="mt-4">
        <BpmTab slug={slug} />
      </TabsContent>
    </Tabs>
  )
}
