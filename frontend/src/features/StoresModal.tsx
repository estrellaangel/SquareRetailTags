import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../api/client";
import { useStores } from "../lib/queries";
import { Button, Field, Modal, TextInput } from "../ui";

export function StoresModal({ onClose }: { onClose: () => void }) {
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
      setError("");
    },
    onError: (e: Error) => setError(e.message),
  });

  const stores = storeData ?? [];

  return (
    <Modal
      title="Stores"
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            Close
          </Button>
          <Button
            variant="primary"
            disabled={mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {mutation.isPending ? "Creating…" : "Create store"}
          </Button>
        </>
      }
    >
      <ul className="mb-6 flex max-h-48 list-none flex-col gap-0 overflow-y-auto p-0">
        {stores.length === 0 && (
          <li className="py-2 text-sm text-faint">No stores yet.</li>
        )}
        {stores.map((s) => (
          <li
            key={s.id}
            className="flex items-center justify-between gap-3 border-b border-line-soft py-2.5 text-sm last:border-0"
          >
            <span className="font-medium text-ink">{s.name}</span>
            <span className="font-mono text-xs text-faint">{s.id}</span>
          </li>
        ))}
      </ul>

      {newKey && (
        <div className="mb-5 rounded-xl border border-line bg-warn-tint p-3.5">
          <p className="text-sm font-semibold text-warn">
            API key for {newKey.storeId} — shown once, save it now
          </p>
          <code className="mt-1.5 block font-mono text-xs break-all text-ink">
            {newKey.apiKey}
          </code>
          <p className="mt-2 text-xs text-muted">
            This is the <span className="font-mono">X-Store-Key</span> that
            store’s gateway sends when it polls for its labels.
          </p>
        </div>
      )}

      <h3 className="mb-3 text-xs font-bold tracking-wider text-muted uppercase">
        Add a store
      </h3>
      <div className="flex flex-col gap-3.5">
        <Field label="Store ID" hint="Short and lowercase, e.g. westgate">
          <TextInput
            placeholder="westgate"
            className="font-mono"
            value={id}
            onChange={(e) => setId(e.target.value)}
          />
        </Field>
        <Field label="Store name">
          <TextInput
            placeholder="Westgate"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
        <Field
          label="Square location ID"
          hint="Which Square location resolves this store’s price overrides"
        >
          <TextInput
            placeholder="L8MN4PQR2STUV"
            className="font-mono"
            value={squareLocationId}
            onChange={(e) => setSquareLocationId(e.target.value)}
          />
        </Field>
        {error && (
          <p className="rounded-lg bg-bad-tint px-3 py-2 text-sm text-bad">{error}</p>
        )}
      </div>
    </Modal>
  );
}
