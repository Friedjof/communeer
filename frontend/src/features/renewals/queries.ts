import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as renewalsApi from './api'
import type { CreateRenewalCampaignInput } from './types'

export const renewalKeys = {
  suggestions: (communityId: string) => ['communities', communityId, 'renewals', 'suggestions'] as const,
  campaigns: (communityId: string) => ['communities', communityId, 'renewals'] as const,
  detail: (campaignId: string) => ['renewals', campaignId] as const,
  nonResponders: (campaignId: string) => ['renewals', campaignId, 'non-responders'] as const,
}

export function useRenewalSuggestions(communityId: string) {
  return useQuery({
    queryKey: renewalKeys.suggestions(communityId),
    queryFn: () => renewalsApi.getRenewalSuggestions(communityId),
    enabled: Boolean(communityId),
  })
}

export function useRenewalCampaigns(communityId: string) {
  return useQuery({
    queryKey: renewalKeys.campaigns(communityId),
    queryFn: () => renewalsApi.getRenewalCampaigns(communityId),
    enabled: Boolean(communityId),
  })
}

export function useRenewalCampaign(campaignId: string | null) {
  return useQuery({
    queryKey: renewalKeys.detail(campaignId ?? ''),
    queryFn: () => renewalsApi.getRenewalCampaign(campaignId as string),
    enabled: Boolean(campaignId),
  })
}

export function useNonResponders(campaignId: string | null) {
  return useQuery({
    queryKey: renewalKeys.nonResponders(campaignId ?? ''),
    queryFn: () => renewalsApi.getNonResponders(campaignId as string),
    enabled: Boolean(campaignId),
  })
}

export function useCreateRenewalCampaign(communityId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateRenewalCampaignInput) => renewalsApi.createRenewalCampaign(communityId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.campaigns(communityId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.suggestions(communityId) })
    },
  })
}

export function useConfirmRenewal(campaignId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (memberId: string) => renewalsApi.confirmRenewal(campaignId, memberId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.detail(campaignId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.nonResponders(campaignId) })
      // Campaign summaries (pending/confirmed/expired counts) live under each
      // community's campaign list; invalidate every one of those broadly
      // rather than threading communityId through this hook.
      void queryClient.invalidateQueries({
        predicate: (query) =>
          query.queryKey[0] === 'communities' && query.queryKey[2] === 'renewals' && query.queryKey.length === 3,
      })
    },
  })
}
