import { CampaignDetail } from '@/features/renewals/components/CampaignDetail'
import { CampaignList } from '@/features/renewals/components/CampaignList'
import { RenewalHowItWorks } from '@/features/renewals/components/RenewalHowItWorks'
import { StartRenewalSection } from '@/features/renewals/components/StartRenewalSection'

interface GroupRenewalsTabProps {
  groupId: string
  groupName: string
  selectedCampaignId: string | null
  onSelectCampaign: (campaignId: string | null) => void
}

export function GroupRenewalsTab({ groupId, groupName, selectedCampaignId, onSelectCampaign }: GroupRenewalsTabProps) {
  return (
    <div className="flex flex-col gap-4">
      <RenewalHowItWorks />

      <CampaignList groupId={groupId} selectedCampaignId={selectedCampaignId} onSelect={onSelectCampaign} />

      {selectedCampaignId ? <CampaignDetail campaignId={selectedCampaignId} groupName={groupName} /> : null}

      <StartRenewalSection groupId={groupId} groupName={groupName} onCampaignCreated={onSelectCampaign} />
    </div>
  )
}
