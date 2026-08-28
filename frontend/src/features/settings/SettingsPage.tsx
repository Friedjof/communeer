import { Settings } from 'lucide-react'
import { EmptyState } from '@/components/feedback/EmptyState'

export function SettingsPage() {
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Settings</h1>
      <EmptyState icon={Settings} title="Settings coming soon" description="Workspace and provider settings will live here." />
    </div>
  )
}
