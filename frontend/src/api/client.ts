import createClient from "openapi-fetch";
import type { paths } from "./schema.d.ts";

export const api = createClient<paths>({ baseUrl: "/v1" });

let tokenGetter: (() => Promise<string>) | null = null;

/** Called once from App after Auth0 is ready, so this module-level `api`
 * singleton can attach a bearer token without every caller threading it
 * through props or context. */
export function setTokenGetter(fn: () => Promise<string>) {
  tokenGetter = fn;
}

api.use({
  async onRequest({ request }) {
    if (!tokenGetter) return request;
    try {
      const token = await tokenGetter();
      request.headers.set("Authorization", `Bearer ${token}`);
    } catch {
      // Not logged in yet, or token fetch failed — let the request go
      // through unauthenticated; the backend will 401 gateway/admin
      // routes that need it. Store-key-gated routes never needed this.
    }
    return request;
  },
});
