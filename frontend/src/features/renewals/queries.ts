import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import * as renewalsApi from './api'
import type { CreateRenewalCampaignInput } from './types'

export const renewalKeys = {
  suggestions: (groupId: string) => ['groups', groupId, 'renewals', 'suggestions'] as const,
  campaigns: (groupId: string) => ['groups', groupId, 'renewals'] as const,
  detail: (campaignId: string) => ['renewals', campaignId] as const,
  nonResponders: (campaignId: string) => ['renewals', campaignId, 'non-responders'] as const,
}

export function useRenewalSuggestions(groupId: string) {
  return useQuery({
    queryKey: renewalKeys.suggestions(groupId),
    queryFn: () => renewalsApi.getRenewalSuggestions(groupId),
    enabled: Boolean(groupId),
  })
}

export function useRenewalCampaigns(groupId: string) {
  return useQuery({
    queryKey: renewalKeys.campaigns(groupId),
    queryFn: () => renewalsApi.getRenewalCampaigns(groupId),
    enabled: Boolean(groupId),
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

export function useCreateRenewalCampaign(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: CreateRenewalCampaignInput) => renewalsApi.createRenewalCampaign(groupId, input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.campaigns(groupId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.suggestions(groupId) })
    },
  })
}

export function useSendRenewalReminder(campaignId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (memberId: string) => renewalsApi.sendRenewalReminder(campaignId, memberId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.detail(campaignId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.nonResponders(campaignId) })
    },
  })
}

function invalidateCampaignListsPredicate(query: { queryKey: readonly unknown[] }) {
  return query.queryKey[0] === 'groups' && query.queryKey[2] === 'renewals' && query.queryKey.length === 3
}

export function useRemoveFromCampaign(campaignId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (memberId: string) => renewalsApi.removeFromCampaign(campaignId, memberId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.detail(campaignId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.nonResponders(campaignId) })
      void queryClient.invalidateQueries({ predicate: invalidateCampaignListsPredicate })
    },
  })
}

export function useCheckRenewalReactions(campaignId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => renewalsApi.checkRenewalReactions(campaignId),
    onSuccess: (detail) => {
      // The endpoint already returns the fresh detail — write it straight
      // into the cache instead of paying for a second round trip.
      queryClient.setQueryData(renewalKeys.detail(campaignId), detail)
      void queryClient.invalidateQueries({ queryKey: renewalKeys.nonResponders(campaignId) })
      void queryClient.invalidateQueries({ predicate: invalidateCampaignListsPredicate })
    },
  })
}

export function useProcessDueRemovals(campaignId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => renewalsApi.processDueRemovals(campaignId),
    onSuccess: (detail) => {
      // Same "endpoint already returns the fresh detail" shortcut as
      // `useCheckRenewalReactions` above.
      queryClient.setQueryData(renewalKeys.detail(campaignId), detail)
      void queryClient.invalidateQueries({ queryKey: renewalKeys.nonResponders(campaignId) })
      void queryClient.invalidateQueries({ predicate: invalidateCampaignListsPredicate })
    },
  })
}

export function useArchiveCampaign(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: string) => renewalsApi.archiveCampaign(campaignId),
    onSuccess: (_data, campaignId) => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.campaigns(groupId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.detail(campaignId) })
    },
  })
}

export function useUnarchiveCampaign(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: string) => renewalsApi.unarchiveCampaign(campaignId),
    onSuccess: (_data, campaignId) => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.campaigns(groupId) })
      void queryClient.invalidateQueries({ queryKey: renewalKeys.detail(campaignId) })
    },
  })
}

export function useDeleteCampaign(groupId: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (campaignId: string) => renewalsApi.deleteCampaign(campaignId),
    onSuccess: (_data, campaignId) => {
      void queryClient.invalidateQueries({ queryKey: renewalKeys.campaigns(groupId) })
      queryClient.removeQueries({ queryKey: renewalKeys.detail(campaignId) })
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
      // group's campaign list; invalidate every one of those broadly rather
      // than threading groupId through this hook.
      void queryClient.invalidateQueries({ predicate: invalidateCampaignListsPredicate })
    },
  })
}
