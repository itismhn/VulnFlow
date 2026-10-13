/** VulnFlow mark: a finding flowing from critical, through high and medium, to fixed. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden>
      <rect width="32" height="32" rx="7" fill="#0E1A2B" />
      <path d="M7 9C16 9 16 23 25 23" fill="none" stroke="#334155" strokeWidth="2.2" strokeLinecap="round" />
      <circle cx="7" cy="9" r="3" fill="#DC2626" />
      <circle cx="13.7" cy="12.6" r="2.5" fill="#EA580C" />
      <circle cx="18.3" cy="19.4" r="2.5" fill="#CA8A04" />
      <circle cx="25" cy="23" r="3.2" fill="#22A3C3" />
    </svg>
  );
}
