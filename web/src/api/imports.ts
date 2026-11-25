// Importing files.
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { request, type Schemas } from './client'

export type ImportResult = Schemas['ImportResult']

// Imports files. Rides the user deleted are left out (and listed) unless `includeDeleted`.
export function useImport() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      files,
      includeDeleted = false,
    }: {
      files: File[]
      includeDeleted?: boolean
    }) => {
      const body = new FormData()
      for (const file of files) body.append('files', file)
      const query = includeDeleted ? '?include_deleted=true' : ''
      return request<ImportResult>(`/api/imports${query}`, { method: 'POST', body })
    },
    // New rides change every list.
    onSuccess: () =>
      Promise.all(
        ['rides', 'trends', 'route-progress'].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      ),
  })
}
