import { apiDelete, apiGet, apiPost } from '@/api/client'
import type {
  CreateRenewalCampaignInput,
  RenewalCampaignDetail,
  RenewalCampaignSummary,
  RenewalConfirmation,
  RenewalSuggestion,
} from './types'

export function getRenewalSuggestions(groupId: string): Promise<RenewalSuggestion[]> {
  return apiGet<RenewalSuggestion[]>(`/groups/${groupId}/renewals/suggestions`)
}

export function createRenewalCampaign(
  groupId: string,
  input: CreateRenewalCampaignInput,
): Promise<RenewalCampaignSummary> {
  return apiPost<RenewalCampaignSummary>(`/groups/${groupId}/renewals`, input)
}

export function getRenewalCampaigns(groupId: string): Promise<RenewalCampaignSummary[]> {
  return apiGet<RenewalCampaignSummary[]>(`/groups/${groupId}/renewals`)
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

export function sendRenewalReminder(campaignId: string, memberId: string): Promise<RenewalConfirmation> {
  return apiPost<RenewalConfirmation>(`/renewals/${campaignId}/confirmations/${memberId}/send-reminder`)
}

export function removeFromCampaign(campaignId: string, memberId: string): Promise<void> {
  return apiPost<void>(`/renewals/${campaignId}/confirmations/${memberId}/remove`)
}

export function checkRenewalReactions(campaignId: string): Promise<RenewalCampaignDetail> {
  return apiPost<RenewalCampaignDetail>(`/renewals/${campaignId}/check-reactions`)
}

export function archiveCampaign(campaignId: string): Promise<RenewalCampaignSummary> {
  return apiPost<RenewalCampaignSummary>(`/renewals/${campaignId}/archive`)
}

export function unarchiveCampaign(campaignId: string): Promise<RenewalCampaignSummary> {
  return apiPost<RenewalCampaignSummary>(`/renewals/${campaignId}/unarchive`)
}

export function deleteCampaign(campaignId: string): Promise<void> {
  return apiDelete<void>(`/renewals/${campaignId}`)
}

export function processDueRemovals(campaignId: string): Promise<RenewalCampaignDetail> {
  return apiPost<RenewalCampaignDetail>(`/renewals/${campaignId}/process-removals`)
}
