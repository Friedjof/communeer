import { apiGet, apiPost } from '@/api/client'
import type {
  CreateRenewalCampaignInput,
  RenewalCampaignDetail,
  RenewalCampaignSummary,
  RenewalConfirmation,
  RenewalSuggestion,
} from './types'

export function getRenewalSuggestions(communityId: string): Promise<RenewalSuggestion[]> {
  return apiGet<RenewalSuggestion[]>(`/communities/${communityId}/renewals/suggestions`)
}

export function createRenewalCampaign(
  communityId: string,
  input: CreateRenewalCampaignInput,
): Promise<RenewalCampaignSummary> {
  return apiPost<RenewalCampaignSummary>(`/communities/${communityId}/renewals`, input)
}

export function getRenewalCampaigns(communityId: string): Promise<RenewalCampaignSummary[]> {
  return apiGet<RenewalCampaignSummary[]>(`/communities/${communityId}/renewals`)
}

export function getRenewalCampaign(campaignId: string): Promise<RenewalCampaignDetail> {
  return apiGet<RenewalCampaignDetail>(`/renewals/${campaignId}`)
}

export function confirmRenewal(campaignId: string, memberId: string): Promise<RenewalConfirmation> {
  return apiPost<RenewalConfirmation>(`/renewals/${campaignId}/confirmations/${memberId}/confirm`)
}

export function getNonResponders(campaignId: string): Promise<RenewalConfirmation[]> {
  return apiGet<RenewalConfirmation[]>(`/renewals/${campaignId}/non-responders`)
}
