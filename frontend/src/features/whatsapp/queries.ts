import { queryOptions, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { communityKeys } from '@/features/communities/queries'
import * as whatsappApi from './api'

export const whatsappKeys = {
  status: ['whatsapp', 'status'] as const,
}

export function whatsappStatusQueryOptions() {
  return queryOptions({
    queryKey: whatsappKeys.status,
    queryFn: whatsappApi.getWhatsAppStatus,
    staleTime: 0,
    // Keep polling while a discovery is running even once `state ===
    // 'connected'` — otherwise a page that reloaded mid-discovery would
    // fetch `discoveryInProgress: true` once and then never poll again to
    // see it flip back to `false`.
    refetchInterval: (query) =>
      query.state.data?.state !== 'connected' || query.state.data.discoveryInProgress ? 3000 : false,
  })
}

export function useWhatsAppStatus() {
  return useQuery(whatsappStatusQueryOptions())
}

export function useConnectWhatsApp() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: whatsappApi.connectWhatsApp,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: whatsappKeys.status })
    },
  })
}

export function useDiscoverAndSync() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: whatsappApi.discoverAndSyncCommunities,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: whatsappKeys.status })
      void queryClient.invalidateQueries({ queryKey: communityKeys.all })
    },
  })
}
