import { useAuth0 } from "@auth0/auth0-react";
import clsx from "clsx";
import { useEffect, useState } from "react";
import { setTokenGetter } from "./api/client";
import { AssignModal, type AssignTarget } from "./features/AssignModal";
import { ItemDetailModal } from "./features/ItemDetailModal";
import { LabelList } from "./features/LabelList";
import { ProductList } from "./features/ProductList";
import { StoresModal } from "./features/StoresModal";
import type { Variation } from "./lib/queries";
import { Button, ThemeToggle } from "./ui";

type View = "labels" | "products";

/** The wordmark. The rounded rectangle is a shelf label with a price line —
 * swap it for the company mark when there is one. */
function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true">
        <rect x="2" y="5" width="20" height="14" rx="3" className="fill-accent" />
        <rect x="5.5" y="8.5" width="8" height="2" rx="1" className="fill-on-accent" />
        <rect
          x="5.5"
          y="12.5"
          width="13"
          height="3"
          rx="1.5"
          className="fill-on-accent"
          opacity="0.55"
        />
      </svg>
      <span className="text-[15px] font-bold tracking-tight text-ink">
        ESL Pricing
      </span>
    </span>
  );
}

function NavLink({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-current={active ? "page" : undefined}
      onClick={onClick}
      className={clsx(
        "min-h-10 rounded-lg px-3.5 text-sm transition-colors",
        active
          ? "bg-accent font-semibold text-on-accent"
          : "font-medium text-muted hover:text-ink",
      )}
    >
      {children}
    </button>
  );
}

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

  const [view, setView] = useState<View>("labels");
  const [assigning, setAssigning] = useState<AssignTarget | "new" | null>(null);
  const [selected, setSelected] = useState<Variation | null>(null);
  const [storesOpen, setStoresOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted">
        Loading…
      </div>
    );
  }

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-5 px-6">
        <Logo />
        <p className="text-center text-sm text-muted">
          Sign in to manage shelf labels and stores.
        </p>
        <Button
          variant="primary"
          className="min-h-11 px-5"
          onClick={() => loginWithRedirect()}
        >
          Log in
        </Button>
        <div className="mt-2">
          <ThemeToggle />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="flex flex-wrap items-center gap-x-6 gap-y-3.5 border-b border-line-soft px-7 py-4">
        <Logo />

        <nav className="flex gap-1" aria-label="Main">
          <NavLink active={view === "labels"} onClick={() => setView("labels")}>
            Labels
          </NavLink>
          <NavLink active={view === "products"} onClick={() => setView("products")}>
            Products
          </NavLink>
        </nav>

        <div className="flex flex-1 flex-wrap items-center justify-end gap-2.5">
          <ThemeToggle />
          <Button onClick={() => setStoresOpen(true)}>Stores</Button>
          {user?.email && (
            <span className="text-[13px] text-faint">{user.email}</span>
          )}
          <Button
            variant="quiet"
            onClick={() =>
              logout({ logoutParams: { returnTo: window.location.origin } })
            }
          >
            Log out
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-9 pb-14">
        {view === "labels" ? (
          <LabelList
            onAddTag={() => setAssigning("new")}
            onAssign={(tag) =>
              setAssigning({
                tagId: tag.id,
                storeId: tag.store_id,
                variationId: tag.variation_id,
              })
            }
          />
        ) : (
          <ProductList onSelect={setSelected} />
        )}
      </main>

      {selected && (
        <ItemDetailModal variation={selected} onClose={() => setSelected(null)} />
      )}

      {assigning !== null && (
        <AssignModal
          initial={assigning === "new" ? undefined : assigning}
          onClose={() => setAssigning(null)}
        />
      )}

      {storesOpen && <StoresModal onClose={() => setStoresOpen(false)} />}
    </div>
  );
}
