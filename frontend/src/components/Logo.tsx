/** The app icon: an H whose crossbar is the Haber reaction's ⇌ (green over, red under). Same drawing as pwa/icon-*.png. */
export default function Logo({ size = 30 }: { size?: number }) {
  return (
    <svg className="logo" viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <rect x="1" y="1" width="118" height="118" rx="26" fill="#0f172a" stroke="var(--line)" strokeWidth="2" />
      <rect x="26" y="24" width="15" height="72" rx="3" fill="#fff" />
      <rect x="79" y="24" width="15" height="72" rx="3" fill="#fff" />
      <path d="M47 53H74L65 45" stroke="#22c55e" strokeWidth="7" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M73 67H46L55 75" stroke="#ef4444" strokeWidth="7" fill="none" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
