// Force /login out of static generation. useSearchParams() in the page
// would otherwise need a Suspense boundary at build time.
export const dynamic = 'force-dynamic';

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
