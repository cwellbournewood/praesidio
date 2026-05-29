import NextAuth, { type NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

/**
 * NextAuth handler — Credentials provider that authenticates against
 * Keycloak's OIDC token endpoint via the Resource Owner Password
 * Credentials grant (a.k.a. "Direct Access Grants" in Keycloak).
 *
 * Why ROPC and not Authorization Code?
 *   - Praesidio is an internal admin console; we want a single inline
 *     login form that matches the rest of the chrome, not a redirect to
 *     a separate themed Keycloak page.
 *   - Keycloak still owns identity, password storage, brute-force lockout,
 *     group → role mapping, and audit.
 *
 * Env contract (host pnpm dev):
 *
 *   OIDC_ISSUER         = http://localhost:8081/realms/praesidio
 *   OIDC_CLIENT_ID      = praesidio
 *   OIDC_CLIENT_SECRET  = praesidio-demo-secret
 *   NEXTAUTH_URL        = http://localhost:3010
 *   NEXTAUTH_SECRET     = <random hex>
 */

const issuer = process.env.OIDC_ISSUER ?? 'http://localhost:8081/realms/praesidio';
const clientId = process.env.OIDC_CLIENT_ID ?? 'praesidio';
const clientSecret = process.env.OIDC_CLIENT_SECRET ?? 'praesidio-demo-secret';

type KeycloakTokenResponse = {
  access_token: string;
  refresh_token?: string;
  id_token?: string;
  expires_in: number;
  token_type: string;
  error?: string;
  error_description?: string;
};

type KeycloakUserInfo = {
  sub: string;
  preferred_username?: string;
  name?: string;
  email?: string;
  groups?: string[];
  tenant_id?: string;
};

async function keycloakLogin(
  username: string,
  password: string,
): Promise<{ token: KeycloakTokenResponse; userinfo: KeycloakUserInfo }> {
  const body = new URLSearchParams({
    grant_type: 'password',
    client_id: clientId,
    client_secret: clientSecret,
    username,
    password,
    scope: 'openid',
  });

  const tokenRes = await fetch(`${issuer}/protocol/openid-connect/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  const token = (await tokenRes.json()) as KeycloakTokenResponse;
  if (!tokenRes.ok || !token.access_token) {
    throw new Error(token.error_description || token.error || 'invalid_grant');
  }

  const userinfoRes = await fetch(`${issuer}/protocol/openid-connect/userinfo`, {
    headers: { Authorization: `Bearer ${token.access_token}` },
  });
  if (!userinfoRes.ok) {
    throw new Error(`userinfo failed: HTTP ${userinfoRes.status}`);
  }
  const userinfo = (await userinfoRes.json()) as KeycloakUserInfo;
  return { token, userinfo };
}

const authOptions: NextAuthOptions = {
  debug: process.env.NEXTAUTH_DEBUG === 'true',
  logger: {
    error: (code, meta) => {
      // eslint-disable-next-line no-console
      console.error('[next-auth][error]', code, meta);
    },
    warn: (code) => {
      // eslint-disable-next-line no-console
      console.warn('[next-auth][warn]', code);
    },
  },
  providers: [
    CredentialsProvider({
      id: 'keycloak',
      name: 'Praesidio',
      credentials: {
        username: { label: 'Username', type: 'text' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(creds) {
        if (!creds?.username || !creds.password) return null;
        try {
          const { token, userinfo } = await keycloakLogin(
            creds.username,
            creds.password,
          );
          return {
            id: userinfo.sub,
            name: userinfo.name ?? userinfo.preferred_username ?? userinfo.sub,
            email: userinfo.email,
            // Pass-through carried in `jwt()` below.
            accessToken: token.access_token,
            refreshToken: token.refresh_token,
            expiresAt: Math.floor(Date.now() / 1000) + token.expires_in,
            groups: userinfo.groups ?? [],
            tenantId: userinfo.tenant_id ?? null,
            username: userinfo.preferred_username ?? creds.username,
          } as never;
        } catch (err) {
          // eslint-disable-next-line no-console
          console.error('[auth] keycloak login failed:', err);
          return null;
        }
      },
    }),
  ],
  session: { strategy: 'jwt', maxAge: 10 * 60 * 60 },
  jwt: { maxAge: 10 * 60 * 60 },
  pages: {
    signIn: '/login',
    error: '/login',
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        const u = user as unknown as Record<string, unknown>;
        token.accessToken = u.accessToken as string | undefined;
        token.refreshToken = u.refreshToken as string | undefined;
        token.expiresAt = u.expiresAt as number | undefined;
        token.groups = (u.groups as string[] | undefined) ?? [];
        token.tenantId = (u.tenantId as string | undefined) ?? null;
        token.username = u.username as string | undefined;
      }
      return token;
    },
    async session({ session, token }) {
      session.accessToken = token.accessToken as string | undefined;
      session.groups = (token.groups as string[] | undefined) ?? [];
      session.tenantId = (token.tenantId as string | undefined) ?? null;
      session.expiresAt = token.expiresAt as number | undefined;
      if (session.user) {
        session.user.name =
          (token.username as string | undefined) ?? session.user.name;
      }
      return session;
    },
  },
};

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
