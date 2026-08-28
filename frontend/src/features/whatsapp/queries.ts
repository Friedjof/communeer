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
    refetchInterval: (query) => (query.state.data?.state === 'connected' ? false : 3000),
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
