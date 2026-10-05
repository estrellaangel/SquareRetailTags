import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { components } from "../api/schema.d.ts";

export type Tag = components["schemas"]["Tag"];
export type Variation = components["schemas"]["Variation"];
export type Store = components["schemas"]["Store"];

/** Tag IDs are 12-char uppercase hex at the API boundary — the real ESL
 * hardware's id length. Validate before sending, so a typo fails here with a
 * readable message instead of as a 422. */
export const TAG_ID_RE = /^[0-9A-F]{12}$/;

export function useTags() {
  return useQuery({
    queryKey: ["tags"],
    queryFn: async () => {
      const { data, error } = await api.GET("/admin/tags", {});
      if (error) throw error;
      return (data as { tags: Tag[] }).tags;
    },
    refetchInterval: 5_000,
  });
}

export function useStores() {
  return useQuery({
    queryKey: ["stores"],
    queryFn: async () => {
      const { data, error } = await api.GET("/stores", {});
      if (error) throw error;
      return data as Store[];
    },
  });
}

export function useVariations() {
  return useQuery({
    queryKey: ["variations"],
    queryFn: async () => {
      const { data, error } = await api.GET("/catalog/variations", {});
      if (error) throw error;
      return (data as { variations: Variation[] }).variations;
    },
  });
}
