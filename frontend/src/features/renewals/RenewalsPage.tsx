import { CampaignDetail } from './components/CampaignDetail'
import { CampaignList } from './components/CampaignList'
import { RenewalHowItWorks } from './components/RenewalHowItWorks'
import { StartRenewalSection } from './components/StartRenewalSection'

interface RenewalsPageProps {
  communityId: string
  selectedCampaignId: string | null
  onSelectCampaign: (campaignId: string | null) => void
}

export function RenewalsPage({ communityId, selectedCampaignId, onSelectCampaign }: RenewalsPageProps) {
  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-2xl font-semibold">Renewals</h1>
        <p className="text-sm text-muted-foreground">Track membership re-confirmation rounds for this community.</p>
      </div>

      <RenewalHowItWorks />

      <CampaignList communityId={communityId} selectedCampaignId={selectedCampaignId} onSelect={onSelectCampaign} />

      {selectedCampaignId ? <CampaignDetail campaignId={selectedCampaignId} /> : null}

      <StartRenewalSection communityId={communityId} onCampaignCreated={onSelectCampaign} />
    </div>
  )
}
