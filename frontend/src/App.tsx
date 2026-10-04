import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";
import { useEffect, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import { api, setTokenGetter } from "./api/client";
import type { components } from "./api/schema.d.ts";

type Tag = components["schemas"]["Tag"];
type Variation = components["schemas"]["Variation"];
type Store = components["schemas"]["Store"];

const TAG_ID_RE = /^[0-9A-F]{12}$/;

function useTags() {
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

function useStores() {
  return useQuery({
    queryKey: ["stores"],
    queryFn: async () => {
      const { data, error } = await api.GET("/stores", {});
      if (error) throw error;
      return data as Store[];
    },
  });
}

function useVariations() {
  return useQuery({
    queryKey: ["variations"],
    queryFn: async () => {
      const { data, error } = await api.GET("/catalog/variations", {});
      if (error) throw error;
      return (data as { variations: Variation[] }).variations;
    },
  });
}

/** Same hiding rule the label hardware itself uses: a "Regular" variation
 * name, or one that just repeats the item name, adds no information. */
function variationLabel(v: Variation): string | null {
  if (!v.variation_name) return null;
  if (v.variation_name === "Regular" || v.variation_name === v.name) return null;
  return v.variation_name;
}

function formatPrice(cents: number | null | undefined): string {
  return cents != null ? `$${(cents / 100).toFixed(2)}` : "Variable";
}

// ── Assign Modal ────────────────────────────────────────────────────────────

function AssignModal({
  initial,
  onClose,
}: {
  initial?: { tagId: string; storeId?: string; variationId?: string | null };
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [tagId, setTagId] = useState(initial?.tagId ?? "");
  const [storeId, setStoreId] = useState(initial?.storeId ?? "");
  const [variationId, setVariationId] = useState(initial?.variationId ?? "");
  const [error, setError] = useState("");

  const { data: varData } = useVariations();
  const { data: storeData } = useStores();

  const mutation = useMutation({
    mutationFn: async () => {
      const id = tagId.trim().toUpperCase();
      if (!TAG_ID_RE.test(id)) {
        throw new Error("Tag ID must be exactly 12 uppercase hex characters");
      }
      if (!storeId) {
        throw new Error("Store is required");
      }
      const { error } = await api.PUT("/tags/{tag_id}", {
        params: { path: { tag_id: id } },
        body: { store_id: storeId, variation_id: variationId || null },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tags"] });
      onClose();
    },
    onError: (e: Error) => setError(e.message),
  });

  const variations = varData ?? [];
  const stores = storeData ?? [];

  function formatVariationLabel(v: Variation) {
    const variation = variationLabel(v);
    return `${v.name}${variation ? ` › ${variation}` : ""} — ${formatPrice(v.price)}`;
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">
          {initial?.tagId ? "Edit Tag Assignment" : "Add Tag"}
        </h2>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Tag ID (12-char hex)
            </label>
            <input
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="AABBCCDD1122"
              value={tagId}
              maxLength={12}
              readOnly={!!initial?.tagId}
              onChange={(e) => setTagId(e.target.value.toUpperCase())}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Store
            </label>
            <select
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={storeId}
              disabled={!!initial?.storeId}
              onChange={(e) => setStoreId(e.target.value)}
            >
              <option value="">— Select a store —</option>
              {stores.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Variation
            </label>
            <select
              className="w-full border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              value={variationId}
              onChange={(e) => setVariationId(e.target.value)}
            >
              <option value="">— Unassigned —</option>
              {variations.map((v) => (
                <option key={v.id} value={v.id}>
                  {formatVariationLabel(v)}
                </option>
              ))}
            </select>
          </div>

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Saving…" : "Save"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Stores Modal ─────────────────────────────────────────────────────────────

function StoresModal({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [squareLocationId, setSquareLocationId] = useState("");
  const [error, setError] = useState("");
  const [newKey, setNewKey] = useState<{ storeId: string; apiKey: string } | null>(
    null,
  );

  const { data: storeData } = useStores();

  const mutation = useMutation({
    mutationFn: async () => {
      if (!id || !name || !squareLocationId) {
        throw new Error("id, name, and square_location_id are all required");
      }
      const { data, error } = await api.POST("/stores", {
        body: { id, name, square_location_id: squareLocationId },
      });
      if (error) throw error;
      return data as { id: string; api_key: string };
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["stores"] });
      setNewKey({ storeId: data.id, apiKey: data.api_key });
      setId("");
      setName("");
      setSquareLocationId("");
    },
    onError: (e: Error) => setError(e.message),
  });

  const stores = storeData ?? [];

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 className="text-base font-semibold text-gray-900 mb-4">Stores</h2>

        <ul className="divide-y divide-gray-100 mb-6 max-h-48 overflow-y-auto">
          {stores.length === 0 && (
            <li className="text-sm text-gray-400 py-2">No stores yet.</li>
          )}
          {stores.map((s) => (
            <li key={s.id} className="py-2 text-sm flex justify-between">
              <span className="font-medium text-gray-900">{s.name}</span>
              <span className="text-gray-400 font-mono text-xs">{s.id}</span>
            </li>
          ))}
        </ul>

        {newKey && (
          <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded text-sm">
            <p className="font-medium text-gray-900 mb-1">
              API key for {newKey.storeId} — shown once, save it now:
            </p>
            <code className="block break-all text-xs">{newKey.apiKey}</code>
          </div>
        )}

        <div className="space-y-3">
          <input
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            placeholder="Store id (e.g. downtown)"
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
          <input
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            placeholder="Store name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm"
            placeholder="Square location id"
            value={squareLocationId}
            onChange={(e) => setSquareLocationId(e.target.value)}
          />
          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
            onClick={onClose}
          >
            Close
          </button>
          <button
            className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Creating…" : "Create Store"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Item Detail Modal ───────────────────────────────────────────────────────

function ItemDetailModal({
  variation,
  onClose,
}: {
  variation: Variation;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: tagData } = useTags();
  const { data: storeData } = useStores();
  const [newTagId, setNewTagId] = useState("");
  const [newStoreId, setNewStoreId] = useState("");
  const [error, setError] = useState("");

  const tags = (tagData ?? []).filter((t) => t.variation_id === variation.id);
  const stores = storeData ?? [];

  const invalidateTags = () =>
    queryClient.invalidateQueries({ queryKey: ["tags"] });

  const addMutation = useMutation({
    mutationFn: async () => {
      const id = newTagId.trim().toUpperCase();
      if (!TAG_ID_RE.test(id)) {
        throw new Error("Tag ID must be exactly 12 uppercase hex characters");
      }
      if (!newStoreId) {
        throw new Error("Store is required");
      }
      const { error } = await api.PUT("/tags/{tag_id}", {
        params: { path: { tag_id: id } },
        body: { store_id: newStoreId, variation_id: variation.id },
      });
      if (error) throw error;
    },
    onSuccess: () => {
      invalidateTags();
      setNewTagId("");
      setNewStoreId("");
      setError("");
    },
    onError: (e: Error) => setError(e.message),
  });

  const unassignMutation = useMutation({
    mutationFn: async (tag: Tag) => {
      const { error } = await api.PUT("/tags/{tag_id}", {
        params: { path: { tag_id: tag.id } },
        body: { store_id: tag.store_id, variation_id: null },
      });
      if (error) throw error;
    },
    onSuccess: invalidateTags,
  });

  const variationName = variationLabel(variation);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg p-6">
        <h2 className="text-base font-semibold text-gray-900">
          {variation.name}
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          {variationName ? `${variationName} — ` : ""}
          {formatPrice(variation.price)}
          {variation.sku ? ` · SKU ${variation.sku}` : ""}
        </p>

        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Tags showing this item
        </h3>
        <ul className="divide-y divide-gray-100 mb-4 max-h-56 overflow-y-auto">
          {tags.length === 0 && (
            <li className="text-sm text-gray-400 py-2">
              No tags assigned yet — add one below.
            </li>
          )}
          {tags.map((tag) => (
            <li
              key={tag.id}
              className="py-2 text-sm flex items-center justify-between gap-2"
            >
              <div>
                <span className="font-mono text-xs text-gray-900">{tag.id}</span>
                <span className="text-gray-400 mx-2">·</span>
                <span className="text-gray-600">{tag.store_id}</span>
                {tag.battery_pct != null && (
                  <span className="text-gray-400 ml-2 text-xs">
                    {tag.battery_pct}% battery
                  </span>
                )}
              </div>
              <button
                className="text-xs text-red-600 hover:underline disabled:opacity-50"
                disabled={unassignMutation.isPending}
                onClick={() => unassignMutation.mutate(tag)}
              >
                Unassign
              </button>
            </li>
          ))}
        </ul>

        <h3 className="text-sm font-medium text-gray-700 mb-2">
          Add a tag for this item
        </h3>
        <div className="flex gap-2">
          <input
            className="flex-1 border border-gray-300 rounded px-3 py-2 text-sm font-mono uppercase focus:outline-none focus:ring-2 focus:ring-blue-500"
            placeholder="Tag ID (12-char hex)"
            value={newTagId}
            maxLength={12}
            onChange={(e) => setNewTagId(e.target.value.toUpperCase())}
          />
          <select
            className="border border-gray-300 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={newStoreId}
            onChange={(e) => setNewStoreId(e.target.value)}
          >
            <option value="">— Store —</option>
            {stores.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          <button
            className="px-3 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
            disabled={addMutation.isPending}
            onClick={() => addMutation.mutate()}
          >
            Add
          </button>
        </div>
        {error && <p className="text-sm text-red-600 mt-2">{error}</p>}

        <div className="flex justify-end mt-6">
          <button
            className="px-4 py-2 text-sm text-gray-600 hover:text-gray-900"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Item Grid ────────────────────────────────────────────────────────────────

function ItemGrid({ onSelect }: { onSelect: (variation: Variation) => void }) {
  const { data: varData, isLoading, error } = useVariations();
  const { data: tagData } = useTags();
  const [search, setSearch] = useState("");

  const tagCounts = new Map<string, number>();
  for (const tag of tagData ?? []) {
    if (!tag.variation_id) continue;
    tagCounts.set(tag.variation_id, (tagCounts.get(tag.variation_id) ?? 0) + 1);
  }

  const q = search.trim().toLowerCase();
  const items = (varData ?? []).filter((v) => {
    if (!q) return true;
    return (
      v.name.toLowerCase().includes(q) ||
      v.variation_name.toLowerCase().includes(q) ||
      (v.sku ?? "").toLowerCase().includes(q)
    );
  });

  if (isLoading)
    return (
      <div className="p-8 text-center text-gray-500">Loading items…</div>
    );
  if (error)
    return (
      <div className="p-8 text-center text-red-600">
        Failed to load items: {String(error)}
      </div>
    );

  return (
    <div>
      <input
        className="w-full max-w-sm border border-gray-300 rounded px-3 py-2 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-blue-500"
        placeholder="Search items…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {items.length === 0 && (
        <p className="text-sm text-gray-400">No items match.</p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {items.map((v) => {
          const count = tagCounts.get(v.id) ?? 0;
          const variationName = variationLabel(v);
          return (
            <button
              key={v.id}
              onClick={() => onSelect(v)}
              className="text-left border border-gray-200 rounded-lg p-4 hover:border-blue-400 hover:shadow-sm transition"
            >
              <p className="font-medium text-gray-900 text-sm">{v.name}</p>
              {variationName && (
                <p className="text-xs text-gray-500">{variationName}</p>
              )}
              <div className="flex items-center justify-between mt-3">
                <span className="text-sm text-gray-700">
                  {formatPrice(v.price)}
                </span>
                <span
                  className={
                    count > 0
                      ? "text-xs bg-blue-50 text-blue-700 rounded-full px-2 py-0.5"
                      : "text-xs bg-gray-100 text-gray-500 rounded-full px-2 py-0.5"
                  }
                >
                  {count} tag{count === 1 ? "" : "s"}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ── Signal ───────────────────────────────────────────────────────────────────

type Signal = Tag["signal"];

/** Worst first — what someone scanning the table needs to see at the top. */
const SIGNAL_RANK: Record<string, number> = {
  never_heard: 0,
  out_of_range: 1,
  weak: 2,
  ok: 3,
};

const SIGNAL_STYLE: Record<string, { label: string; className: string }> = {
  never_heard: {
    label: "Never heard",
    className: "bg-red-50 text-red-700 border-red-200",
  },
  out_of_range: {
    label: "Out of range",
    className: "bg-red-50 text-red-700 border-red-200",
  },
  weak: {
    label: "Weak",
    className: "bg-yellow-50 text-yellow-800 border-yellow-200",
  },
  ok: { label: "In range", className: "bg-green-50 text-green-700 border-green-200" },
};

function relativeTime(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function SignalPill({
  signal,
  rfPower,
  lastSeenAt,
}: {
  signal: Signal;
  rfPower?: number | null;
  lastSeenAt?: string | null;
}) {
  const style = SIGNAL_STYLE[signal] ?? SIGNAL_STYLE.never_heard;

  // The tooltip carries the detail so the cell itself stays scannable.
  const title =
    signal === "never_heard"
      ? "No access point has ever reported this tag — usually a tag ID that doesn't match real hardware"
      : `${rfPower ?? "?"} dBm${lastSeenAt ? `, last heard ${relativeTime(lastSeenAt)}` : ""}`;

  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap" title={title}>
      <span
        className={`text-xs border rounded px-1.5 py-0.5 ${style.className}`}
      >
        {style.label}
      </span>
      {signal !== "never_heard" && rfPower != null && (
        <span className="text-xs text-gray-400 tabular-nums">{rfPower} dBm</span>
      )}
    </span>
  );
}

/** Counts the tags that need attention, so problems are visible without
 * reading every row. Renders nothing when everything is healthy. */
function SignalSummary({ tags }: { tags: Tag[] }) {
  const never = tags.filter((t) => t.signal === "never_heard").length;
  const out = tags.filter((t) => t.signal === "out_of_range").length;
  const weak = tags.filter((t) => t.signal === "weak").length;
  const lowBattery = tags.filter((t) => t.low_battery).length;

  if (never + out + weak + lowBattery === 0) {
    return (
      <p className="text-sm text-green-700 mb-3">
        All {tags.length} tags in range.
      </p>
    );
  }

  const parts = [
    never > 0 && `${never} never heard`,
    out > 0 && `${out} out of range`,
    weak > 0 && `${weak} weak signal`,
    lowBattery > 0 && `${lowBattery} low battery`,
  ].filter(Boolean);

  return (
    <div className="mb-3 px-3 py-2 bg-amber-50 border border-amber-200 rounded text-sm text-amber-900">
      <span className="font-medium">Needs attention:</span> {parts.join(" · ")}
      <span className="text-amber-700">
        {" "}
        — sort by Signal to group them.
      </span>
    </div>
  );
}

// ── Locate ───────────────────────────────────────────────────────────────────

/** Flashes a tag's LED so staff can find it on the shelf.
 *
 * The flash is queued, not immediate: the store gateway is LAN-only and
 * can't be called from here, so it picks the command up on its next poll.
 * The button says "Queued" rather than "Flashing" for that reason. */
function LocateButton({ tagId }: { tagId: string }) {
  const [state, setState] = useState<"idle" | "queued" | "error">("idle");

  const mutation = useMutation({
    mutationFn: async () => {
      const { error } = await api.POST("/tags/{tag_id}/locate", {
        params: { path: { tag_id: tagId } },
        body: {},
      });
      if (error) throw error;
    },
    onSuccess: () => {
      setState("queued");
      setTimeout(() => setState("idle"), 4000);
    },
    onError: () => {
      setState("error");
      setTimeout(() => setState("idle"), 4000);
    },
  });

  const label =
    state === "queued" ? "Queued ✓" : state === "error" ? "Failed" : "Locate";

  return (
    <button
      className={
        state === "queued"
          ? "text-xs text-green-700"
          : state === "error"
            ? "text-xs text-red-600"
            : "text-xs text-gray-600 hover:text-gray-900 hover:underline disabled:opacity-50"
      }
      disabled={mutation.isPending || state !== "idle"}
      title="Flash this label's LED on the gateway's next poll"
      onClick={() => mutation.mutate()}
    >
      {mutation.isPending ? "…" : label}
    </button>
  );
}

// ── Tag Grid ─────────────────────────────────────────────────────────────────

const columnHelper = createColumnHelper<Tag>();

function TagGrid({ onAssign }: { onAssign: (tag: Tag) => void }) {
  const { data, isLoading, error } = useTags();

  // Battery ascending stays the default: the recurring operational task
  // this table exists for is "which tags need batteries". The column is
  // now volts rather than a percentage, because that is what the hardware
  // actually reports — the sort order is unchanged. Out-of-range tags are
  // surfaced by the summary banner instead, not by reordering this.
  const [sorting, setSorting] = useState<SortingState>([
    { id: "battery_volts", desc: false },
  ]);

  const columns = [
    columnHelper.accessor("id", {
      header: "Tag ID",
      cell: (info) => (
        <span className="font-mono text-xs">{info.getValue()}</span>
      ),
    }),
    columnHelper.accessor("store_id", {
      header: "Store",
      cell: (info) => <span className="text-xs">{info.getValue()}</span>,
    }),
    columnHelper.accessor("name", {
      header: "Product",
      cell: (info) =>
        info.getValue() ?? <span className="text-gray-400">—</span>,
    }),
    columnHelper.accessor("variation_name", {
      header: "Variation",
      cell: (info) =>
        info.getValue() ?? <span className="text-gray-400">—</span>,
    }),
    columnHelper.accessor("price", {
      header: "Price",
      cell: (info) => {
        const cents = info.getValue();
        if (cents == null)
          return <span className="text-gray-400">Variable</span>;
        return `$${(cents / 100).toFixed(2)}`;
      },
    }),
    columnHelper.accessor("signal", {
      header: "Signal",
      sortingFn: (a, b) =>
        SIGNAL_RANK[a.original.signal] - SIGNAL_RANK[b.original.signal],
      cell: (info) => (
        <SignalPill
          signal={info.getValue()}
          rfPower={info.row.original.rf_power}
          lastSeenAt={info.row.original.last_seen_at}
        />
      ),
    }),
    columnHelper.accessor("battery_volts", {
      header: "Battery",
      cell: (info) => {
        const volts = info.getValue();
        if (volts == null) return <span className="text-gray-400">—</span>;
        // Raw volts, not a percentage — the gateway's low-battery flag is
        // the authority on whether it needs swapping.
        const low = info.row.original.low_battery;
        return (
          <span className={low ? "text-red-600 font-medium" : "text-gray-700"}>
            {volts.toFixed(1)} V{low ? " ⚠" : ""}
          </span>
        );
      },
    }),
    columnHelper.accessor("last_confirmed_at", {
      header: "Last Confirmed",
      cell: (info) => {
        const v = info.getValue();
        if (!v) return <span className="text-gray-400">Never</span>;
        return new Date(v).toLocaleString();
      },
    }),
    columnHelper.accessor("content_hash", {
      header: "Hash",
      cell: (info) => {
        const h = info.getValue();
        if (!h) return <span className="text-gray-400">—</span>;
        return <span className="font-mono text-xs">{h.slice(0, 8)}…</span>;
      },
    }),
    columnHelper.display({
      id: "actions",
      header: "",
      cell: (info) => (
        <div className="flex items-center gap-3 justify-end">
          <LocateButton tagId={info.row.original.id} />
          <button
            className="text-xs text-blue-600 hover:underline"
            onClick={() => onAssign(info.row.original)}
          >
            Assign
          </button>
        </div>
      ),
    }),
  ];

  const table = useReactTable({
    data: data ?? [],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (isLoading)
    return <div className="p-8 text-center text-gray-500">Loading tags…</div>;
  if (error)
    return (
      <div className="p-8 text-center text-red-600">
        Failed to load tags: {String(error)}
      </div>
    );

  return (
    <div>
      <SignalSummary tags={data ?? []} />
      <div className="overflow-x-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id} className="border-b border-gray-200 bg-gray-50">
              {hg.headers.map((header) => (
                <th
                  key={header.id}
                  className="px-4 py-2 text-left font-medium text-gray-600 cursor-pointer select-none"
                  onClick={header.column.getToggleSortingHandler()}
                >
                  {flexRender(
                    header.column.columnDef.header,
                    header.getContext(),
                  )}
                  {header.column.getIsSorted() === "asc"
                    ? " ↑"
                    : header.column.getIsSorted() === "desc"
                      ? " ↓"
                      : ""}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td
                colSpan={columns.length}
                className="px-4 py-8 text-center text-gray-400"
              >
                No tags yet. Click "Add Tag" to register one.
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className="border-b border-gray-100 hover:bg-gray-50"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-4 py-2">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
      </div>
    </div>
  );
}

// ── App ───────────────────────────────────────────────────────────────────────

export default function App() {
  const {
    isLoading,
    isAuthenticated,
    loginWithRedirect,
    logout,
    getAccessTokenSilently,
    user,
  } = useAuth0();

  useEffect(() => {
    setTokenGetter(getAccessTokenSilently);
  }, [getAccessTokenSilently]);

  const [view, setView] = useState<"products" | "tags">("products");
  const [modal, setModal] = useState<
    | { tagId: string; storeId?: string; variationId?: string | null }
    | "new"
    | null
  >(null);
  const [selectedItem, setSelectedItem] = useState<Variation | null>(null);
  const [storesOpen, setStoresOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-gray-500 text-sm">
        Loading…
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4">
        <h1 className="text-lg font-semibold text-gray-900">ESL Pricing</h1>
        <p className="text-sm text-gray-500">Sign in to manage tags and stores.</p>
        <button
          className="px-4 py-2 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
          onClick={() => loginWithRedirect()}
        >
          Log In
        </button>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white">
      <header className="border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <h1 className="text-lg font-semibold text-gray-900">ESL Pricing</h1>
          <nav className="flex gap-1">
            <button
              className={
                view === "products"
                  ? "px-3 py-1.5 text-sm rounded bg-gray-900 text-white"
                  : "px-3 py-1.5 text-sm rounded text-gray-600 hover:bg-gray-100"
              }
              onClick={() => setView("products")}
            >
              Products
            </button>
            <button
              className={
                view === "tags"
                  ? "px-3 py-1.5 text-sm rounded bg-gray-900 text-white"
                  : "px-3 py-1.5 text-sm rounded text-gray-600 hover:bg-gray-100"
              }
              onClick={() => setView("tags")}
            >
              All Tags
            </button>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {user?.email && (
            <span className="text-sm text-gray-500">{user.email}</span>
          )}
          <button
            className="px-3 py-1.5 text-sm text-gray-700 border border-gray-300 rounded hover:bg-gray-50"
            onClick={() => setStoresOpen(true)}
          >
            Stores
          </button>
          {view === "tags" && (
            <button
              className="px-3 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
              onClick={() => setModal("new")}
            >
              + Add Tag
            </button>
          )}
          <button
            className="px-3 py-1.5 text-sm text-gray-700 border border-gray-300 rounded hover:bg-gray-50"
            onClick={() =>
              logout({ logoutParams: { returnTo: window.location.origin } })
            }
          >
            Log Out
          </button>
        </div>
      </header>

      <main className="p-6">
        {view === "products" ? (
          <ItemGrid onSelect={setSelectedItem} />
        ) : (
          <TagGrid
            onAssign={(tag) =>
              setModal({
                tagId: tag.id,
                storeId: tag.store_id,
                variationId: tag.variation_id,
              })
            }
          />
        )}
      </main>

      {selectedItem && (
        <ItemDetailModal
          variation={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}

      {modal !== null && (
        <AssignModal
          initial={modal === "new" ? undefined : modal}
          onClose={() => setModal(null)}
        />
      )}

      {storesOpen && <StoresModal onClose={() => setStoresOpen(false)} />}
    </div>
  );
}
